import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import yaml
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.meross_cloud.common import (
    BROKER_ADAPTER,
    DOMAIN,
    HA_BUTTON,
    HA_COVER,
    HA_LIGHT,
    HA_NUMBER,
    HA_SENSOR,
    HA_SWITCH,
)
from custom_components.meross_cloud.profile_entities import (
    async_setup_profile_entities,
)
from custom_components.meross_cloud.profiles.compiler import compile_profile
from custom_components.meross_cloud.profiles.models import ProfileMeta
from custom_components.meross_cloud.profiles.runtime import DeviceRuntime

_LOGGER = logging.getLogger(__name__)
FIXTURES = Path(__file__).parent / "fixtures" / "profiles"


def compiled_fixture(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return compile_profile(ProfileMeta(
        id=data["profile"]["id"], version=data["profile"].get("version"),
        source="test", digest=None, requires_engine=None, data=data,
    ))


class FakeAdapter:
    def __init__(self, runtime, state="connected"):
        self.state = state
        self.runtimes = {runtime.uuid: runtime}
        self.schedulers = {}
        self.sent = []
        self.ready = []

    async def async_send(self, device_uuid, namespace, method, payload):
        self.sent.append((device_uuid, namespace, method, payload))
        return True

    def add_ready_listener(self, callback):
        if self.state == "connected":
            callback()
        else:
            self.ready.append(callback)


def entry(enabled=True):
    return SimpleNamespace(options={"profile_entities": enabled})


async def setup_entities(hass, adapter, platform):
    hass.data[DOMAIN] = {
        BROKER_ADAPTER: adapter,
        "ADDED_ENTITIES_IDS": set(),
    }
    component = EntityComponent(_LOGGER, platform, hass)

    def add(entities, update_before_add=False):
        hass.async_create_task(component.async_add_entities(
            entities, update_before_add=update_before_add))

    async_setup_profile_entities(hass, entry(), platform, add)
    await hass.async_block_till_done()
    return component


def runtime(name, uuid="u1"):
    compiled = compiled_fixture(name)
    return DeviceRuntime(uuid, compiled)


async def test_switch_state_ids_and_command(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_SWITCH)
    entity = next(iter(component.entities))

    assert entity.unique_id == f"{DOMAIN}:u1:meross.mss310:switch"
    assert entity.is_on is False

    device.dispatch("Appliance.Control.ToggleX", "PUSH", {
        "channel": 0, "togglex": [{"channel": 0, "onoff": 1}]})
    await hass.async_block_till_done()
    assert entity.is_on is True

    await entity.async_turn_off()
    assert adapter.sent[-1] == (
        "u1", "Appliance.Control.ToggleX", "SET",
        {"channel": 0, "togglex": [{"channel": 0, "onoff": 0}]})


async def test_light_mapping_and_commands(hass):
    device = runtime("msl120")
    device.entities["light"].values.update(
        {"onoff": 1, "brightness": 50, "rgb": 0x123456})
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_LIGHT)
    entity = next(iter(component.entities))

    assert entity.is_on is True
    assert entity.brightness == 128
    assert entity.rgb_color == (0x12, 0x34, 0x56)

    await entity.async_turn_on(brightness=255, rgb_color=(1, 2, 3))
    assert adapter.sent[-3][3] == {
        "channel": 0, "light": {"rgb": 0x010203}}
    assert adapter.sent[-2][3] == {
        "channel": 0, "light": {"luminance": 100}}
    assert adapter.sent[-1][3] == {
        "channel": 0, "light": {"onoff": 1}}


async def test_cover_state_and_position_command(hass):
    device = runtime("mrs100")
    device.entities["cover"].values.update({"position": 40, "state": 1})
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_COVER)
    entity = next(iter(component.entities))

    assert entity.current_cover_position == 40
    assert entity.is_closed is False

    await entity.async_set_cover_position(position=55)
    assert adapter.sent[-1][3] == {"channel": 0, "position": 55}


async def test_number_range_and_scaled_command(hass):
    device = runtime("mrs100")
    device.entities["open_duration"].values["value"] = 45.0
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_NUMBER)
    entity = next(
        item for item in component.entities if item._spec.key == "open_duration")

    assert entity.native_min_value == 10
    assert entity.native_max_value == 120
    assert entity.native_step == 1
    assert entity.native_value == 45.0

    await entity.async_set_native_value(60)
    assert adapter.sent[-1][3] == {
        "channel": 0, "config": {"signalOpen": 60000}}


async def test_button_press(hass):
    device = runtime("mrs100")
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_BUTTON)
    entity = next(
        item for item in component.entities
        if item._spec.key == "start_calibration")

    await entity.async_press()

    assert adapter.sent[-1][3] == {"channel": 0, "value": 1}


async def test_sensor_value_and_entities_are_deduplicated(hass):
    device = runtime("mss310")
    device.entities["power"].values["value"] = 12
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_SENSOR)
    count = len(component.entities)
    assert count == 3
    power = next(
        item for item in component.entities if item._spec.key == "power")
    assert power.native_value == 12

    added = []
    async_setup_profile_entities(
        hass, entry(), HA_SENSOR,
        lambda entities, update_before_add=False: added.extend(entities))
    assert added == []


async def test_profile_entities_are_gated_by_the_option(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device)
    hass.data[DOMAIN] = {
        BROKER_ADAPTER: adapter,
        "ADDED_ENTITIES_IDS": set(),
    }
    component = EntityComponent(_LOGGER, HA_SWITCH, hass)
    added = []

    def add(entities, update_before_add=False):
        added.extend(entities)

    async_setup_profile_entities(hass, entry(False), HA_SWITCH, add)

    assert added == []
    assert not component.entities


async def test_subdevice_entity_device_info(hass):
    device = runtime("msh300", uuid="hub1")
    template = next(
        item for item in device.profile.subdevices if item.name == "ms100")
    device.add_subdevice("sub1", template)
    device.subdevices["sub1"].entities["temperature"].values["value"] = 21.5
    adapter = FakeAdapter(device)
    component = await setup_entities(hass, adapter, HA_SENSOR)
    entity = next(
        item for item in component.entities
        if item.unique_id.endswith("sub1:" + template.uid + ":temperature"))

    assert entity.native_value == 21.5
    assert entity.device_info["identifiers"] == {(DOMAIN, "sub1")}
    assert entity.device_info["via_device"] == (DOMAIN, "hub1")


async def test_unavailable_backend_marks_entities_unavailable(hass):
    device = runtime("mss310")
    adapter = FakeAdapter(device, state="starting")
    component = EntityComponent(_LOGGER, HA_SWITCH, hass)

    def add(entities, update_before_add=False):
        hass.async_create_task(component.async_add_entities(
            entities, update_before_add=update_before_add))

    hass.data[DOMAIN] = {
        BROKER_ADAPTER: adapter,
        "ADDED_ENTITIES_IDS": set(),
    }
    async_setup_profile_entities(hass, entry(), HA_SWITCH, add)
    assert len(adapter.ready) == 1

    adapter.state = "connected"
    adapter.ready[0]()
    await hass.async_block_till_done()

    entity = next(iter(component.entities))
    assert entity.available is True
