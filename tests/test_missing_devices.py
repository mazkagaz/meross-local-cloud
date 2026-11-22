from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_local_cloud.common import DOMAIN
from custom_components.meross_local_cloud.missing_devices import (
    MISSING_DEVICE_RETENTION,
    MissingDeviceTracker,
    issue_id,
)


def _device(uuid, name):
    return SimpleNamespace(uuid=uuid, dev_name=name)


def _issue(hass, uuid):
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id(uuid))


def _freeze(monkeypatch, start):
    clock = {"now": start}
    monkeypatch.setattr(
        "custom_components.meross_local_cloud.missing_devices.dt_util.utcnow",
        lambda: clock["now"])
    return clock


async def test_issue_is_created_only_after_48_hours(hass, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = _freeze(monkeypatch, start)
    tracker = MissingDeviceTracker(hass, "entry")

    await tracker.async_update([_device("u1", "Volet")])
    assert _issue(hass, "u1") is None

    await tracker.async_update([])
    assert _issue(hass, "u1") is None

    clock["now"] = start + MISSING_DEVICE_RETENTION - timedelta(minutes=1)
    await tracker.async_update([])
    assert _issue(hass, "u1") is None

    clock["now"] = start + MISSING_DEVICE_RETENTION
    await tracker.async_update([])
    issue = _issue(hass, "u1")
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.translation_key == "remove_missing_device"
    assert issue.translation_placeholders["name"] == "Volet"
    assert issue.data["uuid"] == "u1"


async def test_returning_device_clears_issue(hass, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = _freeze(monkeypatch, start)
    tracker = MissingDeviceTracker(hass, "entry")

    await tracker.async_update([_device("u1", "Volet")])
    await tracker.async_update([])
    clock["now"] = start + MISSING_DEVICE_RETENTION
    await tracker.async_update([])
    assert _issue(hass, "u1") is not None

    await tracker.async_update([_device("u1", "Volet")])
    assert _issue(hass, "u1") is None


async def test_missing_period_survives_a_restart(hass, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = _freeze(monkeypatch, start)
    first = MissingDeviceTracker(hass, "entry")
    await first.async_update([_device("u1", "Volet")])
    await first.async_update([])

    second = MissingDeviceTracker(hass, "entry")
    await second.async_load()
    clock["now"] = start + MISSING_DEVICE_RETENTION
    await second.async_update([])

    assert _issue(hass, "u1") is not None


async def test_registry_orphan_raises_issue_after_48_hours(hass, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = _freeze(monkeypatch, start)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "#BASE:u1")},
        name="Volet",
    )

    tracker = MissingDeviceTracker(hass, entry.entry_id)
    await tracker.async_reconcile(entry.entry_id)
    await tracker.async_update([])
    assert _issue(hass, "u1") is None

    clock["now"] = start + MISSING_DEVICE_RETENTION
    await tracker.async_update([])
    issue = _issue(hass, "u1")
    assert issue is not None
    assert issue.translation_placeholders["name"] == "Volet"


async def test_registry_reconcile_ignores_subdevices(hass, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = _freeze(monkeypatch, start)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "#BASE:u1#SUB:0")},
        name="Thermostat",
    )

    tracker = MissingDeviceTracker(hass, entry.entry_id)
    await tracker.async_reconcile(entry.entry_id)
    await tracker.async_update([])
    clock["now"] = start + MISSING_DEVICE_RETENTION
    await tracker.async_update([])

    assert _issue(hass, "u1#SUB:0") is None


async def test_forget_stops_tracking(hass, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = _freeze(monkeypatch, start)
    tracker = MissingDeviceTracker(hass, "entry")

    await tracker.async_update([_device("u1", "Volet")])
    await tracker.async_update([])
    clock["now"] = start + MISSING_DEVICE_RETENTION
    await tracker.async_update([])
    assert _issue(hass, "u1") is not None

    await tracker.async_forget("u1")
    assert _issue(hass, "u1") is None

    clock["now"] = start + 2 * MISSING_DEVICE_RETENTION
    await tracker.async_update([])
    assert _issue(hass, "u1") is None
