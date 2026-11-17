import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from urllib.error import HTTPError

import aiohttp
import voluptuous as vol
from aiohttp import ClientConnectorSSLError, ClientConnectorError
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode
from meross_iot.http_api import MerossHttpClient
from meross_iot.model.credentials import MerossCloudCreds
from meross_iot.model.http.exception import UnauthorizedException, MissingMFA, BadLoginException
from requests.exceptions import ConnectTimeout
from homeassistant.components import zeroconf

from .common import DOMAIN, CONF_STORED_CREDS, CONF_MFA_CODE, \
    CONF_BROKER_HOST, CONF_USE_HTTPS, CONF_ADVANCED, \
    CONF_HTTP_ENDPOINT, CONF_MQTT_SKIP_CERT_VALIDATION, CONF_HTTP_SKIP_CERT_VALIDATION, \
    CONF_OPT_CUSTOM_USER_AGENT, HTTP_API_RE, \
    MEROSS_LOCAL_MDNS_SERVICE_TYPES, MEROSS_LOCAL_MDNS_MQTT_SERVICE_TYPE, \
    MEROSS_LOCAL_MDNS_API_SERVICE_TYPE, CONF_OVERRIDE_MQTT_ENDPOINT, \
    CONF_OPT_LAN, CONF_OPT_LAN_MQTT_ONLY, \
    CONF_OPT_LAN_HTTP_FIRST, CONF_OPT_LAN_HTTP_FIRST_ONLY_GET, DEFAULT_USER_AGENT
from .patches import set_http_cert_validation

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1


class MerossFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Meross config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_PUSH

    def __init__(self) -> None:
        """Initialize flow."""
        self._http_api: Optional[str] = None
        self._mqtt_boker: Optional[str] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        self._local_mode: bool = True
        self._skip_cert_validation: Optional[bool] = None
        self._skip_http_cert_validation: Optional[bool] = None
        self._discovered_services: List[AsyncServiceInfo] = []
        self._is_reauth: bool = False
        self._discovered_host: Optional[str] = None
        self._discovered_api: Optional[str] = None
        self._discovered_mqtt: Optional[str] = None
        self._discovered_https: bool = False
        self._simple_host: Optional[str] = None
        self._simple_use_https: bool = True
        self._include_simple_host: bool = False
        self._requires_mfa: bool = False

    def _build_setup_schema(
            self,
            http_endpoint: str = None,
            username: str = None,
            password: str = None,
            override_mqtt_endpoint: str = None,
            skip_cert_validation: bool = None,
            skip_http_cert_validation: bool = None,
            requires_mfa: bool = False
    ) -> vol.Schema:
        http_endpoint_default = http_endpoint if http_endpoint is not None else self._http_api
        mqtt_endpoint_default = override_mqtt_endpoint if override_mqtt_endpoint is not None else self._mqtt_boker
        username_default = username if username is not None else self._username
        password_default = password if password is not None else self._password
        skip_cert_validation_default = skip_cert_validation if skip_cert_validation is not None else self._skip_cert_validation
        skip_http_cert_validation_default = skip_http_cert_validation \
            if skip_http_cert_validation is not None else self._skip_http_cert_validation
        if skip_http_cert_validation_default is None:
            # Opt-in: certificate validation stays on unless the user accepts
            # the local broker's self-signed certificate explicitly.
            skip_http_cert_validation_default = False

        schema_params = {
            vol.Required(CONF_HTTP_ENDPOINT, default=http_endpoint_default): str,
            vol.Required(CONF_OVERRIDE_MQTT_ENDPOINT, default=mqtt_endpoint_default): str,
            vol.Required(CONF_USERNAME, default=username_default): str,
            vol.Required(CONF_PASSWORD, default=password_default): str,
        }

        if requires_mfa:
            schema_params[vol.Required(CONF_MFA_CODE)] = str
        schema_params[vol.Required(CONF_MQTT_SKIP_CERT_VALIDATION, default=skip_cert_validation_default)] = bool
        schema_params[vol.Required(CONF_HTTP_SKIP_CERT_VALIDATION,
                                   default=skip_http_cert_validation_default)] = bool
        return vol.Schema(schema_params)

    def _build_simple_schema(self, username=None, password=None,
                             advanced=False) -> vol.Schema:
        # Optional fields so the form can be submitted with empty values:
        # otherwise the frontend blocks submission and "Advanced settings"
        # can never be reached without a broker address and credentials.
        params = {}
        if self._include_simple_host:
            params[vol.Optional(CONF_BROKER_HOST,
                                default=self._simple_host or "")] = str
            params[vol.Optional(CONF_USE_HTTPS,
                                default=self._simple_use_https)] = bool
        params[vol.Optional(
            CONF_USERNAME,
            default=(username if username is not None else self._username) or "")] = str
        params[vol.Optional(
            CONF_PASSWORD,
            default=(password if password is not None else self._password) or "")] = str
        params[vol.Optional(CONF_ADVANCED, default=advanced)] = bool
        return vol.Schema(params)

    def _broker_description(self) -> str:
        if self._discovered_api:
            return self._discovered_api
        if self._is_reauth:
            return self._http_api or ""
        if self._simple_host:
            scheme = "https" if self._simple_use_https else "http"
            return f"{scheme}://{self._simple_host}"
        return ""

    def _show_simple_form(self, errors=None, username=None, password=None,
                          advanced=False):
        return self.async_show_form(
            step_id="configure_manager",
            data_schema=self._build_simple_schema(
                username=username, password=password, advanced=advanced),
            errors=errors or {},
            description_placeholders={
                "broker": self._broker_description() or "not discovered",
            },
        )

    @staticmethod
    def _sanitize_host(raw: str) -> str:
        """Accept a pasted URL and keep only the host part."""
        host = (raw or "").strip()
        if "://" in host:
            host = host.split("://", 1)[1]
        host = host.split("/", 1)[0]
        if host.startswith("["):  # IPv6 literal
            return host.split("]", 1)[0].lstrip("[")
        if host.count(":") == 1:
            host = host.split(":", 1)[0]
        return host.strip()

    def _simple_selection(self, user_input) -> Tuple[str, str, bool, bool]:
        """Returns endpoint, MQTT endpoint, skip MQTT validation, skip HTTP validation."""
        if self._is_reauth:
            return (
                self._http_api,
                self._mqtt_boker,
                self._skip_cert_validation
                if self._skip_cert_validation is not None else True,
                self._skip_http_cert_validation
                if self._skip_http_cert_validation is not None else False,
            )
        if self._discovered_api and not self._include_simple_host:
            return (self._discovered_api, self._discovered_mqtt,
                    True, self._discovered_https)
        host = self._sanitize_host(user_input.get(CONF_BROKER_HOST))
        use_https = bool(user_input.get(CONF_USE_HTTPS, True))
        scheme = "https" if use_https else "http"
        port = 2004 if use_https else 2003
        return (f"{scheme}://{host}:{port}", f"{host}:2001",
                True, use_https)

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
        self._http_api = data.get(CONF_HTTP_ENDPOINT)
        self._mqtt_boker = data.get(CONF_OVERRIDE_MQTT_ENDPOINT)
        self._username = creds.get("user_email")
        self._password = None
        self._skip_cert_validation = data.get(CONF_MQTT_SKIP_CERT_VALIDATION, True)
        self._skip_http_cert_validation = data.get(CONF_HTTP_SKIP_CERT_VALIDATION, False)

    async def async_step_reauth(self, entry_data=None):
        """Reauthenticate against the existing broker configuration."""
        self._is_reauth = True
        self._load_reauth_defaults()
        self._include_simple_host = False
        return self._show_simple_form()

    async def _resolve_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        _LOGGER.debug("MDNS resolving service type: %s, name: %s", service_type, name)
        info = AsyncServiceInfo(service_type, name)
        await info.async_request(zeroconf, 3000)
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

    async def _probe_broker(self, host: str, port: int, scheme: str) -> bool:
        url = f"{scheme}://{self._url_host(host)}:{port}/ca.crt"
        connector = aiohttp.TCPConnector(ssl=False) if scheme == "https" else None
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=3)) as response:
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
        if not api_infos:
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
            try:
                http_port = int(records.get("http_port") or api_info.port or 2003)
                https_port = int(records.get("https_port") or 0)
            except (TypeError, ValueError):
                continue
            for host in hosts:
                if https_port and await self._probe_broker(host, https_port, "https"):
                    _LOGGER.info("Discovered Meross broker at %s:%d (HTTPS)",
                                 host, https_port)
                    return (host, f"https://{self._url_host(host)}:{https_port}",
                            f"{host}:{mqtt_port}", True)
                if await self._probe_broker(host, http_port, "http"):
                    _LOGGER.info("Discovered Meross broker at %s:%d (HTTP)",
                                 host, http_port)
                    return (host, f"http://{self._url_host(host)}:{http_port}",
                            f"{host}:{mqtt_port}", False)
        _LOGGER.info("Meross mDNS services found but no API endpoint responded.")
        return None

    async def async_step_user(self, user_input=None) -> Dict[str, Any]:
        """Configure the local broker connection."""
        _LOGGER.debug("Starting STEP_USER")
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
            self._simple_host = self._discovered_host
            self._simple_use_https = self._discovered_https
            self._include_simple_host = False
            return self._show_simple_form()

        self._discovered_host = None
        self._discovered_api = None
        self._discovered_mqtt = None
        self._discovered_https = False
        self._simple_host = ""
        self._simple_use_https = True
        self._include_simple_host = True
        return self._show_simple_form(errors={"base": "mdns_lookup_failed"})

    async def async_step_configure_manager(self, user_input=None) -> Dict[str, Any]:
        """Simple setup: only the local login and broker address when needed."""
        if not user_input:
            return self._show_simple_form()

        username = user_input.get(CONF_USERNAME) or None
        password = user_input.get(CONF_PASSWORD) or None
        if self._include_simple_host:
            self._simple_host = self._sanitize_host(
                user_input.get(CONF_BROKER_HOST))
            self._simple_use_https = bool(user_input.get(CONF_USE_HTTPS, True))
        endpoint, mqtt, skip_mqtt, skip_http = self._simple_selection(user_input)
        self._http_api = endpoint
        self._mqtt_boker = mqtt
        self._skip_cert_validation = skip_mqtt
        self._skip_http_cert_validation = skip_http
        self._username = username
        self._password = password

        if user_input.get(CONF_ADVANCED):
            if not self._discovered_api and not self._simple_host:
                # No broker discovered and no address typed yet: keep the
                # explicit endpoint fields empty instead of a malformed URL.
                self._http_api = None
                self._mqtt_boker = None
            return await self.async_step_configure_manager_advanced()

        if self._include_simple_host and not self._simple_host:
            return self._show_simple_form(
                errors={"base": "missing_broker_host"},
                username=username, password=password, advanced=False)
        if not username or not password:
            return self._show_simple_form(
                errors={"base": "missing_credentials"},
                username=username, password=password, advanced=False)

        result = await self.async_step_configure_manager_advanced({
            CONF_HTTP_ENDPOINT: endpoint,
            CONF_OVERRIDE_MQTT_ENDPOINT: mqtt,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_MQTT_SKIP_CERT_VALIDATION: skip_mqtt,
            CONF_HTTP_SKIP_CERT_VALIDATION: skip_http,
        })
        if (isinstance(result, dict)
                and result.get("step_id") == "configure_manager_advanced"
                and result.get("errors")
                and "missing_mfa" not in result.get("errors", {}).values()):
            return self._show_simple_form(
                errors=result.get("errors"), username=username, password=password)
        return result

    async def async_step_configure_manager_advanced(self, user_input=None) -> Dict[str, Any]:
        """Advanced setup: explicit endpoints and TLS options."""
        _LOGGER.debug("Starting CONFIGURE_MANAGER_ADVANCED")
        if not user_input:
            _LOGGER.debug("Empty user_input, showing default prefilled form")
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=self._build_setup_schema(),
                errors={},
            )

        _LOGGER.debug("UserInput was provided: form data will be populated with that")
        http_api_endpoint = user_input.get(CONF_HTTP_ENDPOINT)
        username = user_input.get(CONF_USERNAME)
        password = user_input.get(CONF_PASSWORD)
        mqtt_host = user_input.get(CONF_OVERRIDE_MQTT_ENDPOINT)
        skip_cert_validation = user_input.get(CONF_MQTT_SKIP_CERT_VALIDATION)
        skip_http_cert_validation = user_input.get(CONF_HTTP_SKIP_CERT_VALIDATION)
        if skip_http_cert_validation is None:
            skip_http_cert_validation = False
        mfa_code = user_input.get(CONF_MFA_CODE)

        # The self-signed local certificate is only accepted when the user
        # opted in; this must be in place before the login test below.
        set_http_cert_validation(skip_http_cert_validation)

        data_schema = self._build_setup_schema(
            http_endpoint=http_api_endpoint,
            username=username,
            password=password,
            override_mqtt_endpoint=mqtt_host,
            skip_http_cert_validation=skip_http_cert_validation,
            requires_mfa=mfa_code is not None
        )

        # Check if we have everything we need
        if username is None or password is None or http_api_endpoint is None:
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "missing_credentials"},
            )

        # Check the base-url is valid
        match = HTTP_API_RE.fullmatch(http_api_endpoint)

        if match is None:
            _LOGGER.error("Invalid Meross HTTTP API endpoint: %s", http_api_endpoint)
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "invalid_http_endpoint"}
            )
        else:
            _LOGGER.debug("Meross HTTP API endpoint looks good: %s.", http_api_endpoint)

        schema, domain, colonport, port = match.groups()
        if schema is None:
            _LOGGER.warning("No schema specified, assuming http")
            http_api_endpoint = "http://" + http_api_endpoint

        # Test the connection to the Meross Cloud.
        try:
            creds = await self._test_authorization(
                api_base_url=http_api_endpoint, username=username, password=password, mfa_code=mfa_code
            )
            _LOGGER.info("HTTP API successful tested against %s.", http_api_endpoint)
        except MissingMFA as ex:
            data_schema = self._build_setup_schema(
                http_endpoint=http_api_endpoint,
                username=username,
                password=password,
                override_mqtt_endpoint=mqtt_host,
                skip_http_cert_validation=skip_http_cert_validation,
                requires_mfa=True
            )
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "missing_mfa"}
            )
        except (BadLoginException, UnauthorizedException) as ex:
            _LOGGER.error("Unable to connect to Meross HTTP api: %s", str(ex))
            _LOGGER.debug("Passing data_schema: %s", str(data_schema))
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "invalid_credentials"}
            )
        except (UnauthorizedException, ConnectTimeout, HTTPError) as ex:
            _LOGGER.error("Unable to connect to Meross HTTP api: %s", str(ex))
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "connection_error"}
            )
        except ClientConnectorSSLError as ex:
            _LOGGER.error("Unable to connect to Meross HTTP api: %s", str(ex))
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "api_invalid_ssl_code"}
            )
        except ClientConnectorError as ex:
            _LOGGER.error("Connection ERROR to HTTP api: %s", str(ex))
            if isinstance(ex.os_error, ConnectionRefusedError):
                return self.async_show_form(
                    step_id="configure_manager_advanced",
                    data_schema=data_schema,
                    errors={"base": "api_connection_refused"}
                )
            else:
                return self.async_show_form(
                    step_id="configure_manager_advanced",
                    data_schema=data_schema,
                    errors={"base": "client_connection_error"}
                )
        except Exception as ex:
            _LOGGER.exception("Unable to connect to Meross HTTP api, ex: %s", str(ex))
            return self.async_show_form(
                step_id="configure_manager_advanced",
                data_schema=data_schema,
                errors={"base": "unknown_error"}
            )

        # TODO: Test MQTT connection?
        data = {
            CONF_HTTP_ENDPOINT: http_api_endpoint,
            CONF_OVERRIDE_MQTT_ENDPOINT: mqtt_host,
            CONF_STORED_CREDS: {
                "domain": creds.domain,
                "mqtt_domain": creds.mqtt_domain,
                "token": creds.token,
                "key": creds.key,
                "user_id": creds.user_id,
                "user_email": creds.user_email,
                "issued_on": creds.issued_on.isoformat()
            },
            CONF_MQTT_SKIP_CERT_VALIDATION: skip_cert_validation,
            CONF_HTTP_SKIP_CERT_VALIDATION: skip_http_cert_validation
        }

        if self._is_reauth:
            entry = self._reauth_entry()
            self.hass.config_entries.async_update_entry(
                entry, data=data, title=http_api_endpoint)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        entry = await self.async_set_unique_id(http_api_endpoint)

        # If this is a re-auth for an existing entry, just update the entry configuration.
        if entry is not None:
            self._abort_if_unique_id_configured(updates=data, reload_on_update=True)  # No more needed
            await self.hass.config_entries.async_reload(entry.entry_id)

        # Otherwise create a new entry from scratch
        else:
            return self.async_create_entry(
                title=user_input[CONF_HTTP_ENDPOINT],
                data=data
            )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MerossOptionsFlowHandler()

    @staticmethod
    async def _test_authorization(
            api_base_url: str, username: str, password: str, mfa_code: str = None
    ) -> MerossCloudCreds:
        client = await MerossHttpClient.async_from_user_password(
            api_base_url=api_base_url, email=username, password=password, mfa_code=mfa_code
        )
        return client.cloud_credentials

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
            return self.async_create_entry(
                title="",
                data={k: v for k, v in user_input.items() if v not in (None, "")},
            )

        saved_options = {}
        if self.config_entry is not None:
            saved_options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_OPT_CUSTOM_USER_AGENT,
                             default=saved_options.get(CONF_OPT_CUSTOM_USER_AGENT, DEFAULT_USER_AGENT)): str,
                vol.Required(CONF_OPT_LAN,
                             default=saved_options.get(CONF_OPT_LAN, CONF_OPT_LAN_MQTT_ONLY)): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": CONF_OPT_LAN_MQTT_ONLY,
                             "label": "Do not rely on local HTTP communication at all, just use the MQTT broker"},
                            {"value": CONF_OPT_LAN_HTTP_FIRST,
                             "label": "Attempt local HTTP communication first and fall-back to MQTT broker"},
                            {"value": CONF_OPT_LAN_HTTP_FIRST_ONLY_GET,
                             "label": "Attempt local HTTP communication first only for GET commands, fall-back to MQTT broker"}
                        ], mode=SelectSelectorMode.LIST)
                )
            })
        )
