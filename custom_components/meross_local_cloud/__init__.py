"""Meross devices platform loader"""
import asyncio
import logging
import ssl
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional
from urllib.parse import urlparse

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .common import (
    ATTR_CONFIG,
    DOMAIN,
    MEROSS_PLATFORMS,
    notify_error,
    log_exception,
    CONF_STORED_CREDS,
    CONF_HTTP_ENDPOINT,
    HTTP_API_RE,
    HTTP_UPDATE_INTERVAL, DEVICE_LIST_COORDINATOR,
    CONF_OPT_CUSTOM_USER_AGENT, CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_CA_PEM, CONF_CA_FINGERPRINT, MISSING_TRACKER,
    BROKER_ADAPTER, SHUTTER_CONFIG_CACHE, effective_user_agent
)
from .broker_config import RollerShutterConfigCache
from .broker_devices import BrokerDeviceInfo, async_list_devices
from .broker_http import (
    BrokerAuthError,
    BrokerCredentials,
    BrokerHttpClient,
    BrokerHttpError,
    BrokerTokenError,
)
from .missing_devices import MissingDeviceTracker
from .log_redaction import install as install_log_redaction
from .version import MEROSS_INTEGRATION_VERSION
from .tls import (
    async_fetch_ca,
    build_client_ssl_context,
    certificate_hostnames,
    fetch_server_certificate,
    fingerprint,
    host_is_covered,
    is_ca,
    parse_certificate,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HTTP_ENDPOINT): cv.string,
                vol.Optional(CONF_STORED_CREDS): cv.string,
                vol.Optional(CONF_OVERRIDE_MQTT_ENDPOINT): cv.string
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def print_startup_message(http_devices: List[BrokerDeviceInfo]):
    http_info = "\n".join(
        [f"- {x.dev_name} ({x.device_type}) - {x.online_status}" for x in http_devices]
    )

    start_message = (
        f"\n"
        f"===============================\n"
        f"Meross Local Cloud\n"
        f"Fork of the Meross Cloud component by Alberto Geniola:\n"
        f"https://github.com/albertogeniola/meross-homeassistant\n"
        f"Profile engine version: {MEROSS_INTEGRATION_VERSION}\n"
        f"-------------------------------\n"
        f"In case of errors or unexpected behavior, please report them here:\n"
        f"https://github.com/mazkagaz/meross-local-cloud/issues\n"
        f"-------------------------------\n"
        f"List of devices reported by HTTP API:\n"
        f"{http_info}"
        f"\n==============================="
    )
    _LOGGER.info(start_message)


class MerossCoordinator(DataUpdateCoordinator):
    def __init__(self,
                 hass: HomeAssistant,
                 config_entry: ConfigEntry,
                 http_api_endpoint: str,
                 creds: BrokerCredentials,
                 mqtt_override_address: Optional[tuple[str, int]],
                 update_interval: timedelta,
                 ua_header: str,
                 ca_pem: str,
                 ca_check_hostname: bool = False):

        self._entry = config_entry
        self._http_api_endpoint = http_api_endpoint
        self._cached_creds = creds
        self._mqtt_override_address = mqtt_override_address
        self._ca_pem = ca_pem
        self._ca_check_hostname = ca_check_hostname
        self._mqtt_ssl_context_verified: Optional[ssl.SSLContext] = None
        self._broker_http: Optional[BrokerHttpClient] = None
        self._setup_done = False
        self._ua_header = ua_header
        self._missing_tracker = MissingDeviceTracker(hass, config_entry.entry_id)

        super().__init__(hass=hass, logger=_LOGGER, name="meross_http_coordinator", update_interval=update_interval,
                         update_method=self._async_fetch_http_data)

    async def _async_fetch_http_data(self):
        if self._broker_http is None:
            return {}
        try:
            async with asyncio.timeout(10):
                # Fetch devices and compose a quick-access dictionary
                devices = await async_list_devices(self._broker_http)
                data = {device.uuid: device for device in devices}
                # Only a successful poll may start or clear a 48 h countdown.
                await self._missing_tracker.async_update(data.values())
                return data

        except (BrokerAuthError, BrokerTokenError) as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except (BrokerHttpError, TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def initial_setup(self):
        if self._setup_done:
            raise ValueError("This coordinator was already set up")

        try:
            self._mqtt_ssl_context_verified = await self.hass.async_add_executor_job(
                build_client_ssl_context, self._ca_pem,
                self._ca_check_hostname)
        except ssl.SSLError as err:
            raise ConfigEntryNotReady(
                f"Unable to trust the broker CA: {err}") from err

        self._broker_http = BrokerHttpClient(
            self._http_api_endpoint,
            lambda: self._cached_creds.token,
            self._mqtt_ssl_context_verified,
            user_agent=self._ua_header)

        try:
            async with asyncio.timeout(10):
                http_devices = await async_list_devices(self._broker_http)
        except (BrokerAuthError, BrokerTokenError) as err:
            raise ConfigEntryAuthFailed from err
        except (BrokerHttpError, TimeoutError, aiohttp.ClientError) as err:
            raise ConfigEntryNotReady(
                f"Error communicating with API: {err}") from err

        if self._cached_creds.domain != self._http_api_endpoint:
            _LOGGER.warning(
                "Stored credentials domain <%s> differs from the configured "
                "endpoint; using %s.",
                self._cached_creds.domain, self._http_api_endpoint)
            self._cached_creds = replace(
                self._cached_creds, domain=self._http_api_endpoint)
            self.hass.config_entries.async_update_entry(
                entry=self._entry,
                data={
                    CONF_HTTP_ENDPOINT: self._http_api_endpoint,
                    CONF_STORED_CREDS: self._cached_creds.as_dict(),
                },
            )

        # Since we already have fetched for the DeviceList, publish it right away
        self.async_set_updated_data({device.uuid: device for device in http_devices})

        print_startup_message(http_devices=self.data.values())

        # Older versions could leave devices behind in the HA registry only:
        # seed them so the 48 h repair can offer to clean them up.
        await self._missing_tracker.async_reconcile(self._entry.entry_id)
        await self._missing_tracker.async_update(http_devices)
        self.hass.data[DOMAIN][MISSING_TRACKER] = self._missing_tracker

        # If no exception is thrown so far, it means setup was successful
        self._setup_done = True

    @property
    def http_api_endpoint(self) -> str:
        return self._http_api_endpoint

    @property
    def config_entry_id(self) -> str:
        return self._entry.entry_id

    @property
    def credentials(self) -> BrokerCredentials:
        return self._cached_creds

    @property
    def user_agent(self) -> str:
        return self._ua_header

    @property
    def mqtt_address(self) -> tuple[str, int]:
        if self._mqtt_override_address is not None:
            return self._mqtt_override_address
        host = urlparse(self._http_api_endpoint).hostname or "localhost"
        return host, 2001

    @property
    def mqtt_ssl_context(self) -> ssl.SSLContext:
        return self._mqtt_ssl_context_verified


def _is_stale_profile_uid(unique_id: str) -> bool:
    if "#BASE:" in unique_id:
        return False
    if unique_id == "broker_profile_backend":
        return False
    if unique_id.startswith(f"{DOMAIN}:"):
        return False
    return unique_id.split(":", 1)[0] in MEROSS_PLATFORMS


def async_prune_stale_profile_entities(hass: HomeAssistant,
                                       entry: ConfigEntry) -> None:
    """Drop profile entities registered with the pre-D5-c unique_ids."""
    registry = er.async_get(hass)
    removed = 0
    for entity in er.async_entries_for_config_entry(
            registry, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        if _is_stale_profile_uid(entity.unique_id):
            registry.async_remove(entity.entity_id)
            removed += 1
    if removed:
        _LOGGER.info(
            "Removed %d profile entit(y/ies) with pre-D5-c unique_ids",
            removed)


async def _async_prepare_tls(
        hass: HomeAssistant, config_entry: ConfigEntry,
        endpoint: str, mqtt_host: Optional[str]):
    """Fetch the broker CA, pin it, and build the HTTP SSL context."""
    stored_pem = config_entry.data.get(CONF_CA_PEM)
    stored_fp = config_entry.data.get(CONF_CA_FINGERPRINT)
    ca_pem = stored_pem
    ca_fp = stored_fp
    fetched = await async_fetch_ca(endpoint)
    if fetched:
        cert = parse_certificate(fetched)
        if cert is not None and is_ca(cert):
            ca_fp = fingerprint(cert)
            if stored_fp and ca_fp != stored_fp:
                _LOGGER.warning(
                    "Broker TLS CA changed (SHA-256 %s); trusting the new CA.",
                    ca_fp)
            ca_pem = fetched
        else:
            raise ConfigEntryNotReady(
                "The /ca.crt served by the broker is not a valid CA "
                "certificate. Update the broker (broker 1.0.0 or later).")

    if ca_pem is None:
        raise ConfigEntryNotReady(
            "Unable to retrieve the broker CA certificate. Update the broker "
            "(broker 1.0.0 or later).")

    parsed = urlparse(endpoint)
    host = parsed.hostname
    http_check = False
    mqtt_check = False
    server_info: Optional[Dict[str, Any]] = None
    if host:
        ports = [parsed.port or 443] if parsed.scheme == "https" else []
        ports.extend((2004, 2001))
        server_cert = None
        for port in dict.fromkeys(ports):
            pem = await hass.async_add_executor_job(
                fetch_server_certificate, host, port)
            server_cert = parse_certificate(pem) if pem else None
            if server_cert is not None:
                break
        if server_cert is not None:
            http_check = host_is_covered(server_cert, host)
            mqtt_check = host_is_covered(
                server_cert, mqtt_host or host)
            server_info = {
                "subject": server_cert.subject.rfc4514_string(),
                "issuer": server_cert.issuer.rfc4514_string(),
                "valid_until": server_cert.not_valid_after_utc.isoformat(),
                "fingerprint": fingerprint(server_cert),
                "hostnames": sorted(certificate_hostnames(server_cert)),
            }

    http_context = await hass.async_add_executor_job(
        build_client_ssl_context, ca_pem, http_check)
    return (ca_pem, ca_fp, http_context, http_check, mqtt_check,
            server_info)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """
    This class is called by the HomeAssistant framework when a configuration entry is provided.
    For us, the configuration entry is the username-password credentials that the user
    needs to access the Meross cloud.
    """

    install_log_redaction(config_entry.entry_id)

    # Retrieve the stored credentials from config-flow
    http_api_endpoint = config_entry.data.get(CONF_HTTP_ENDPOINT)
    _LOGGER.info("Loaded %s: %s", CONF_HTTP_ENDPOINT, http_api_endpoint)

    str_creds = config_entry.data.get(CONF_STORED_CREDS)
    _LOGGER.info("Loaded %s: %s", CONF_STORED_CREDS, "******")

    mqtt_override_address = config_entry.data.get(CONF_OVERRIDE_MQTT_ENDPOINT)
    _LOGGER.info("Override MQTT address set to: %s", "no" if mqtt_override_address is None else "yes -> %s" % mqtt_override_address)

    # Make sure we have all the needed requirements
    if http_api_endpoint is None or HTTP_API_RE.fullmatch(http_api_endpoint) is None:
        raise ConfigEntryAuthFailed("Missing or wrong HTTP_API_ENDPOINT")
    if not http_api_endpoint.lower().startswith("https://"):
        raise ConfigEntryAuthFailed(
            "The broker must be reached over HTTPS. Use the https://…:2004 "
            "endpoint and update the broker (broker 1.0.0 or later).")
    if str_creds is None:
        raise ConfigEntryAuthFailed("Missing credentials. Please re-authenticate.")
    mqtt_host = None
    if mqtt_override_address is not None:
        mqtt_host = mqtt_override_address.split(":")[0]
        mqtt_port = int(mqtt_override_address.split(":")[1])
        mqtt_override_address = (mqtt_host, mqtt_port)

    (ca_pem, ca_fingerprint, http_ssl_context, http_check_hostname,
     ca_check_hostname, server_tls) = await _async_prepare_tls(
        hass, config_entry, http_api_endpoint, mqtt_host)
    _LOGGER.info(
        "Meross Local Cloud %s: broker CA pinned (SHA-256 %s), "
        "hostname verification %s",
        MEROSS_INTEGRATION_VERSION,
        ca_fingerprint[:16] if ca_fingerprint else "unknown",
        "enabled" if ca_check_hostname else "disabled")

    try:
        issued_on = datetime.fromisoformat(str_creds.get("issued_on"))
    except (TypeError, ValueError):
        issued_on = datetime.now()
    creds = BrokerCredentials(
        domain=str_creds.get("domain") or http_api_endpoint,
        mqtt_domain=str_creds.get("mqtt_domain") or "",
        token=str_creds.get("token") or "",
        key=str_creds.get("key") or "",
        user_id=str(str_creds.get("user_id") or ""),
        user_email=str_creds.get("user_email") or "",
        issued_on=issued_on,
    )

    # Initialize the HASS structure
    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["ADDED_ENTITIES_IDS"] = set()
    hass.data[DOMAIN]["TLS_INFO"] = {
        "http_verified": True,
        "mqtt_verified": True,
        "http_host": urlparse(http_api_endpoint).hostname,
        "mqtt_host": mqtt_host or urlparse(http_api_endpoint).hostname,
        "http_check_hostname": http_check_hostname,
        "mqtt_check_hostname": ca_check_hostname,
        "server": server_tls,
    }

    # Retrieve options we need
    ua_header = effective_user_agent(
        config_entry.options.get(CONF_OPT_CUSTOM_USER_AGENT))

    try:
        # Setup the coordinator
        meross_coordinator = MerossCoordinator(
            hass=hass,
            config_entry=config_entry,
            http_api_endpoint=http_api_endpoint,
            creds=creds,
            mqtt_override_address=mqtt_override_address,
            update_interval=timedelta(seconds=HTTP_UPDATE_INTERVAL),
            ua_header=ua_header,
            ca_pem=ca_pem,
            ca_check_hostname=ca_check_hostname,
        )

        # Initiate the coordinator. This validates the token and lists devices.
        await meross_coordinator.initial_setup()
        hass.data[DOMAIN][DEVICE_LIST_COORDINATOR] = meross_coordinator
        hass.data[DOMAIN][SHUTTER_CONFIG_CACHE] = RollerShutterConfigCache(
            BrokerHttpClient(
                meross_coordinator.http_api_endpoint,
                lambda: meross_coordinator.credentials.token,
                meross_coordinator.mqtt_ssl_context,
                user_agent=meross_coordinator.user_agent))

        from .broker_adapter import BrokerProfileAdapter

        adapter = BrokerProfileAdapter(hass, meross_coordinator)
        adapter.entities_only = True
        hass.data[DOMAIN][BROKER_ADAPTER] = adapter

        if ca_pem and (
                config_entry.data.get(CONF_CA_PEM) != ca_pem
                or config_entry.data.get(CONF_CA_FINGERPRINT) != ca_fingerprint):
            hass.config_entries.async_update_entry(
                config_entry,
                data={
                    **config_entry.data,
                    CONF_CA_PEM: ca_pem,
                    CONF_CA_FINGERPRINT: ca_fingerprint,
                },
            )

        # Mount the profile platforms, then start discovery in the background.
        async_prune_stale_profile_entities(hass, config_entry)
        await hass.config_entries.async_forward_entry_setups(config_entry, MEROSS_PLATFORMS)

        reload_pending = False

        def _http_api_polled(*args, **kwargs):
            nonlocal reload_pending
            devices = (meross_coordinator.data or {}).values()
            adapter.async_update_devices(devices)
            if reload_pending or adapter.state != "connected":
                return
            unknown = adapter.unknown_devices(devices)
            if unknown:
                reload_pending = True
                _LOGGER.info(
                    "The broker reported %d new device(s); reloading the "
                    "integration to describe them", len(unknown))
                hass.async_create_task(
                    hass.config_entries.async_reload(config_entry.entry_id))

        config_entry.async_on_unload(
            meross_coordinator.async_add_listener(_http_api_polled))
        config_entry.async_on_unload(
            config_entry.add_update_listener(update_listener))

        adapter.start_background(hass)

        return True

    except (BrokerAuthError, BrokerTokenError) as ex:
        _LOGGER.warning("Local broker authentication failed: %s", ex)
        raise ConfigEntryAuthFailed("Invalid token or credentials")
    except BrokerHttpError as ex:
        msg = ("Your local broker login is invalid or the broker could not "
               "be reached at the moment.")
        notify_error(
            hass,
            "http_connection",
            "Meross Local Cloud",
            "Could not connect to the local broker. Please check"
            " the broker address and the local login",
        )
        log_exception(msg, logger=_LOGGER)
        raise ConfigEntryNotReady() from ex


async def update_listener(hass, entry):
    """Reload so the custom user agent reaches every HTTP client."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    # Unload entities first
    _LOGGER.info("Removing Meross Local Cloud integration.")
    _LOGGER.info("Cleaning up resources...")

    for platform in MEROSS_PLATFORMS:
        _LOGGER.info(f"Cleaning up platform {platform}")
        await hass.config_entries.async_forward_entry_unload(entry, platform)

    adapter = hass.data.get(DOMAIN, {}).get(BROKER_ADAPTER)
    if adapter is not None:
        await adapter.async_stop()

    _LOGGER.info("Cleaning up memory...")
    for plat in MEROSS_PLATFORMS:
        if plat in hass.data[DOMAIN]:
            hass.data[DOMAIN][plat].clear()
            del hass.data[DOMAIN][plat]
    hass.data[DOMAIN].clear()
    del hass.data[DOMAIN]

    _LOGGER.info("Meross Local Cloud component removal done.")
    return True


async def async_remove_entry(hass, entry) -> None:
    # TODO
    pass


async def async_setup(hass, config):
    """
    This method gets called if HomeAssistant has a valid meross_local_cloud: configuration entry within
    configurations.yaml.

    Thus, in this method we simply trigger the creation of a config entry.

    :return:
    """

    conf = config.get(DOMAIN)
    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][ATTR_CONFIG] = conf

    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=conf
            )
        )

    return True
