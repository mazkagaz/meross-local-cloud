"""F2 — D5 cutover: profile-only mode, legacy ids, rollback (H2)."""
from helpers import FakeAdapter, entry, runtime, setup_entities

from custom_components.meross_cloud.common import DOMAIN, HA_SENSOR, HA_SWITCH
from custom_components.meross_cloud.profile_entities import (
    historical_entities_allowed,
)


async def test_f2_1_only_mode_uses_legacy_ids(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    switches = await setup_entities(
        hass, adapter, HA_SWITCH, entry(only=True))
    sensors = await setup_entities(
        hass, adapter, HA_SENSOR, entry(only=True))

    assert [entity.unique_id for entity in switches.entities] == [
        "switch:u1:0"]
    assert sorted(entity.unique_id for entity in sensors.entities) == [
        "sensor:u1:0:current:A",
        "sensor:u1:0:power:W",
        "sensor:u1:0:voltage:V",
    ]
    assert historical_entities_allowed(hass, entry(only=True), "u1") is False


async def test_f2_2_rollback_restores_the_historical_path(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    switches = await setup_entities(hass, adapter, HA_SWITCH, entry())

    entity = next(iter(switches.entities))
    assert entity.unique_id.startswith(f"{DOMAIN}:u1:")
    assert historical_entities_allowed(hass, entry(), "u1") is True


async def test_f2_3_unmatched_device_keeps_the_historical_fallback(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    sensors = await setup_entities(
        hass, adapter, HA_SENSOR, entry(only=True))

    assert all(":u1:" in entity.unique_id
               or entity.unique_id.startswith("sensor:u1:")
               for entity in sensors.entities)
    assert historical_entities_allowed(hass, entry(only=True), "u2") is True


async def test_f2_4_hub_subdevice_identity_and_via_device(hass):
    device = runtime("msh300", uuid="hub1")
    template = next(
        item for item in device.profile.subdevices if item.name == "ms100")
    device.add_subdevice("sub1", template)
    adapter = FakeAdapter(device)

    sensors = await setup_entities(
        hass, adapter, HA_SENSOR, entry(only=True))
    temperature = next(
        entity for entity in sensors.entities
        if entity.unique_id == "sensor:sub1:0:temperature:°C")

    assert temperature.device_info["identifiers"] == {(DOMAIN, "sub1")}
    assert temperature.device_info["via_device"] == (DOMAIN, "hub1")
    ids = [entity.unique_id for entity in sensors.entities]
    assert len(ids) == len(set(ids))


async def test_f2_5_restart_keeps_the_same_ids(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    first = await setup_entities(
        hass, adapter, HA_SWITCH, entry(only=True))
    first_ids = [entity.unique_id for entity in first.entities]

    second = await setup_entities(
        hass, adapter, HA_SWITCH, entry(only=True))
    second_ids = [entity.unique_id for entity in second.entities]

    assert first_ids == second_ids == ["switch:u1:0"]
