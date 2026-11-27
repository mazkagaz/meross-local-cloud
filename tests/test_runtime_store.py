"""Generic raw runtime state persistence."""
from pathlib import Path

import yaml

from custom_components.meross_local_cloud.profiles.compiler import compile_profile
from custom_components.meross_local_cloud.profiles.models import ProfileMeta
from custom_components.meross_local_cloud.profiles.runtime import DeviceRuntime
from custom_components.meross_local_cloud.runtime_store import (
    STORE_VERSION,
    restore_runtimes,
    snapshot_runtimes,
)

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"


def compiled(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return compile_profile(ProfileMeta(
        id=data["profile"]["id"], version=data["profile"].get("version"),
        source="test", digest=None, requires_engine=None, data=data,
    ))


def test_snapshot_and_restore_roundtrip():
    source = DeviceRuntime("u1", compiled("mrs100"))
    source.entities["cover"].values["position"] = 0
    source.entities["calibration_status"].values["value"] = 2
    source.entities["open_duration"].values["value"] = 45.0

    data = snapshot_runtimes({"u1": source})
    target = DeviceRuntime("u1", compiled("mrs100"))

    assert restore_runtimes(data, {"u1": target}) == 3
    assert target.entities["cover"].values == {"position": 0}
    assert target.entities["calibration_status"].values == {"value": 2}
    assert target.entities["open_duration"].values == {"value": 45.0}


def test_restore_ignores_unknown_profiles_and_platforms():
    source = DeviceRuntime("u1", compiled("mrs100"))
    source.entities["calibration_status"].values["value"] = 2
    data = snapshot_runtimes({"u1": source})

    other = DeviceRuntime("u1", compiled("mss310"))
    assert restore_runtimes(data, {"u1": other}) == 0

    data["devices"]["u1"]["profile"] = "meross.mrs100"
    data["devices"]["u1"]["entities"]["calibration_status"][
        "platform"] = "binary_sensor"
    target = DeviceRuntime("u1", compiled("mrs100"))
    assert restore_runtimes(data, {"u1": target}) == 0
    assert target.entities["calibration_status"].values == {}


def test_restore_filters_non_scalar_and_unknown_values():
    source = DeviceRuntime("u1", compiled("mrs100"))
    data = snapshot_runtimes({"u1": source})
    data["devices"]["u1"]["entities"]["cover"]["values"] = {
        "position": 40, "extra": 1, "nested": {"a": 1}}
    target = DeviceRuntime("u1", compiled("mrs100"))

    assert restore_runtimes(data, {"u1": target}) == 1
    assert target.entities["cover"].values == {"position": 40}


def test_restore_handles_subdevices_and_bad_payloads():
    source = DeviceRuntime("hub1", compiled("msh300"))
    template = {item.name: item for item in source.profile.subdevices}["ms100"]
    source.add_subdevice("sub1", template)
    source.subdevices["sub1"].entities["temperature"].values["value"] = 21.5
    data = snapshot_runtimes({"hub1": source})

    target = DeviceRuntime("hub1", compiled("msh300"))
    target.add_subdevice("sub1", template)
    assert restore_runtimes(data, {"hub1": target}) == 1
    assert target.subdevices["sub1"].entities[
        "temperature"].values["value"] == 21.5

    data["devices"]["hub1"]["subdevices"]["sub1"]["template"] = "other"
    empty = DeviceRuntime("hub1", compiled("msh300"))
    empty.add_subdevice("sub1", template)
    assert restore_runtimes(data, {"hub1": empty}) == 0
    assert restore_runtimes(None, {"hub1": empty}) == 0
    assert restore_runtimes({"version": STORE_VERSION}, {"hub1": empty}) == 0


def test_movement_fields_are_persisted_and_restored():
    source = DeviceRuntime("u1", compiled("msl610"))
    source.entities["light"].values.update(
        {"onoff": 1, "brightness": 20, "color_temp": 50})
    data = snapshot_runtimes({"u1": source})

    target = DeviceRuntime("u1", compiled("msl610"))
    assert restore_runtimes(data, {"u1": target}) == 1
    assert target.entities["light"].values == {
        "onoff": 1, "brightness": 20, "color_temp": 50}
