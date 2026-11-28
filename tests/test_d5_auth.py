"""D5-b: the coordinator authenticates through the broker HTTP client."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.meross_local_cloud as integration
from custom_components.meross_local_cloud import MerossCoordinator
from custom_components.meross_local_cloud.broker_devices import BrokerDeviceInfo
from custom_components.meross_local_cloud.broker_http import (
    BrokerCredentials,
    BrokerHttpError,
    BrokerTokenError,
)
from custom_components.meross_local_cloud.common import (
    CONF_CA_FINGERPRINT,
    CONF_CA_PEM,
    CONF_HTTP_ENDPOINT,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DOMAIN,
)

ENDPOINT = "https://10.0.0.5:2004"


def credentials(domain=ENDPOINT):
    return BrokerCredentials(
        token="token",
        key="key",
        user_id="1",
        user_email="local",
        domain=domain,
        mqtt_domain="",
        issued_on=datetime.now(timezone.utc),
    )


def make_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HTTP_ENDPOINT: ENDPOINT,
            CONF_STORED_CREDS: credentials().as_dict(),
        },
    )


def make_coordinator(hass, entry):
    return MerossCoordinator(
        hass=hass,
        config_entry=entry,
        http_api_endpoint=ENDPOINT,
        creds=credentials(),
        mqtt_override_address=None,
        update_interval=None,
        ua_header="MerossHA/test",
        ca_pem=None,
        ca_check_hostname=False,
    )


async def test_initial_setup_uses_broker_http_without_a_manager(
        hass, ca_pem, monkeypatch):
    entry = make_entry()
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {}
    coordinator = make_coordinator(hass, entry)
    coordinator._ca_pem = ca_pem
    monkeypatch.setattr(
        integration, "BrokerHttpClient", lambda *args, **kwargs: object())
    devices = [BrokerDeviceInfo(
        uuid="u1", name="volet", device_type="mrs100", online=True)]
    monkeypatch.setattr(
        integration, "async_list_devices", AsyncMock(return_value=devices))

    await coordinator.initial_setup()

    assert coordinator.data == {"u1": devices[0]}
    assert not hasattr(coordinator, "_manager")
    assert coordinator.credentials.token == "token"


async def test_invalid_token_aborts_setup(hass, ca_pem, monkeypatch):
    entry = make_entry()
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {}
    coordinator = make_coordinator(hass, entry)
    coordinator._ca_pem = ca_pem
    monkeypatch.setattr(
        integration, "BrokerHttpClient", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        integration, "async_list_devices",
        AsyncMock(side_effect=BrokerTokenError("token_error")))

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.initial_setup()


async def test_broker_outage_retries_setup(hass, ca_pem, monkeypatch):
    entry = make_entry()
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {}
    coordinator = make_coordinator(hass, entry)
    coordinator._ca_pem = ca_pem
    monkeypatch.setattr(
        integration, "BrokerHttpClient", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        integration, "async_list_devices",
        AsyncMock(side_effect=BrokerHttpError("HTTP 503", status=503)))

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.initial_setup()


async def test_stored_domain_is_aligned_with_the_endpoint(
        hass, ca_pem, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={
        **dict(make_entry().data),
        CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.5:2001",
        CONF_CA_PEM: "stored-ca",
        CONF_CA_FINGERPRINT: "stored-fingerprint",
    })
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {}
    stale = credentials("https://old-host:2004")
    coordinator = MerossCoordinator(
        hass=hass,
        config_entry=entry,
        http_api_endpoint=ENDPOINT,
        creds=stale,
        mqtt_override_address=None,
        update_interval=None,
        ua_header="MerossHA/test",
        ca_pem=ca_pem,
        ca_check_hostname=False,
    )
    monkeypatch.setattr(
        integration, "BrokerHttpClient", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        integration, "async_list_devices", AsyncMock(return_value=[]))

    await coordinator.initial_setup()

    assert coordinator.credentials.domain == ENDPOINT
    assert entry.data[CONF_HTTP_ENDPOINT] == ENDPOINT
    assert entry.data[CONF_STORED_CREDS]["domain"] == ENDPOINT
    assert entry.data[CONF_OVERRIDE_MQTT_ENDPOINT] == "10.0.0.5:2001"
    assert entry.data[CONF_CA_PEM] == "stored-ca"
    assert entry.data[CONF_CA_FINGERPRINT] == "stored-fingerprint"


async def test_http_client_uses_the_http_ssl_context(hass, ca_pem, monkeypatch):
    entry = make_entry()
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {}
    seen = {}

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            seen["ssl"] = args[2]

    coordinator = make_coordinator(hass, entry)
    coordinator._ca_pem = ca_pem
    coordinator._http_ssl_context = object()
    monkeypatch.setattr(integration, "BrokerHttpClient", FakeHttpClient)
    monkeypatch.setattr(
        integration, "async_list_devices", AsyncMock(return_value=[]))

    await coordinator.initial_setup()

    assert seen["ssl"] is coordinator._http_ssl_context
