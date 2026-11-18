from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud.common import (
    CONF_CA_PEM,
    CONF_HTTP_ENDPOINT,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DEVICE_LIST_COORDINATOR,
    DOMAIN,
    MANAGER,
)
from custom_components.meross_cloud.diagnostics import (
    async_get_config_entry_diagnostics,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_diagnostics_redacts_secrets(hass, ca_pem):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HTTP_ENDPOINT: "https://10.0.0.5:2004",
            CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.5:2001",
            CONF_CA_PEM: ca_pem,
            CONF_STORED_CREDS: {
                "token": "secret-token",
                "key": "secret-key",
                "password": "secret-password",
                "user_email": "local-user",
                "user_id": "1",
            },
        },
    )
    entry.add_to_hass(hass)

    device = SimpleNamespace(
        name="volet",
        uuid="uuid-1",
        type="mrs100",
        firmware_version="7.6.20",
        hardware_version="7.0.0",
        online_status=SimpleNamespace(name="ONLINE"),
    )
    manager = SimpleNamespace(find_devices=lambda: [device])
    coordinator = SimpleNamespace(
        _mqtt_ssl_context_verified=object())
    hass.data[DOMAIN] = {
        MANAGER: manager,
        DEVICE_LIST_COORDINATOR: coordinator,
        "TLS_INFO": {
            "http_verified": True,
            "mqtt_verified": True,
            "http_host": "10.0.0.5",
            "mqtt_host": "10.0.0.5",
            "http_check_hostname": True,
            "mqtt_check_hostname": True,
            "server": {
                "subject": "CN=Broker",
                "hostnames": ["10.0.0.5", "homeassistant.local"],
            },
        },
    }

    result = await async_get_config_entry_diagnostics(hass, entry)

    creds = result["entry"]["stored_credentials"]
    assert creds["token"] == "**REDACTED**"
    assert creds["key"] == "**REDACTED**"
    assert creds["password"] == "**REDACTED**"
    assert creds["user_email"] == "local-user"

    assert result["tls"]["ca"]["valid_ca"] is True
    assert len(result["tls"]["ca"]["fingerprint"]) == 64
    assert result["tls"]["server"]["hostnames"] == [
        "10.0.0.5", "homeassistant.local"]
    assert result["tls"]["http"]["check_hostname"] is True
    assert result["tls"]["mqtt"]["verified_context"] is True
    assert result["runtime"]["manager_started"] is True
    assert result["runtime"]["devices"][0]["uuid"] == "uuid-1"
