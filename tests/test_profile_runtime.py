from pathlib import Path

import pytest
import yaml

from custom_components.meross_local_cloud.profiles.compiler import (
    compile_profile,
    expand_channel_entities,
)
from custom_components.meross_local_cloud.profiles.models import ProfileMeta
from custom_components.meross_local_cloud.profiles.runtime import (
    MAX_PAYLOAD_BYTES,
    DeviceRuntime,
)

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"
TOGGLE_NS = "Appliance.Control.ToggleX"
ELECTRICITY_NS = "Appliance.Control.Electricity"
CONFIG_NS = "Appliance.RollerShutter.Config"
STATE_NS = "Appliance.RollerShutter.State"
SUBDEVICE_NS = "Appliance.Hub.Sensor.TempHum"


def compile_data(data):
    return compile_profile(ProfileMeta(
        id=data["profile"]["id"],
        version=data["profile"].get("version"),
        source="test",
        digest=None,
        requires_engine=None,
        data=data,
    ))


def compiled_fixture(name):
    return compile_data(yaml.safe_load(
        (FIXTURES / f"{name}.yaml").read_text()))


def runtime(name="mss310"):
    return DeviceRuntime("u1", compiled_fixture(name))


def test_cover_movement_is_applied_from_state_push():
    device = runtime("mrs100")

    applied = device.dispatch(STATE_NS, "PUSH", {
        "state": [{"channel": 0, "state": 2, "timestamp": 1}],
    })

    assert applied == 1
    assert device.entities["cover"].values["movement"] == 2


def test_toggle_push_updates_the_switch_state():
    device = runtime()

    applied = device.dispatch(TOGGLE_NS, "PUSH", {
        "channel": 0,
        "togglex": [{"channel": 0, "onoff": 1}],
    })

    assert applied == 1
    assert device.entities["switch"].values == {"onoff": 1}
    assert device.messages == 1
    assert device.updates == 1
    assert device.ignored == 0


def test_ack_payloads_are_applied():
    device = runtime()

    assert device.dispatch(TOGGLE_NS, "GETACK", {
        "channel": 0,
        "togglex": [{"channel": 0, "onoff": 0}],
    }) == 1
    assert device.entities["switch"].values == {"onoff": 0}


def test_state_scale_is_applied_to_mrs100_durations():
    device = runtime("mrs100")

    applied = device.dispatch(CONFIG_NS, "GETACK", {
        "config": [
            {"channel": 0, "signalOpen": 45000, "signalClose": 50000}],
    })

    assert applied == 2
    assert device.entities["open_duration"].values["value"] == \
        pytest.approx(45.0)
    assert device.entities["close_duration"].values["value"] == \
        pytest.approx(50.0)


@pytest.mark.parametrize("method", ["GET", "SET", "ERROR", None])
def test_non_state_methods_are_ignored(method):
    device = runtime()

    assert device.dispatch(TOGGLE_NS, method, {
        "channel": 0, "togglex": [{"channel": 0, "onoff": 1}]}) == 0
    assert device.entities["switch"].values == {}
    assert device.ignored == 1


@pytest.mark.parametrize("payload", [[], "nope", None, 5])
def test_non_object_payload_is_ignored(payload):
    device = runtime()

    assert device.dispatch(TOGGLE_NS, "PUSH", payload) == 0
    assert device.ignored == 1
    assert device.errors == []


def test_missing_namespace_is_ignored():
    device = runtime()

    assert device.dispatch(None, "PUSH", {"x": 1}) == 0
    assert device.ignored == 1


def test_unknown_namespace_is_ignored():
    device = runtime()

    assert device.dispatch("Appliance.Unknown", "PUSH", {"x": 1}) == 0
    assert device.ignored == 1
    assert device.errors == []


def test_short_array_and_missing_path_are_ignored():
    device = runtime()

    assert device.dispatch(TOGGLE_NS, "PUSH", {
        "channel": 0, "togglex": []}) == 0
    assert device.dispatch(TOGGLE_NS, "PUSH", {"channel": 0}) == 0
    assert device.entities["switch"].values == {}
    assert device.ignored == 2


def test_out_of_range_channel_is_ignored():
    device = runtime("mss310")

    assert device.dispatch(ELECTRICITY_NS, "PUSH", {
        "channel": 2,
        "electricity": {"power": 10, "voltage": 2300, "current": 50},
    }) == 0
    assert device.entities["power"].values == {}
    assert device.ignored == 1


def test_unexpected_value_type_is_an_isolated_error():
    data = {
        "schema_version": 2,
        "profile": {"id": "test.types", "version": "1"},
        "match": {"type": ["x"]},
        "payloads": {
            "Appliance.Test": {"methods": ["PUSH"], "fields": {}},
        },
        "entities": [{
            "key": "sensor",
            "platform": "sensor",
            "channel": 0,
            "state": {
                "namespace": "Appliance.Test",
                "channel": "$channel",
                "fields": {"value": "nested"},
            },
        }],
    }
    device = DeviceRuntime("u1", compile_data(data))

    applied = device.dispatch(
        "Appliance.Test", "PUSH", {"channel": 0, "nested": {"x": 1}})

    assert applied == 0
    assert device.errors
    assert "unexpected dict" in device.errors[0]


def test_one_bad_entity_does_not_block_the_other():
    data = {
        "schema_version": 2,
        "profile": {"id": "test.isolation", "version": "1"},
        "match": {"type": ["x"]},
        "payloads": {
            "Appliance.Test": {"methods": ["PUSH"], "fields": {}},
        },
        "entities": [
            {
                "key": "bad",
                "platform": "sensor",
                "channel": 0,
                "state": {
                    "namespace": "Appliance.Test",
                    "channel": "$channel",
                    "fields": {"value": "nested"},
                },
            },
            {
                "key": "good",
                "platform": "sensor",
                "channel": 0,
                "state": {
                    "namespace": "Appliance.Test",
                    "channel": "$channel",
                    "fields": {"value": "value"},
                },
            },
        ],
    }
    device = DeviceRuntime("u1", compile_data(data))

    applied = device.dispatch(
        "Appliance.Test", "PUSH",
        {"channel": 0, "nested": {"x": 1}, "value": 7})

    assert applied == 1
    assert device.entities["good"].values == {"value": 7}
    assert device.entities["bad"].values == {}
    assert device.errors


def test_non_numeric_value_cannot_be_scaled():
    data = {
        "schema_version": 2,
        "profile": {"id": "test.scale", "version": "1"},
        "match": {"type": ["x"]},
        "payloads": {
            "Appliance.Test": {"methods": ["PUSH"], "fields": {}},
        },
        "entities": [{
            "key": "sensor",
            "platform": "sensor",
            "channel": 0,
            "state": {
                "namespace": "Appliance.Test",
                "channel": "$channel",
                "fields": {"value": "value"},
                "scale": 0.001,
            },
        }],
    }
    device = DeviceRuntime("u1", compile_data(data))

    applied = device.dispatch(
        "Appliance.Test", "PUSH", {"channel": 0, "value": "abc"})

    assert applied == 0
    assert any("cannot scale" in error for error in device.errors)


def test_oversized_payload_is_rejected():
    device = runtime()

    applied = device.dispatch(TOGGLE_NS, "PUSH", {
        "blob": "x" * (MAX_PAYLOAD_BYTES + 10)})

    assert applied == 0
    assert device.ignored == 1
    assert any("size limit" in error for error in device.errors)


def pilot_hub():
    compiled = compiled_fixture("msh300")
    templates = {template.name: template for template in compiled.subdevices}
    device = DeviceRuntime("hub1", compiled)
    device.add_subdevice("sub1", templates["ms100"])
    device.add_subdevice("sensor1", templates["ms130"])
    device.add_subdevice("valve1", templates["mts100"])
    return device


def test_ms100_temperature_humidity_frame():
    device = pilot_hub()

    applied = device.dispatch("Appliance.Hub.Sensor.TempHum", "PUSH", {
        "tempHum": [{
            "id": "sub1",
            "latestTemperature": 215,
            "latestHumidity": 553,
            "voltage": 3000,
        }],
    })

    entities = device.subdevices["sub1"].entities
    assert applied == 3
    assert entities["temperature"].values["value"] == pytest.approx(21.5)
    assert entities["humidity"].values["value"] == pytest.approx(55.3)
    assert entities["voltage"].values["value"] == pytest.approx(3.0)


def test_ms130_sensor_all_frame():
    device = pilot_hub()

    applied = device.dispatch("Appliance.Hub.Sensor.All", "PUSH", {
        "all": [{
            "id": "sensor1",
            "temperature": {"latest": 215},
            "humidity": {"latest": 553},
        }],
    })

    entities = device.subdevices["sensor1"].entities
    assert applied == 2
    assert entities["temperature"].values["value"] == pytest.approx(21.5)
    assert entities["humidity"].values["value"] == pytest.approx(55.3)


def test_generic_switch_frame():
    device = DeviceRuntime("plug", compiled_fixture("mss"))

    applied = device.dispatch(TOGGLE_NS, "PUSH", {
        "channel": 0, "togglex": [{"channel": 0, "onoff": 1}]})

    assert applied == 1
    assert device.entities["switch"].values == {"onoff": 1}


def test_generic_light_frame():
    device = DeviceRuntime("bulb", compiled_fixture("msl"))

    applied = device.dispatch("Appliance.Control.Light", "PUSH", {
        "channel": 0,
        "light": {"onoff": 1, "luminance": 80, "rgb": 255},
    })

    assert applied == 3
    assert device.entities["light"].values == {
        "onoff": 1, "brightness": 80, "rgb": 255}


def test_generic_shutter_frame():
    device = DeviceRuntime("shutter", compiled_fixture("mrs"))

    applied = device.dispatch("Appliance.RollerShutter.Position", "PUSH", {
        "position": [{"channel": 0, "position": 60}]})

    assert applied == 1
    assert device.entities["cover"].values == {"position": 60}


def test_dimmer_frame():
    device = DeviceRuntime("dimmer", compiled_fixture("mss5"))

    applied = device.dispatch("Appliance.Control.Light", "PUSH", {
        "channel": 0, "light": {"onoff": 1, "luminance": 40}})

    assert applied == 2
    assert device.entities["light"].values == {
        "onoff": 1, "brightness": 40}


def test_diffuser_frames():
    device = DeviceRuntime("diffuser", compiled_fixture("mod"))

    spray = device.dispatch("Appliance.Control.Diffuser.Spray", "PUSH", {
        "spray": {"channel": 0, "mode": 1}})
    light = device.dispatch("Appliance.Control.Diffuser.Light", "PUSH", {
        "channel": 0,
        "light": {"onoff": 1, "luminance": 50, "rgb": 100},
    })

    assert spray == 1
    assert light == 3
    assert device.entities["spray"].values == {"mode": 1}
    assert device.entities["light"].values == {
        "onoff": 1, "brightness": 50, "rgb": 100}


def test_mts100_all_frame():
    device = pilot_hub()

    applied = device.dispatch("Appliance.Hub.Mts100.All", "PUSH", {
        "all": [{
            "id": "valve1",
            "mode": {"state": 1},
            "temperature": {"room": 44, "currentSet": 40, "heating": 1,
                            "min": 10, "max": 70},
            "togglex": {"onoff": 1},
        }],
    })

    values = device.subdevices["valve1"].entities["climate"].values
    assert applied == 7
    assert values["current_temperature"] == pytest.approx(22.0)
    assert values["target_temperature"] == pytest.approx(20.0)
    assert values["heating"] == 1
    assert values["mode"] == 1
    assert values["onoff"] == 1
    assert values["min_temp"] == pytest.approx(5.0)
    assert values["max_temp"] == pytest.approx(35.0)


def test_mts200_mode_frame():
    device = DeviceRuntime("thermostat", compiled_fixture("mts200"))

    applied = device.dispatch("Appliance.Control.Thermostat.Mode", "PUSH", {
        "mode": [{
            "channel": 0, "onoff": 1, "mode": 1, "state": 1,
            "currentTemp": 177, "targetTemp": 200, "min": 50, "max": 350,
        }],
    })

    values = device.entities["climate"].values
    assert applied == 7
    assert values["current_temperature"] == pytest.approx(17.7)
    assert values["target_temperature"] == pytest.approx(20.0)
    assert values["mode"] == 1


def test_fan_frame():
    device = DeviceRuntime("fan", compiled_fixture("mfc"))

    applied = device.dispatch("Appliance.Control.Fan", "PUSH", {
        "fan": [{"channel": 0, "speed": 2, "maxSpeed": 3}],
    })

    values = device.entities["fan"].values
    assert applied == 2
    assert values == {"speed": 2, "max_speed": 3}


def hub_data():
    return {
        "schema_version": 2,
        "profile": {"id": "test.hub", "version": "1"},
        "match": {"kind": "hub", "type": ["msh300"]},
        "payloads": {},
        "entities": [],
        "subdevices": [{
            "match": {"type": ["ms100"]},
            "payloads": {
                SUBDEVICE_NS: {"methods": ["PUSH"], "fields": {}},
            },
            "entities": [{
                "key": "temperature",
                "platform": "sensor",
                "state": {
                    "namespace": SUBDEVICE_NS,
                    "fields": {"value": "temperature"},
                },
            }],
        }],
    }


def hub_runtime():
    compiled = compile_data(hub_data())
    device = DeviceRuntime("hub1", compiled)
    device.add_subdevice("sub1", compiled.subdevices[0])
    return device


def test_hub_subdevice_payload_is_routed_by_id():
    device = hub_runtime()

    applied = device.dispatch(SUBDEVICE_NS, "PUSH", {
        "tempHum": [
            {"id": "other", "temperature": 10},
            {"id": "sub1", "temperature": 215},
        ],
    })

    assert applied == 1
    state = device.subdevices["sub1"].entities["temperature"]
    assert state.values == {"value": 215}


def test_hub_subdevice_payload_can_be_the_document_itself():
    device = hub_runtime()

    applied = device.dispatch(
        SUBDEVICE_NS, "PUSH", {"id": "sub1", "temperature": 200})

    assert applied == 1
    state = device.subdevices["sub1"].entities["temperature"]
    assert state.values == {"value": 200}


def test_unknown_subdevice_id_is_ignored():
    device = hub_runtime()

    applied = device.dispatch(SUBDEVICE_NS, "PUSH", {
        "tempHum": [{"id": "other", "temperature": 10}]})

    assert applied == 0
    assert device.ignored == 1


def channel_runtime(channels=(0, 1, 2)):
    data = {
        "schema_version": 2,
        "profile": {"id": "test.multisocket", "version": "1"},
        "match": {"type": ["mss425"]},
        "payloads": {
            TOGGLE_NS: {
                "methods": ["GETACK", "PUSH"],
                "fields": {},
            },
        },
        "entities": [{
            "key": "outlet",
            "platform": "switch",
            "channel": "$channels",
            "name": "Outlet $channel_number",
            "state": {
                "namespace": TOGGLE_NS,
                "channel": "$channel",
                "select": {"path": "togglex", "key": "channel"},
                "fields": {"onoff": "onoff"},
            },
            "commands": {
                "turn_on": {
                    "namespace": TOGGLE_NS,
                    "payload": {"channel": "$channel",
                                "togglex": [{"channel": "$channel",
                                             "onoff": 1}]},
                },
            },
        }],
    }
    compiled = expand_channel_entities(compile_data(data), channels)
    return DeviceRuntime("strip1", compiled)


def test_channel_selection_uses_the_item_channel_not_its_position():
    device = channel_runtime()

    applied = device.dispatch(TOGGLE_NS, "PUSH", {
        "togglex": [
            {"channel": 2, "onoff": 1},
            {"channel": 0, "onoff": 0},
        ],
    })

    assert applied == 2
    assert device.entities["outlet_0"].values == {"onoff": 0}
    assert device.entities["outlet_2"].values == {"onoff": 1}
    assert device.entities["outlet_1"].values == {}


def test_channel_selection_ignores_the_payload_top_level_channel():
    device = channel_runtime()

    device.dispatch(TOGGLE_NS, "PUSH", {
        "channel": 0,
        "togglex": [{"channel": 1, "onoff": 1}],
    })

    assert device.entities["outlet_1"].values == {"onoff": 1}
    assert device.entities["outlet_0"].values == {}


def test_channel_selection_misses_are_ignored():
    device = channel_runtime()

    applied = device.dispatch(TOGGLE_NS, "PUSH", {
        "togglex": [{"channel": 7, "onoff": 1}],
    })

    assert applied == 0
    assert all(not entity.values for entity in device.entities.values())


@pytest.mark.parametrize("payload", [
    {"togglex": None},
    {"togglex": [1, 2]},
    {},
])
def test_channel_selection_rejects_malformed_lists(payload):
    device = channel_runtime()

    assert device.dispatch(TOGGLE_NS, "PUSH", payload) == 0
    assert all(not entity.values for entity in device.entities.values())


def test_on_values_maps_the_raw_value_to_a_boolean():
    data = {
        "schema_version": 2,
        "profile": {"id": "test.smoke", "version": "1"},
        "match": {"type": ["gs559"]},
        "payloads": {
            "Appliance.Hub.Sensor.Smoke": {
                "methods": ["GETACK", "PUSH"],
                "fields": {},
            },
        },
        "entities": [{
            "key": "alarm",
            "platform": "binary_sensor",
            "state": {
                "namespace": "Appliance.Hub.Sensor.Smoke",
                "fields": {"value": {"path": "status",
                                     "on_values": [23, 25]}},
            },
        }],
    }
    device = DeviceRuntime("gs1", compile_data(data))

    for status, expected in ((25, True), (170, False), (23, True)):
        assert device.dispatch("Appliance.Hub.Sensor.Smoke", "PUSH", {
            "status": status}) == 1
        assert device.entities["alarm"].values["value"] is expected


def test_state_select_accepts_a_single_object_payload():
    data = {
        "schema_version": 2,
        "profile": {"id": "test.garage", "version": "1"},
        "match": {"type": ["msg"]},
        "payloads": {
            "Appliance.GarageDoor.State": {
                "methods": ["GETACK", "PUSH"],
                "fields": {},
            },
        },
        "entities": [{
            "key": "door",
            "platform": "cover",
            "channel": 0,
            "quirks": [{"name": "garage_door"}],
            "state": {
                "namespace": "Appliance.GarageDoor.State",
                "channel": "$channel",
                "select": {"path": "state", "key": "channel"},
                "fields": {"open": "open"},
            },
        }],
    }
    device = DeviceRuntime("g1", compile_data(data))

    assert device.dispatch("Appliance.GarageDoor.State", "PUSH", {
        "state": {"channel": 0, "open": 1}}) == 1
    assert device.entities["door"].values == {"open": 1}

    assert device.dispatch("Appliance.GarageDoor.State", "PUSH", {
        "state": [{"channel": 0, "open": 0}]}) == 1
    assert device.entities["door"].values == {"open": 0}


def test_subdevice_payload_is_routed_by_sub_id():
    data = {
        "schema_version": 2,
        "profile": {"id": "test.hub-mst", "version": "1"},
        "match": {"kind": "hub", "type": ["msh"]},
        "payloads": {},
        "entities": [],
        "subdevices": [{
            "match": {"type": ["mst100"]},
            "payloads": {
                "Appliance.Control.Water": {
                    "methods": ["GETACK", "PUSH"],
                    "fields": {},
                },
            },
            "entities": [{
                "key": "watering",
                "platform": "switch",
                "device": "subdevice",
                "state": {
                    "namespace": "Appliance.Control.Water",
                    "fields": {"onoff": {"path": "onoff",
                                         "on_values": [1]}},
                },
            }],
        }],
    }
    compiled = compile_data(data)
    device = DeviceRuntime("hub1", compiled)
    device.add_subdevice("MST1", compiled.subdevices[0])

    assert device.dispatch("Appliance.Control.Water", "PUSH", {
        "control": [{"subId": "MST1", "onoff": 1, "dura": 1800}]}) == 1
    assert device.subdevices["MST1"].entities[
        "watering"].values["onoff"] is True
