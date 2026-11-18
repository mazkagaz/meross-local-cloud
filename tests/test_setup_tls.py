import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud import _async_prepare_tls
from custom_components.meross_cloud.common import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_prepare_tls_evaluates_sans(hass, monkeypatch, ca_pem, server_pem):
    async def fake_fetch(endpoint):
        return ca_pem

    def fake_server(host, port):
        return server_pem

    monkeypatch.setattr(
        "custom_components.meross_cloud.async_fetch_ca", fake_fetch)
    monkeypatch.setattr(
        "custom_components.meross_cloud.fetch_server_certificate",
        fake_server)

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    (pem, fingerprint, context, http_check, mqtt_check,
     server_info) = await _async_prepare_tls(
        hass, entry, "https://10.0.0.5:2004", "10.0.0.5")

    assert pem == ca_pem
    assert fingerprint is not None
    assert context is not None
    assert http_check is True
    assert mqtt_check is True
    assert "10.0.0.5" in server_info["hostnames"]


async def test_prepare_tls_requires_a_valid_ca(hass, monkeypatch):
    async def fake_fetch(endpoint):
        return None

    monkeypatch.setattr(
        "custom_components.meross_cloud.async_fetch_ca", fake_fetch)

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    with pytest.raises(Exception):
        await _async_prepare_tls(
            hass, entry, "https://10.0.0.5:2004", "10.0.0.5")
