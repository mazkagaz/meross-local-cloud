"""Functional: a CA change is visible but never blocks the setup."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.meross_local_cloud as integration
from custom_components.meross_local_cloud import repairs
from custom_components.meross_local_cloud.common import (
    CONF_CA_FINGERPRINT,
    CONF_HTTP_ENDPOINT,
    CONF_STORED_CREDS,
    DOMAIN,
)
from homeassistant.helpers import issue_registry as ir


def _credentials(endpoint):
    return {
        "token": "token",
        "key": "key",
        "user_id": "1",
        "user_email": "local",
        "domain": endpoint,
        "mqtt_domain": "",
        "issued_on": "2026-11-28T10:00:00+00:00",
    }


class _Coordinator:
    def __init__(self, **kwargs):
        self.data = {}
        self.credentials = SimpleNamespace()
        self.http_api_endpoint = kwargs["http_api_endpoint"]
        self.http_ssl_context = kwargs["http_ssl_context"]
        self.user_agent = "test"

    async def initial_setup(self):
        return None

    def async_add_listener(self, callback):
        return lambda: None

    async def async_stop(self):
        return None


class _Adapter:
    def __init__(self, hass, coordinator):
        self.state = "connected"
        self.entities_only = False

    def start_background(self, hass):
        return None

    def async_update_devices(self, devices):
        return None

    def unknown_devices(self, devices):
        return []

    async def async_stop(self):
        return None


async def _setup(hass, monkeypatch, ca_pem, ca_change):
    endpoint = "https://10.0.0.5:2004"
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_HTTP_ENDPOINT: endpoint,
        CONF_STORED_CREDS: _credentials(endpoint),
        CONF_CA_FINGERPRINT: "old-fingerprint",
    })
    entry.add_to_hass(hass)

    async def prepare(*args, **kwargs):
        return (ca_pem, "new-fingerprint", object(), True, True, {}, ca_change)

    monkeypatch.setattr(integration, "_async_prepare_tls", prepare)
    monkeypatch.setattr(integration, "MerossCoordinator", _Coordinator)
    monkeypatch.setattr(integration, "BrokerProfileAdapter", _Adapter)
    monkeypatch.setattr(
        integration, "RollerShutterConfigCache", lambda *a, **kw: object())
    monkeypatch.setattr(
        integration, "async_prune_stale_profile_entities", Mock())
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_unload", AsyncMock(return_value=True))

    assert await integration.async_setup_entry(hass, entry) is True
    return entry


async def test_ca_change_is_non_blocking_and_creates_a_repair(
        hass, monkeypatch, ca_pem):
    change = {
        "old_fingerprint": "old-fingerprint",
        "new_fingerprint": "new-fingerprint",
        "subject": "CN=New CA",
        "issuer": "CN=New CA",
        "valid_until": "2036-01-01T00:00:00+00:00",
        "endpoint": "https://10.0.0.5:2004",
        "detected_at": "2026-11-28T10:00:00+00:00",
    }

    entry = await _setup(hass, monkeypatch, ca_pem, change)

    issue_id = repairs.ca_change_issue_id(entry.entry_id, "new-fingerprint")
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["old_fingerprint"] == "old-fingerprint"
    assert issue.translation_placeholders["new_fingerprint"] == "new-fingerprint"
    assert entry.data[CONF_CA_FINGERPRINT] == "new-fingerprint"
    assert entry.disabled_by is None


async def test_unchanged_ca_does_not_create_a_repair(
        hass, monkeypatch, ca_pem):
    entry = await _setup(hass, monkeypatch, ca_pem, None)

    assert not [
        item for item in ir.async_get(hass).issues.values()
        if item.domain == DOMAIN and item.issue_id.startswith(
            repairs.CA_CHANGE_ISSUE_PREFIX)
    ]


async def test_a_warning_failure_does_not_block_setup(
        hass, monkeypatch, ca_pem):
    change = {
        "old_fingerprint": "old-fingerprint",
        "new_fingerprint": "new-fingerprint",
        "subject": "CN=New CA",
        "issuer": "CN=New CA",
        "valid_until": "2036-01-01T00:00:00+00:00",
        "endpoint": "https://10.0.0.5:2004",
        "detected_at": "2026-11-28T10:00:00+00:00",
    }
    monkeypatch.setattr(
        integration, "async_create_ca_change_issue",
        Mock(side_effect=RuntimeError("repair registry unavailable")))

    entry = await _setup(hass, monkeypatch, ca_pem, change)

    assert entry.disabled_by is None
