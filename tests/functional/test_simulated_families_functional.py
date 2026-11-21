"""F3.7-F3.9 — light, thermostat and diffuser over the in-memory bus."""
from device_simulator import (
    DiffuserSimulator,
    GarageSimulator,
    LightSimulator,
    MS600Simulator,
    MTS200Simulator,
    MTS300Simulator,
)
from helpers import start_adapter_with_bus, wait_for
from mqtt_bus import InMemoryMqttBus

THERMOSTAT = "Appliance.Control.Thermostat.Mode"
LIGHT = "Appliance.Control.Light"
SPRAY = "Appliance.Control.Diffuser.Spray"
DIFFUSER_LIGHT = "Appliance.Control.Diffuser.Light"


async def test_mts200_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(MTS200Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["mts200"], ["t1"])
    climate = adapter.runtimes["t1"].entities["climate"].values
    try:
        assert await wait_for(lambda: "current_temperature" in climate)
        assert climate["current_temperature"] == 17.7
        assert climate["target_temperature"] == 20.0

        await adapter.async_send("t1", THERMOSTAT, "SET", {
            "mode": [{"channel": 0, "onoff": 0, "targetTemp": 250}]})
        assert simulator.state["onoff"] == 0
        assert simulator.state["targetTemp"] == 250
        assert climate["onoff"] == 0
        assert climate["target_temperature"] == 25.0

        simulator.state["currentTemp"] = 190
        simulator.emit()
        assert climate["current_temperature"] == 19.0
    finally:
        await adapter.async_stop()


async def test_light_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(LightSimulator())
    adapter = await start_adapter_with_bus(hass, bus, ["msl120"], ["l1"])
    light = adapter.runtimes["l1"].entities["light"].values
    try:
        assert await wait_for(lambda: "onoff" in light)
        assert light == {"onoff": 1, "brightness": 80, "rgb": 0x123456}

        await adapter.async_send("l1", LIGHT, "SET", {
            "channel": 0, "light": {"onoff": 0, "luminance": 40}})
        assert simulator.state["onoff"] == 0
        assert light["onoff"] == 0
        assert light["brightness"] == 40

        simulator.state.update(onoff=1, luminance=100)
        simulator.emit()
        assert light["onoff"] == 1
        assert light["brightness"] == 100
    finally:
        await adapter.async_stop()


async def test_diffuser_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(DiffuserSimulator())
    adapter = await start_adapter_with_bus(hass, bus, ["mod"], ["d1"])
    runtime = adapter.runtimes["d1"]
    spray = runtime.entities["spray"].values
    light = runtime.entities["light"].values
    try:
        assert await wait_for(lambda: spray and light)
        assert spray == {"mode": 1}
        assert light == {"onoff": 1, "brightness": 50, "rgb": 100}

        await adapter.async_send("d1", SPRAY, "SET", {
            "spray": {"channel": 0, "mode": 0}})
        assert simulator.spray_mode == 0
        assert spray["mode"] == 0

        await adapter.async_send("d1", DIFFUSER_LIGHT, "SET", {
            "channel": 0, "light": {"luminance": 40}})
        assert light["brightness"] == 40

        simulator.spray_mode = 1
        simulator.light.update(luminance=90, onoff=0)
        simulator.emit(SPRAY)
        simulator.emit(DIFFUSER_LIGHT)
        assert spray["mode"] == 1
        assert light["brightness"] == 90
        assert light["onoff"] == 0
    finally:
        await adapter.async_stop()


async def test_mts300_uses_hundredth_degree_scale(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(MTS300Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["mts300"], ["t3"])
    climate = adapter.runtimes["t3"].entities["climate"].values
    try:
        assert await wait_for(lambda: "current_temperature" in climate)
        assert climate["current_temperature"] == 17.7
        assert climate["target_temperature"] == 20.0
        assert climate["min_temp"] == 5.0
        assert climate["max_temp"] == 35.0

        await adapter.async_send("t3", THERMOSTAT, "SET", {
            "mode": [{"channel": 0, "targetTemp": 2500}]})
        assert simulator.state["targetTemp"] == 2500
        assert climate["target_temperature"] == 25.0
    finally:
        await adapter.async_stop()


async def test_ms600_presence_and_light_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(MS600Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["ms600"], ["p1"])
    runtime = adapter.runtimes["p1"]
    try:
        simulator.emit()
        assert await wait_for(lambda: runtime.entities["distance"].values)
        assert runtime.entities["distance"].values["value"] == 0.76
        assert runtime.entities["illuminance"].values["value"] == 24
        assert runtime.entities["presence"].values["value"] == 2

        simulator.light = 80
        simulator.presence = {"value": 1, "distance": 1200, "times": 0}
        simulator.emit()
        assert await wait_for(
            lambda: runtime.entities["distance"].values["value"] == 1.2)
        assert runtime.entities["illuminance"].values["value"] == 80
    finally:
        await adapter.async_stop()


async def test_garage_door_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(GarageSimulator())
    adapter = await start_adapter_with_bus(hass, bus, ["garage"], ["g1"])
    door = adapter.runtimes["g1"].entities["door"].values
    try:
        assert await wait_for(lambda: "open" in door)
        assert door["open"] == 0

        await adapter.async_send("g1", "Appliance.GarageDoor.State", "SET", {
            "state": {"channel": 0, "open": 1}})
        assert simulator.open == 1
        assert door["open"] == 1

        simulator.open = 0
        simulator.emit()
        assert await wait_for(lambda: door["open"] == 0)
    finally:
        await adapter.async_stop()
