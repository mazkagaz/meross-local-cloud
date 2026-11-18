from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud.common import (
    CONF_ADVANCED,
    CONF_CA_PEM,
    CONF_HTTP_ENDPOINT,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DOMAIN,
)
from custom_components.meross_cloud.config_flow import MerossFlowHandler


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fake_ca(monkeypatch, ca_pem):
    async def _fetch(endpoint):
        return ca_pem

    monkeypatch.setattr(
        "custom_components.meross_cloud.config_flow.async_fetch_ca", _fetch)
    return ca_pem


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


async def test_discovery_failure_opens_advanced_form(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager_advanced"
    assert result["errors"]["base"] == "mdns_lookup_failed"
    defaults = {
        str(marker.schema): marker.default()
        for marker in result["data_schema"].schema
    }
    assert defaults[CONF_HTTP_ENDPOINT] is None
    assert defaults[CONF_OVERRIDE_MQTT_ENDPOINT] is None


async def test_initial_flow_survives_discovery_exception(hass, monkeypatch):
    async def broken_discover(self):
        raise RuntimeError("mDNS unavailable")

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", broken_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager_advanced"
    assert result["errors"]["base"] == "mdns_lookup_failed"


async def test_manual_settings_create_entry_when_discovery_fails(
        hass, monkeypatch, fake_ca):
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
            CONF_HTTP_ENDPOINT: "https://10.0.0.6:2004",
            CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.6:2001",
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_HTTP_ENDPOINT] == "https://10.0.0.6:2004"
    assert data[CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.6:2001"
    assert data[CONF_CA_PEM] == fake_ca


async def test_plain_http_is_rejected(hass, monkeypatch):
    async def fake_discover(self):
        return None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HTTP_ENDPOINT: "http://10.0.0.6:2003",
            CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.6:2001",
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager_advanced"
    assert result["errors"]["base"] == "https_required"


async def test_reauth_reuses_existing_entry(hass, monkeypatch):
    endpoint = "https://10.0.0.5:2004"
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
        },
    )
    entry.add_to_hass(hass)

    async def fake_test_authorization(api_base_url, username, password, mfa_code=None):
        assert password == "secret"
        return _creds(api_base_url, username, token="new-token")

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
    assert defaults[CONF_ADVANCED] is False
    assert CONF_HTTP_ENDPOINT not in defaults
    assert CONF_OVERRIDE_MQTT_ENDPOINT not in defaults

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: False,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data[CONF_STORED_CREDS]["token"] == "new-token"
    assert entries[0].data[CONF_HTTP_ENDPOINT] == endpoint
    assert entries[0].data[CONF_OVERRIDE_MQTT_ENDPOINT] == mqtt_endpoint
    assert entries[0].unique_id == endpoint
    assert entries[0].title == endpoint


async def test_discovery_prefills_simple_form_and_creates_entry(
        hass, monkeypatch, fake_ca):
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
    assert defaults[CONF_ADVANCED] is False

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_ADVANCED: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_HTTP_ENDPOINT] == "https://10.0.0.5:2004"
    assert data[CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.5:2001"
    assert data[CONF_CA_PEM] == fake_ca


async def test_discovered_simple_form_requires_credentials(hass, monkeypatch):
    async def fake_discover(self):
        return ("10.0.0.5", "https://10.0.0.5:2004", "10.0.0.5:2001", True)

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ADVANCED: False},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"
    assert result["errors"]["base"] == "missing_credentials"


async def test_advanced_toggle_opens_full_form(hass, monkeypatch, fake_ca):
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
            CONF_ADVANCED: True,
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

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HTTP_ENDPOINT: "https://10.0.0.5:2004",
            CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.5:2001",
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_loads(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="options-test")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
