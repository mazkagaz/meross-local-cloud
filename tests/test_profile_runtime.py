from pathlib import Path

import pytest
import yaml

from custom_components.meross_cloud.profiles.compiler import compile_profile
from custom_components.meross_cloud.profiles.models import ProfileMeta
from custom_components.meross_cloud.profiles.runtime import (
    MAX_PAYLOAD_BYTES,
    DeviceRuntime,
)

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"
TOGGLE_NS = "Appliance.Control.ToggleX"
ELECTRICITY_NS = "Appliance.Control.Electricity"
CONFIG_NS = "Appliance.RollerShutter.Config"
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
        "channel": 0,
        "config": {"signalOpen": 45000, "signalClose": 50000},
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
