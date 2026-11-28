"""F2 — D5 cutover: profile-only mode, legacy ids, rollback (H2)."""
from types import SimpleNamespace

from helpers import FakeAdapter, entry, runtime, setup_entities

from custom_components.meross_local_cloud.common import DOMAIN, HA_SENSOR, HA_SWITCH


async def test_f2_1_profile_only_uses_legacy_ids(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    switches = await setup_entities(hass, adapter, HA_SWITCH, entry())
    sensors = await setup_entities(hass, adapter, HA_SENSOR, entry())

    assert [entity.unique_id for entity in switches.entities] == [
        "switch:#BASE:u1:0"]
    assert sorted(entity.unique_id for entity in sensors.entities) == [
        "sensor:#BASE:u1:0:current:A",
        "sensor:#BASE:u1:0:power:W",
        "sensor:#BASE:u1:0:voltage:V",
    ]


async def test_f2_2_options_no_longer_change_identity(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    switches = await setup_entities(hass, adapter, HA_SWITCH, entry())
    legacy = await setup_entities(
        hass, adapter, HA_SWITCH, entry(only=True))

    assert [e.unique_id for e in switches.entities] == [
        e.unique_id for e in legacy.entities] == ["switch:#BASE:u1:0"]


async def test_f2_3_unmatched_devices_have_no_historical_fallback(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    sensors = await setup_entities(hass, adapter, HA_SENSOR, entry())

    assert all(entity.unique_id.startswith("sensor:#BASE:u1:")
               for entity in sensors.entities)


async def test_f2_4_hub_subdevice_identity_and_via_device(hass):
    device = runtime("msh300", uuid="hub1")
    template = next(
        item for item in device.profile.subdevices if item.name == "ms100")
    device.add_subdevice("sub1", template)
    adapter = FakeAdapter(device)

    sensors = await setup_entities(hass, adapter, HA_SENSOR, entry())
    temperature = next(
        entity for entity in sensors.entities
        if entity._spec.key == "temperature")

    assert temperature.device_info["identifiers"] == {
        (DOMAIN, "#BASE:hub1#SUB:sub1")}
    assert (temperature.device_info.get("via_device_id")
            or temperature.device_info.get("via_device"))
    ids = [entity.unique_id for entity in sensors.entities]
    assert len(ids) == len(set(ids))


async def test_f2_6_devlist_poll_controls_entity_availability(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)
    switches = await setup_entities(hass, adapter, HA_SWITCH, entry())
    entity = next(iter(switches.entities))

    adapter.async_update_devices([
        SimpleNamespace(uuid="u1", online=False)])
    await hass.async_block_till_done()
    assert entity.available is False

    adapter.async_update_devices([
        SimpleNamespace(uuid="u1", online=True)])
    await hass.async_block_till_done()
    assert entity.available is True


async def test_f2_5_restart_keeps_the_same_ids(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)

    first = await setup_entities(hass, adapter, HA_SWITCH, entry())
    first_ids = [entity.unique_id for entity in first.entities]

    second = await setup_entities(hass, adapter, HA_SWITCH, entry())
    second_ids = [entity.unique_id for entity in second.entities]

    assert first_ids == second_ids == ["switch:#BASE:u1:0"]
