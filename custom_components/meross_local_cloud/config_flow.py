import asyncio
import logging
from typing import Dict, Any, Optional, List
from urllib.error import HTTPError
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from aiohttp import ClientConnectorSSLError, ClientConnectorError
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from requests.exceptions import ConnectTimeout
from homeassistant.components import network, zeroconf

from .common import DOMAIN, CONF_STORED_CREDS, CONF_MFA_CODE, \
    CONF_HTTP_ENDPOINT, CONF_CA_PEM, CONF_CA_FINGERPRINT, \
    CONF_BROKER_HOST, CONF_HTTPS_PORT, CONF_MQTT_PORT, \
    CONF_OPT_CUSTOM_USER_AGENT, \
    MEROSS_LOCAL_MDNS_SERVICE_TYPES, MEROSS_LOCAL_MDNS_MQTT_SERVICE_TYPE, \
    MEROSS_LOCAL_MDNS_API_SERVICE_TYPE, CONF_OVERRIDE_MQTT_ENDPOINT, \
    effective_user_agent
from .broker_http import (
    BrokerAuthError,
    BrokerCredentials,
    BrokerHttpClient,
    BrokerHttpError,
    BrokerTokenError,
)
from .tls import (
    async_fetch_ca,
    build_client_ssl_context,
    fingerprint,
    is_ca,
    parse_certificate,
)
from .version import MEROSS_INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1


class MerossFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Meross config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._http_api: Optional[str] = None
        self._mqtt_boker: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._broker_host: str = ""
        # The broker only ever listens on these two ports; prefilling them
        # keeps the manual (Docker/HA Container) form to host + credentials.
        self._https_port: str = "2004"
        self._mqtt_port: str = "2001"
        self._form_step: str = "configure_manager"
        self._local_mode: bool = True
        self._discovered_services: List[AsyncServiceInfo] = []
        self._is_reauth: bool = False
        self._discovered_host: Optional[str] = None
        self._discovered_api: Optional[str] = None
        self._discovered_mqtt: Optional[str] = None
        self._discovered_https: bool = False

    @staticmethod
    def _sanitize_host(raw: Optional[str]) -> str:
        """Keep only the host part of a pasted address."""
        host = (raw or "").strip()
        if "://" in host:
            host = host.split("://", 1)[1]
        host = host.split("/", 1)[0]
        if host.startswith("["):
            return host.split("]", 1)[0].lstrip("[")
        if host.count(":") == 1:
            host = host.split(":", 1)[0]
        return host.strip()

    def _build_form_schema(self, username=None, password=None,
                           requires_mfa: bool = False) -> vol.Schema:
        params = {
            vol.Optional(CONF_BROKER_HOST, default=self._broker_host): str,
            vol.Optional(CONF_HTTPS_PORT, default=self._https_port): str,
            vol.Optional(CONF_MQTT_PORT, default=self._mqtt_port): str,
            vol.Optional(
                CONF_USERNAME,
                default=(username if username is not None else self._username) or ""): str,
            vol.Optional(
                CONF_PASSWORD,
                default=(password if password is not None else self._password) or ""): str,
        }
        if requires_mfa:
            params[vol.Required(CONF_MFA_CODE)] = str
        return vol.Schema(params)

    def _show_form(self, errors=None, username=None, password=None,
                   requires_mfa: bool = False):
        kwargs = {}
        if self._form_step == "configure_manager_missing":
            kwargs["description_placeholders"] = {
                "broker_url":
                    "https://github.com/mazkagaz/meross-local-broker#readme",
            }
        return self.async_show_form(
            step_id=self._form_step,
            data_schema=self._build_form_schema(
                username=username, password=password,
                requires_mfa=requires_mfa),
            errors=errors or {},
            **kwargs,
        )

    @staticmethod
    def _split_host_port(address: Optional[str]):
        if not address:
            return "", ""
        host, _, port = address.partition(":")
        return host, port

    def _reauth_entry(self) -> ConfigEntry:
        entry_id = self.context.get("entry_id")
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if entry is None:
            raise RuntimeError("Reauthentication entry not found")
        return entry

    def _load_reauth_defaults(self) -> None:
        """Reuse the stored broker settings instead of resetting to defaults."""
        entry = self._reauth_entry()
        data = entry.data
        creds = data.get(CONF_STORED_CREDS)
        if not isinstance(creds, dict):
            creds = {}
        endpoint = data.get(CONF_HTTP_ENDPOINT) or ""
        parsed = urlparse(("https://" + endpoint) if "://" not in endpoint
                          else endpoint)
        self._broker_host = parsed.hostname or ""
        self._https_port = str(parsed.port or 2004)
        mqtt_host, mqtt_port = self._split_host_port(
            data.get(CONF_OVERRIDE_MQTT_ENDPOINT))
        self._mqtt_port = mqtt_port or "2001"
        self._http_api = data.get(CONF_HTTP_ENDPOINT)
        self._mqtt_boker = data.get(CONF_OVERRIDE_MQTT_ENDPOINT)
        self._username = creds.get("user_email")
        self._password = None
        self._form_step = "configure_manager_reauth"

    async def async_step_reauth(self, entry_data=None):
        """Reauthenticate against the existing broker configuration."""
        self._is_reauth = True
        self._load_reauth_defaults()
        return self._show_form()

    async def _resolve_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        _LOGGER.debug("MDNS resolving service type: %s, name: %s", service_type, name)
        info = AsyncServiceInfo(service_type, name)
        await info.async_request(zeroconf, 4000)
        if info:
            self._discovered_services.append(info)

    def _async_on_service_state_change(self, zeroconf: Zeroconf, service_type: str, name: str,
                                       state_change: ServiceStateChange) -> None:
        _LOGGER.debug("MDNS discovery state: %s, service type: %s, name: %s", str(state_change), service_type, name)
        if state_change is not ServiceStateChange.Added:
            return
        # Resolve the service on a different async task
        asyncio.ensure_future(self._resolve_service(zeroconf, service_type, name))

    @staticmethod
    def _txt_records(info: AsyncServiceInfo) -> Dict[str, str]:
        records: Dict[str, str] = {}
        for key, value in (info.properties or {}).items():
            try:
                name = key.decode() if isinstance(key, bytes) else str(key)
                text = value.decode() if isinstance(value, bytes) else str(value)
            except (UnicodeDecodeError, AttributeError):
                continue
            records[name.lower()] = text
        return records

    @staticmethod
    def _url_host(host: str) -> str:
        return f"[{host}]" if ":" in host else host

    async def _probe_broker(self, host: str, port: int, scheme: str,
                            timeout: float = 3) -> bool:
        url = f"{scheme}://{self._url_host(host)}:{port}/ca.crt"
        connector = aiohttp.TCPConnector(ssl=False) if scheme == "https" else None
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    return response.status < 500
        except Exception as err:  # noqa: BLE001 - discovery is best effort
            _LOGGER.debug("Broker probe failed for %s: %s", url, err)
            return False

    async def _discover_services(self):
        """Return (host, api_endpoint, mqtt_endpoint, use_https) or None."""
        self._discovered_services.clear()
        aiozc = await zeroconf.async_get_async_instance(self.hass)
        browser = AsyncServiceBrowser(aiozc.zeroconf, MEROSS_LOCAL_MDNS_SERVICE_TYPES,
                                      handlers=[self._async_on_service_state_change])
        # Wait a bit to collect MDNS responses and then stop the browser
        await asyncio.sleep(5)
        await browser.async_cancel()

        api_infos = [
            info for info in self._discovered_services
            if info.type == MEROSS_LOCAL_MDNS_API_SERVICE_TYPE
        ]
        mqtt_infos = [
            info for info in self._discovered_services
            if info.type == MEROSS_LOCAL_MDNS_MQTT_SERVICE_TYPE
        ]
        _LOGGER.info("Found %d API and %d MQTT mDNS services.",
                     len(api_infos), len(mqtt_infos))

        # The broker add-on runs on this Home Assistant host. When mDNS
        # resolution is incomplete or unavailable, probing the local interface
        # addresses still finds it.
        local_hosts: List[str] = []
        try:
            for adapter in await network.async_get_adapters(self.hass):
                if not adapter.get("enabled", True):
                    continue
                for ipv4 in adapter.get("ipv4", []):
                    address = ipv4.get("address")
                    if address and not address.startswith("127.") \
                            and address not in local_hosts:
                        local_hosts.append(address)
        except Exception as err:  # noqa: BLE001 - discovery is best effort
            _LOGGER.debug("Unable to list local network adapters: %s", err)

        if not api_infos:
            if not local_hosts:
                return None
            _LOGGER.info(
                "No mDNS service found; probing the local addresses %s on the "
                "default API ports.", local_hosts)
            results = await asyncio.gather(*(
                self._probe_broker(host, 2004, "https", timeout=1.5)
                for host in local_hosts
            ))
            for host, ok in zip(local_hosts, results):
                if not ok:
                    continue
                _LOGGER.info("Discovered Meross broker at %s:2004 (HTTPS)",
                             host)
                return (host, f"https://{self._url_host(host)}:2004",
                        f"{host}:2001", True)
            return None

        mqtt_port = 2001
        if mqtt_infos and mqtt_infos[0].port:
            mqtt_port = int(mqtt_infos[0].port)

        for api_info in api_infos:
            records = self._txt_records(api_info)
            hosts: List[str] = []

            def _add_host(candidate: Optional[str]):
                if not candidate:
                    return
                candidate = candidate.strip().rstrip(".")
                if candidate and candidate not in hosts:
                    hosts.append(candidate)

            for host in (records.get("host") or "").split(","):
                _add_host(host)
            # The A/AAAA records cover brokers that do not publish the TXT
            # host entry; the .local server name is not resolvable everywhere.
            for address in api_info.parsed_addresses() or []:
                _add_host(address)
            _add_host(api_info.server)
            for host in local_hosts:
                _add_host(host)
            if not hosts:
                _LOGGER.warning(
                    "mDNS service %s was announced but could not be resolved "
                    "to an address.", api_info.name)
                continue
            _LOGGER.debug("Probing broker candidates for %s: %s",
                          api_info.name, hosts)
            try:
                https_raw = records.get("https_port")
                # No TXT record means the service was not fully resolved:
                # probe the broker default HTTPS port.
                https_port = int(https_raw) if https_raw else 2004
            except (TypeError, ValueError):
                continue
            if not https_port:
                _LOGGER.info(
                    "Broker %s advertises HTTPS as disabled; TLS is required.",
                    api_info.name)
                continue
            for host in hosts:
                if await self._probe_broker(host, https_port, "https"):
                    _LOGGER.info("Discovered Meross broker at %s:%d (HTTPS)",
                                 host, https_port)
                    return (host, f"https://{self._url_host(host)}:{https_port}",
                            f"{host}:{mqtt_port}", True)
        _LOGGER.info("Meross mDNS services found but no API endpoint responded.")
        return None

    async def async_step_user(self, user_input=None) -> Dict[str, Any]:
        """Configure the local broker connection."""
        _LOGGER.info("Starting local broker setup (integration %s)",
                     MEROSS_INTEGRATION_VERSION)
        self._local_mode = True
        self._is_reauth = False

        discovery = None
        try:
            discovery = await self._discover_services()
        except Exception as ex:
            # mDNS is best-effort: never fail the whole flow if the discovery
            # stack cannot start (network permissions, container networking, etc.).
            _LOGGER.warning("Local mDNS discovery failed: %s", ex, exc_info=True)

        if discovery:
            (self._discovered_host, self._discovered_api,
             self._discovered_mqtt, self._discovered_https) = discovery
            self._broker_host = self._discovered_host or ""
            api = urlparse(self._discovered_api or "")
            self._https_port = str(api.port or 2004)
            _, mqtt_port = self._split_host_port(self._discovered_mqtt)
            self._mqtt_port = mqtt_port or "2001"
            self._form_step = "configure_manager"
            return self._show_form()

        self._discovered_host = None
        self._discovered_api = None
        self._discovered_mqtt = None
        self._discovered_https = False
        self._broker_host = ""
        self._https_port = "2004"
        self._mqtt_port = "2001"
        self._form_step = "configure_manager_missing"
        return self._show_form(errors={"base": "mdns_lookup_failed"})

    async def async_step_configure_manager(self, user_input=None) -> Dict[str, Any]:
        return await self._async_handle_form(user_input)

    async def async_step_configure_manager_missing(
            self, user_input=None) -> Dict[str, Any]:
        return await self._async_handle_form(user_input)

    async def async_step_configure_manager_reauth(
            self, user_input=None) -> Dict[str, Any]:
        return await self._async_handle_form(user_input)

    async def _async_handle_form(self, user_input):
        if not user_input:
            return self._show_form()

        host = self._sanitize_host(user_input.get(CONF_BROKER_HOST))
        https_raw = (user_input.get(CONF_HTTPS_PORT) or "").strip()
        mqtt_raw = (user_input.get(CONF_MQTT_PORT) or "").strip()
        username = user_input.get(CONF_USERNAME) or None
        password = user_input.get(CONF_PASSWORD) or None
        mfa_code = user_input.get(CONF_MFA_CODE)
        requires_mfa = mfa_code is not None

        self._broker_host = host
        self._https_port = https_raw
        self._mqtt_port = mqtt_raw

        if not host:
            return self._show_form(
                errors={"base": "missing_broker_host"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        try:
            https_port = int(https_raw)
            mqtt_port = int(mqtt_raw)
        except (TypeError, ValueError):
            return self._show_form(
                errors={"base": "invalid_port"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        if not (1 <= https_port <= 65535 and 1 <= mqtt_port <= 65535):
            return self._show_form(
                errors={"base": "invalid_port"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        if 2003 in (https_port, mqtt_port):
            return self._show_form(
                errors={"base": "port_reserved"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        if not username or not password:
            return self._show_form(
                errors={"base": "missing_credentials"},
                username=username, password=password,
                requires_mfa=requires_mfa)

        endpoint = f"https://{self._url_host(host)}:{https_port}"
        mqtt = f"{host}:{mqtt_port}"
        self._http_api = endpoint
        self._mqtt_boker = mqtt
        self._username = username
        self._password = password

        ca_pem = await async_fetch_ca(endpoint)
        ca_cert = parse_certificate(ca_pem) if ca_pem else None
        if ca_cert is None or not is_ca(ca_cert):
            _LOGGER.error(
                "Unable to retrieve a valid broker CA from %s", endpoint)
            return self._show_form(
                errors={"base": "ca_unavailable"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        ca_fingerprint = fingerprint(ca_cert)
        ssl_context = await self.hass.async_add_executor_job(
            build_client_ssl_context, ca_pem, False)

        try:
            creds = await self._test_authorization(
                api_base_url=endpoint, username=username,
                password=password, mfa_code=mfa_code,
                ssl_context=ssl_context)
            _LOGGER.info("HTTP API successful tested against %s.", endpoint)
        except BrokerAuthError as ex:
            _LOGGER.error("Unable to connect to Meross HTTP api: %s", str(ex))
            return self._show_form(
                errors={"base": "invalid_credentials"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        except (BrokerTokenError, BrokerHttpError, ConnectTimeout,
                HTTPError, TimeoutError) as ex:
            _LOGGER.error("Unable to connect to Meross HTTP api: %s", str(ex))
            return self._show_form(
                errors={"base": "connection_error"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        except ClientConnectorSSLError as ex:
            _LOGGER.error("Unable to connect to Meross HTTP api: %s", str(ex))
            return self._show_form(
                errors={"base": "api_invalid_ssl_code"},
                username=username, password=password,
                requires_mfa=requires_mfa)
        except ClientConnectorError as ex:
            _LOGGER.error("Connection ERROR to HTTP api: %s", str(ex))
            code = ("api_connection_refused"
                    if isinstance(ex.os_error, ConnectionRefusedError)
                    else "client_connection_error")
            return self._show_form(
                errors={"base": code},
                username=username, password=password,
                requires_mfa=requires_mfa)
        except Exception as ex:
            _LOGGER.exception(
                "Unable to connect to Meross HTTP api, ex: %s", str(ex))
            return self._show_form(
                errors={"base": "unknown_error"},
                username=username, password=password,
                requires_mfa=requires_mfa)

        data = {
            CONF_HTTP_ENDPOINT: endpoint,
            CONF_OVERRIDE_MQTT_ENDPOINT: mqtt,
            CONF_CA_PEM: ca_pem,
            CONF_CA_FINGERPRINT: ca_fingerprint,
            CONF_STORED_CREDS: creds.as_dict(),
        }

        if self._is_reauth:
            entry = self._reauth_entry()
            self.hass.config_entries.async_update_entry(
                entry, data=data, title=endpoint)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        await self.async_set_unique_id(endpoint)
        self._abort_if_unique_id_configured(updates=data, reload_on_update=True)
        return self.async_create_entry(title=endpoint, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MerossOptionsFlowHandler()

    @staticmethod
    async def _test_authorization(
            api_base_url: str, username: str, password: str,
            mfa_code: str = None, ssl_context=None,
    ) -> BrokerCredentials:
        return await BrokerHttpClient.async_login(
            api_base_url, username, password, mfa_code=mfa_code,
            ssl_context=ssl_context)

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        if self._async_current_entries():
            _LOGGER.warning(
                "Only one configuration of Meross is allowed. If you added Meross via configuration.yaml, "
                "you should now remove that and use the integration menu con configure it."
            )
            return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_user(import_config)


class MerossOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for Meross Component."""

    async def async_step_init(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            data = {k: v for k, v in user_input.items()
                    if v not in (None, "")}
            if str(data.get(CONF_OPT_CUSTOM_USER_AGENT, "")).startswith(
                    "MerossHA/"):
                # Keep the version-tracking default instead of freezing it.
                data.pop(CONF_OPT_CUSTOM_USER_AGENT, None)
            return self.async_create_entry(title="", data=data)

        saved_options = {}
        if self.config_entry is not None:
            saved_options = self.config_entry.options
        saved_ua = effective_user_agent(
            saved_options.get(CONF_OPT_CUSTOM_USER_AGENT))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_OPT_CUSTOM_USER_AGENT,
                             default=saved_ua): str,
            })
        )
