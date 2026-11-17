from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import voluptuous_serialize

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud.common import (
    CONF_ADVANCED,
    CONF_BROKER_HOST,
    CONF_HTTP_ENDPOINT,
    CONF_HTTP_SKIP_CERT_VALIDATION,
    CONF_MQTT_SKIP_CERT_VALIDATION,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    CONF_USE_HTTPS,
    DOMAIN,
)
from custom_components.meross_cloud.config_flow import MerossFlowHandler
from custom_components.meross_cloud.version import MEROSS_INTEGRATION_VERSION


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_initial_flow_opens_local_configuration(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"


async def test_initial_flow_survives_discovery_failure(hass, monkeypatch):
    async def broken_discover(self):
        raise RuntimeError("mDNS unavailable")

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", broken_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"
    assert result["errors"]["base"] == "mdns_lookup_failed"


async def test_reauth_reuses_existing_entry(hass, monkeypatch):
    endpoint = "http://10.0.0.5:2003"
    mqtt_endpoint = "10.0.0.5:2001"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=endpoint,
        unique_id=endpoint,
        data={
            CONF_HTTP_ENDPOINT: endpoint,
            CONF_OVERRIDE_MQTT_ENDPOINT: mqtt_endpoint,
            CONF_STORED_CREDS: {
                "domain": endpoint,
                "mqtt_domain": "",
                "token": "old-token",
                "key": "key",
                "user_id": "1",
                "user_email": "local-user",
                "issued_on": datetime.now().isoformat(),
            },
            CONF_MQTT_SKIP_CERT_VALIDATION: True,
            CONF_HTTP_SKIP_CERT_VALIDATION: False,
        },
    )
    entry.add_to_hass(hass)

    async def fake_test_authorization(api_base_url, username, password, mfa_code=None):
        assert password == "secret"
        return SimpleNamespace(
            domain=api_base_url,
            mqtt_domain="",
            token="new-token",
            key="key",
            user_id="1",
            user_email=username,
            issued_on=datetime.now(),
        )

    monkeypatch.setattr(
        MerossFlowHandler, "_test_authorization", staticmethod(fake_test_authorization)
    )
    monkeypatch.setattr(type(hass.config_entries), "async_reload", AsyncMock())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"

    defaults = {
        str(marker.schema): marker.default()
        for marker in result["data_schema"].schema
    }
    assert defaults[CONF_USERNAME] == "local-user"
    assert defaults[CONF_ADVANCED] == "simple"
    assert CONF_HTTP_ENDPOINT not in defaults
    assert CONF_OVERRIDE_MQTT_ENDPOINT not in defaults

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: "simple",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data[CONF_STORED_CREDS]["token"] == "new-token"
    assert entries[0].data[CONF_HTTP_ENDPOINT] == endpoint
    assert entries[0].data[CONF_OVERRIDE_MQTT_ENDPOINT] == mqtt_endpoint
    assert entries[0].data[CONF_MQTT_SKIP_CERT_VALIDATION] is True
    assert entries[0].data[CONF_HTTP_SKIP_CERT_VALIDATION] is False
    assert entries[0].unique_id == endpoint
    assert entries[0].title == endpoint


def _creds(endpoint, username, token="new-token"):
    return SimpleNamespace(
        domain=endpoint,
        mqtt_domain="",
        token=token,
        key="key",
        user_id="1",
        user_email=username,
        issued_on=datetime.now(),
    )


async def test_discovery_prefills_simple_form_and_creates_entry(hass, monkeypatch):
    async def fake_discover(self):
        return ("10.0.0.5", "https://10.0.0.5:2004", "10.0.0.5:2001", True)

    async def fake_test_authorization(api_base_url, username, password, mfa_code=None):
        return _creds(api_base_url, username)

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)
    monkeypatch.setattr(
        MerossFlowHandler, "_test_authorization", staticmethod(fake_test_authorization)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"
    defaults = {
        str(marker.schema): marker.default()
        for marker in result["data_schema"].schema
    }
    assert CONF_BROKER_HOST not in defaults
    assert defaults[CONF_ADVANCED] == "simple"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: "simple",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_HTTP_ENDPOINT] == "https://10.0.0.5:2004"
    assert data[CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.5:2001"
    assert data[CONF_MQTT_SKIP_CERT_VALIDATION] is True
    assert data[CONF_HTTP_SKIP_CERT_VALIDATION] is True


async def test_manual_address_is_used_when_discovery_fails(hass, monkeypatch):
    async def fake_discover(self):
        return None

    async def fake_test_authorization(api_base_url, username, password, mfa_code=None):
        return _creds(api_base_url, username)

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)
    monkeypatch.setattr(
        MerossFlowHandler, "_test_authorization", staticmethod(fake_test_authorization)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "configure_manager"
    assert result["errors"]["base"] == "mdns_lookup_failed"
    defaults = {
        str(marker.schema): marker.default()
        for marker in result["data_schema"].schema
    }
    assert defaults[CONF_BROKER_HOST] == ""
    assert defaults[CONF_USE_HTTPS] is True

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_BROKER_HOST: "10.0.0.6",
            CONF_USE_HTTPS: False,
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: "simple",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_HTTP_ENDPOINT] == "http://10.0.0.6:2003"
    assert data[CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.6:2001"
    assert data[CONF_MQTT_SKIP_CERT_VALIDATION] is True
    assert data[CONF_HTTP_SKIP_CERT_VALIDATION] is False


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("10.0.0.6", "10.0.0.6"),
        (" homeassistant.local ", "homeassistant.local"),
        ("http://10.0.0.6:2003", "10.0.0.6"),
        ("https://homeassistant.local/ca.crt", "homeassistant.local"),
        ("10.0.0.6:2004", "10.0.0.6"),
        ("[fd00::1]", "fd00::1"),
        ("", ""),
        (None, ""),
    ],
)
def test_sanitize_host(raw, expected):
    assert MerossFlowHandler._sanitize_host(raw) == expected


async def test_manual_address_accepts_pasted_url(hass, monkeypatch):
    async def fake_discover(self):
        return None

    async def fake_test_authorization(api_base_url, username, password, mfa_code=None):
        return _creds(api_base_url, username)

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)
    monkeypatch.setattr(
        MerossFlowHandler, "_test_authorization", staticmethod(fake_test_authorization)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_BROKER_HOST: "http://10.0.0.6:2003/ca.crt",
            CONF_USE_HTTPS: False,
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: "simple",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HTTP_ENDPOINT] == "http://10.0.0.6:2003"
    assert result["data"][CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.6:2001"


async def test_advanced_toggle_opens_full_form_without_discovery(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "configure_manager"
    assert result["errors"]["base"] == "mdns_lookup_failed"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_BROKER_HOST: "10.0.0.6",
            CONF_USE_HTTPS: True,
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: "advanced",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager_advanced"


async def test_setup_mode_selector_exposes_running_version(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    serialized = voluptuous_serialize.convert(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    advanced = next(
        item for item in serialized if item["name"] == CONF_ADVANCED
    )
    options = advanced["selector"]["select"]["options"]
    assert {option["value"] for option in options} == {"simple", "advanced"}
    assert any(
        MEROSS_INTEGRATION_VERSION in option["label"] for option in options
    )


async def test_advanced_toggle_works_without_any_value(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "configure_manager"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ADVANCED: "advanced"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager_advanced"
    defaults = {
        str(marker.schema): marker.default()
        for marker in result["data_schema"].schema
    }
    assert defaults[CONF_HTTP_ENDPOINT] is None
    assert defaults[CONF_OVERRIDE_MQTT_ENDPOINT] is None


async def test_empty_simple_form_reports_missing_values(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ADVANCED: "simple"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"
    assert result["errors"]["base"] == "missing_broker_host"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_BROKER_HOST: "10.0.0.6",
            CONF_USE_HTTPS: True,
            CONF_ADVANCED: "simple",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "missing_credentials"


async def test_advanced_toggle_opens_full_form(hass, monkeypatch):
    async def fake_discover(self):
        return ("10.0.0.5", "https://10.0.0.5:2004", "10.0.0.5:2001", True)

    async def fake_test_authorization(api_base_url, username, password, mfa_code=None):
        return _creds(api_base_url, username)

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)
    monkeypatch.setattr(
        MerossFlowHandler, "_test_authorization", staticmethod(fake_test_authorization)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: "advanced",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager_advanced"
    defaults = {
        str(marker.schema): marker.default()
        for marker in result["data_schema"].schema
    }
    assert defaults[CONF_HTTP_ENDPOINT] == "https://10.0.0.5:2004"
    assert defaults[CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.5:2001"
    assert defaults[CONF_USERNAME] == "local-user"
    assert defaults[CONF_MQTT_SKIP_CERT_VALIDATION] is True
    assert defaults[CONF_HTTP_SKIP_CERT_VALIDATION] is True

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HTTP_ENDPOINT: "https://10.0.0.5:2004",
            CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.5:2001",
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_MQTT_SKIP_CERT_VALIDATION: True,
            CONF_HTTP_SKIP_CERT_VALIDATION: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_loads(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="options-test")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
