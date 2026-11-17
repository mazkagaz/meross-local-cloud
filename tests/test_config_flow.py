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
    CONF_BROKER_CA,
    CONF_HTTP_ENDPOINT,
    CONF_HTTP_SKIP_CERT_VALIDATION,
    CONF_MQTT_SKIP_CERT_VALIDATION,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DOMAIN,
)
from custom_components.meross_cloud.config_flow import MerossFlowHandler


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_initial_flow_opens_local_configuration(hass, monkeypatch):
    async def fake_discover(self):
        return None, None

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

    async def fake_fetch_ca(endpoint):
        return "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----"

    monkeypatch.setattr(
        MerossFlowHandler, "_test_authorization", staticmethod(fake_test_authorization)
    )
    monkeypatch.setattr(
        "custom_components.meross_cloud.config_flow.async_fetch_broker_ca",
        fake_fetch_ca,
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
    assert defaults[CONF_HTTP_ENDPOINT] == endpoint
    assert defaults[CONF_OVERRIDE_MQTT_ENDPOINT] == mqtt_endpoint
    assert defaults[CONF_USERNAME] == "local-user"
    assert defaults[CONF_MQTT_SKIP_CERT_VALIDATION] is True
    assert defaults[CONF_HTTP_SKIP_CERT_VALIDATION] is False

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HTTP_ENDPOINT: endpoint,
            CONF_OVERRIDE_MQTT_ENDPOINT: mqtt_endpoint,
            CONF_USERNAME: "local-user",
            CONF_PASSWORD: "secret",
            CONF_MQTT_SKIP_CERT_VALIDATION: True,
            CONF_HTTP_SKIP_CERT_VALIDATION: False,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data[CONF_STORED_CREDS]["token"] == "new-token"
    assert entries[0].data[CONF_BROKER_CA].startswith("-----BEGIN CERTIFICATE-----")
    assert entries[0].unique_id == endpoint
    assert entries[0].title == endpoint


async def test_options_flow_loads(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="options-test")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
