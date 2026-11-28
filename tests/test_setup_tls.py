import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_local_cloud import _async_prepare_tls
from custom_components.meross_local_cloud.common import (
    CONF_CA_FINGERPRINT,
    DOMAIN,
)
from custom_components.meross_local_cloud.tls import fingerprint, parse_certificate


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_prepare_tls_evaluates_sans(hass, monkeypatch, ca_pem, server_pem):
    async def fake_fetch(endpoint):
        return ca_pem

    def fake_server(host, port):
        return server_pem

    monkeypatch.setattr(
        "custom_components.meross_local_cloud.async_fetch_ca", fake_fetch)
    monkeypatch.setattr(
        "custom_components.meross_local_cloud.fetch_server_certificate",
        fake_server)

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    (pem, ca_fingerprint, context, http_check, mqtt_check,
     server_info, ca_change) = await _async_prepare_tls(
        hass, entry, "https://10.0.0.5:2004", "10.0.0.5")

    assert pem == ca_pem
    assert ca_fingerprint is not None
    assert ca_change is None
    assert context is not None
    assert http_check is True
    assert mqtt_check is True
    assert "10.0.0.5" in server_info["hostnames"]


async def test_prepare_tls_requires_a_valid_ca(hass, monkeypatch):
    async def fake_fetch(endpoint):
        return None

    monkeypatch.setattr(
        "custom_components.meross_local_cloud.async_fetch_ca", fake_fetch)

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    with pytest.raises(Exception):
        await _async_prepare_tls(
            hass, entry, "https://10.0.0.5:2004", "10.0.0.5")


async def test_prepare_tls_reports_a_changed_ca(hass, monkeypatch, ca_pem, server_pem):
    async def fake_fetch(endpoint):
        return ca_pem

    monkeypatch.setattr(
        "custom_components.meross_local_cloud.async_fetch_ca", fake_fetch)
    monkeypatch.setattr(
        "custom_components.meross_local_cloud.fetch_server_certificate",
        lambda host, port: server_pem)

    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_CA_FINGERPRINT: "AA:BB:CC",
    })
    entry.add_to_hass(hass)

    (_, ca_fingerprint, _, _, _, _, ca_change) = await _async_prepare_tls(
        hass, entry, "https://10.0.0.5:2004", "10.0.0.5")

    assert ca_fingerprint == fingerprint(parse_certificate(ca_pem))
    assert ca_change["old_fingerprint"] == "AA:BB:CC"
    assert ca_change["new_fingerprint"] == ca_fingerprint
    assert ca_change["endpoint"] == "https://10.0.0.5:2004"
    assert ca_change["subject"] == "CN=Test CA"


async def test_prepare_tls_does_not_report_the_same_ca(hass, monkeypatch, ca_pem, server_pem):
    async def fake_fetch(endpoint):
        return ca_pem

    monkeypatch.setattr(
        "custom_components.meross_local_cloud.async_fetch_ca", fake_fetch)
    monkeypatch.setattr(
        "custom_components.meross_local_cloud.fetch_server_certificate",
        lambda host, port: server_pem)

    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_CA_FINGERPRINT: fingerprint(parse_certificate(ca_pem)),
    })
    entry.add_to_hass(hass)

    (_, _, _, _, _, _, ca_change) = await _async_prepare_tls(
        hass, entry, "https://10.0.0.5:2004", "10.0.0.5")

    assert ca_change is None
