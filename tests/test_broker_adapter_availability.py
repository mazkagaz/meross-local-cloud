"""D5-b/D5-c: availability, discovery and unbind cleanup."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_local_cloud.broker_adapter import BrokerProfileAdapter
from custom_components.meross_local_cloud.common import (
    DOMAIN,
    MISSING_TRACKER,
)


def adapter(state="connected"):
    instance = BrokerProfileAdapter.__new__(BrokerProfileAdapter)
    instance.state = state
    instance.device_online = {}
    instance._listeners = []
    instance._unmatched = {}
    instance._transport = None
    return instance


def test_devlist_poll_updates_availability_and_notifies():
    instance = adapter()
    calls = []
    instance.add_listener(lambda: calls.append("changed"))

    instance.async_update_devices([
        SimpleNamespace(uuid="u1", online=True),
        SimpleNamespace(uuid="u2", online=False),
    ])
    instance.async_update_devices([
        SimpleNamespace(uuid="u1", online=True),
        SimpleNamespace(uuid="u2", online=False),
    ])

    assert instance.device_online == {"u1": True, "u2": False}
    assert len(calls) == 1


def test_system_and_hub_online_pushes_update_availability():
    instance = adapter()

    instance._apply_online(
        "u1", "Appliance.System.Online", {"online": {"status": 2}})
    assert instance.device_online["u1"] is False

    instance._apply_online(
        "hub", "Appliance.Hub.Online", {"status": 1})
    assert instance.device_online["hub"] is True

    instance._apply_online("ignored", "Appliance.Control.Light", {})
    assert "ignored" not in instance.device_online


def test_unknown_devices_are_reported_for_reload():
    instance = adapter()
    instance.descriptors = {"u1": {}}

    assert instance.unknown_devices([
        SimpleNamespace(uuid="u1"), SimpleNamespace(uuid="u2")]) == {"u2"}


def test_availability_requires_a_connected_adapter():
    instance = adapter(state="starting")
    instance.device_online["u1"] = True

    assert instance.device_available("u1") is False
    instance.state = "connected"
    assert instance.device_available("u1") is True
    assert instance.device_available("unknown") is True


async def test_unbind_removes_device_subdevice_and_entities(hass):
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry1")
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    top = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "#BASE:u1")},
        name="volet")
    sub = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "#BASE:u1#SUB:s1")},
        name="sonde",
        via_device=(DOMAIN, "#BASE:u1"))
    other = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "#BASE:u10")},
        name="autre")
    entities = er.async_get(hass)
    for device, unique_id in (
            (top, "switch:#BASE:u1:0"),
            (sub, "sensor:#BASE:u1#SUB:s1:0")):
        entities.async_get_or_create(
            domain=unique_id.split(":", 1)[0],
            platform=DOMAIN,
            unique_id=unique_id,
            config_entry=entry,
            device_id=device.id,
            suggested_object_id=unique_id.replace(":", "_"))

    forgotten = []

    class Tracker:
        async def async_forget(self, uuid):
            forgotten.append(uuid)

    instance = adapter()
    instance._hass = hass
    instance._coordinator = SimpleNamespace(config_entry_id=entry.entry_id)
    instance.runtimes = {"u1": object()}
    instance.schedulers = {}
    instance.descriptors = {"u1": {}}
    instance.device_online = {"u1": True}
    hass.data[DOMAIN] = {MISSING_TRACKER: Tracker()}

    await instance._async_remove_unbound("u1")

    assert devices.async_get(top.id) is None
    assert devices.async_get(sub.id) is None
    assert devices.async_get(other.id) is not None
    assert er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, "switch:#BASE:u1:0") is None
    assert forgotten == ["u1"]
    assert instance.runtimes == {}
    assert instance.descriptors == {}
    assert instance.device_online == {}


def test_descriptor_channels_are_normalized():
    from custom_components.meross_local_cloud.broker_adapter import (
        _descriptor_channels,
    )

    descriptor = SimpleNamespace(channels=[2, 0, True, -1, "1", 2])

    assert _descriptor_channels(descriptor) == [0, 2]
    assert _descriptor_channels(SimpleNamespace()) == []


def test_profile_matching_expands_channel_entities():
    from pathlib import Path

    import yaml

    from custom_components.meross_local_cloud.profiles import (
        ProfileCompiler,
        ProfileMeta,
        ProfileRegistry,
    )

    data = yaml.safe_load(
        (Path(__file__).parent / "fixtures" / "profiles" / "mss425.yaml")
        .read_text())
    profile = ProfileMeta(
        id=data["profile"]["id"], version=data["profile"]["version"],
        source="test", digest="hash", requires_engine=None, data=data)
    registry = ProfileRegistry(
        revision="rev", schema_version=2,
        profiles={profile.id: profile})
    instance = adapter()
    instance.registry = registry
    instance.compiler = ProfileCompiler()
    instance.runtimes = {}
    instance.descriptors = {"strip1": {
        "name": "Strip", "type": "mss425", "subType": None,
        "firmware": "4.0.0", "hardware": None,
        "abilities": ["Appliance.Control.ToggleX"],
        "mac": "AA:BB:CC:DD:EE:FF", "is_hub": False,
        "channels": [0, 2], "subdevices": [],
    }}
    instance.match_ambiguities = 0
    instance.devices_matched = 0
    instance.devices_unmatched = 0
    instance.subdevices_matched = 0
    instance.subdevices_unmatched = 0
    instance.compile_errors = []

    instance._match_profiles()

    runtime = instance.runtimes["strip1"]
    assert set(runtime.profile.entities) == {"outlet_0", "outlet_2"}
    assert set(runtime.entities) == {"outlet_0", "outlet_2"}
    assert instance.devices_matched == 1


async def test_runtime_state_is_restored_before_entities():
    from pathlib import Path

    import yaml

    from custom_components.meross_local_cloud.profiles import (
        ProfileCompiler,
        ProfileMeta,
    )
    from custom_components.meross_local_cloud.profiles.runtime import DeviceRuntime
    from custom_components.meross_local_cloud.runtime_store import (
        snapshot_runtimes,
    )

    data = yaml.safe_load(
        (Path(__file__).parent / "fixtures" / "profiles" / "mrs100.yaml")
        .read_text())
    profile = ProfileMeta(
        id=data["profile"]["id"], version=data["profile"]["version"],
        source="test", digest="hash", requires_engine=None, data=data)
    compiled = ProfileCompiler().compile(profile)
    source = DeviceRuntime("u1", compiled)
    source.entities["cover"].values["position"] = 0
    source.entities["calibration_status"].values["value"] = 2

    instance = adapter()
    instance.runtimes = {"u1": DeviceRuntime("u1", compiled)}
    instance._state_store = SimpleNamespace(
        async_load=AsyncMock(return_value=snapshot_runtimes({"u1": source})))

    await instance._async_restore_state()

    assert instance._restored_runtime_entities == 2
    assert instance.runtimes["u1"].entities["cover"].values == {"position": 0}
    assert instance.runtimes["u1"].entities[
        "calibration_status"].values == {"value": 2}
