"""D5 parity: every shipped profile compiles and consumes a golden frame."""
from pathlib import Path

import pytest
import yaml

from custom_components.meross_cloud.profiles.compiler import compile_profile
from custom_components.meross_cloud.profiles.models import ProfileMeta
from custom_components.meross_cloud.profiles.runtime import DeviceRuntime

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"
TOGGLE = "Appliance.Control.ToggleX"
LIGHT = "Appliance.Control.Light"
POSITION = "Appliance.RollerShutter.Position"
CONFIG = "Appliance.RollerShutter.Config"
ELECTRICITY = "Appliance.Control.Electricity"
FAN = "Appliance.Control.Fan"
THERMOSTAT = "Appliance.Control.Thermostat.Mode"
SPRAY = "Appliance.Control.Diffuser.Spray"
DIFFUSER_LIGHT = "Appliance.Control.Diffuser.Light"


def compiled(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return compile_profile(ProfileMeta(
        id=data["profile"]["id"], version=data["profile"].get("version"),
        source="test", digest=None, requires_engine=None, data=data,
    ))


SIMPLE_CASES = {
    "mss310": [
        (TOGGLE, {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]},
         {"switch": {"onoff": 1}}),
        (ELECTRICITY, {"channel": 0, "electricity": {"power": 42}},
         {"power": {"value": 42}}),
    ],
    "mss": [
        (TOGGLE, {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]},
         {"switch": {"onoff": 1}}),
    ],
    "msl120": [
        (LIGHT, {"channel": 0, "light": {"onoff": 1, "luminance": 80}},
         {"light": {"onoff": 1, "brightness": 80}}),
    ],
    "msl": [
        (LIGHT, {"channel": 0, "light": {"onoff": 1, "rgb": 255}},
         {"light": {"onoff": 1, "rgb": 255}}),
    ],
    "mss5": [
        (LIGHT, {"channel": 0, "light": {"onoff": 1, "luminance": 40}},
         {"light": {"onoff": 1, "brightness": 40}}),
    ],
    "mrs": [
        (POSITION, {"channel": 0, "position": 60, "state": 1},
         {"cover": {"position": 60, "state": 1}}),
    ],
    "mrs100": [
        (POSITION, {"channel": 0, "position": 60, "state": 1},
         {"cover": {"position": 60, "state": 1}}),
        (CONFIG, {"channel": 0,
                  "config": {"signalOpen": 45000, "signalClose": 50000}},
         {"open_duration": {"value": 45.0},
          "close_duration": {"value": 50.0}}),
    ],
    "mts200": [
        (THERMOSTAT, {"mode": [{"channel": 0, "onoff": 1, "mode": 1,
                               "state": 1, "currentTemp": 177,
                               "targetTemp": 200, "min": 50, "max": 350}]},
         {"climate": {"current_temperature": 17.7,
                      "target_temperature": 20.0, "mode": 1}}),
    ],
    "mfc": [
        (FAN, {"fan": [{"channel": 0, "speed": 2, "maxSpeed": 3}]},
         {"fan": {"speed": 2, "max_speed": 3}}),
    ],
    "mod": [
        (SPRAY, {"spray": {"channel": 0, "mode": 1}},
         {"spray": {"mode": 1}}),
        (DIFFUSER_LIGHT,
         {"channel": 0, "light": {"onoff": 1, "luminance": 50}},
         {"light": {"onoff": 1, "brightness": 50}}),
    ],
}


@pytest.mark.parametrize("name", sorted(SIMPLE_CASES))
def test_profile_golden_frames(name):
    profile = compiled(name)
    runtime = DeviceRuntime("u1", profile)

    for namespace, frame, expected in SIMPLE_CASES[name]:
        assert runtime.dispatch(namespace, "PUSH", frame) > 0
        for key, values in expected.items():
            assert runtime.entities[key].values.items() >= values.items()


def test_hub_profile_golden_frames():
    profile = compiled("msh300")
    runtime = DeviceRuntime("hub1", profile)
    templates = {template.name: template for template in profile.subdevices}
    runtime.add_subdevice("sub1", templates["ms100"])
    runtime.add_subdevice("sensor1", templates["ms130"])
    runtime.add_subdevice("valve1", templates["mts100"])

    assert runtime.dispatch("Appliance.Hub.Sensor.TempHum", "PUSH", {
        "tempHum": [{"id": "sub1", "latestTemperature": 215,
                     "latestHumidity": 553, "voltage": 3000}],
    }) == 3
    assert runtime.dispatch("Appliance.Hub.Sensor.All", "PUSH", {
        "all": [{"id": "sensor1",
                 "temperature": {"latest": 215},
                 "humidity": {"latest": 553}}],
    }) == 2
    assert runtime.dispatch("Appliance.Hub.Mts100.All", "PUSH", {
        "all": [{"id": "valve1", "mode": {"state": 1},
                 "temperature": {"room": 44, "currentSet": 40,
                                 "heating": 1, "min": 10, "max": 70},
                 "togglex": {"onoff": 1}}],
    }) == 7

    ms100 = runtime.subdevices["sub1"].entities
    assert ms100["temperature"].values["value"] == pytest.approx(21.5)
    assert ms100["humidity"].values["value"] == pytest.approx(55.3)
    assert ms100["voltage"].values["value"] == pytest.approx(3.0)
    assert runtime.subdevices["sensor1"].entities[
        "temperature"].values["value"] == pytest.approx(21.5)
    climate = runtime.subdevices["valve1"].entities["climate"].values
    assert climate["current_temperature"] == pytest.approx(22.0)
    assert climate["target_temperature"] == pytest.approx(20.0)
