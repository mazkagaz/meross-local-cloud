"""F3.7-F3.9 — light, thermostat and diffuser over the in-memory bus."""
from device_simulator import (
    DiffuserSimulator,
    EMSimulator,
    GarageSimulator,
    HP110Simulator,
    Map100Simulator,
    Msxh0Simulator,
    LightSimulator,
    MS600Simulator,
    MSL610Simulator,
    MTS200Simulator,
    MTS300Simulator,
)
from helpers import entry, setup_entities, start_adapter_with_bus, wait_for
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


async def test_msl610_color_brightness_and_onoff_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(MSL610Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["msl610"], ["l610"])
    component = await setup_entities(hass, adapter, "light", entry())
    entity = next(iter(component.entities))
    try:
        assert entity.is_on is None

        simulator.emit_light()
        simulator.emit_toggle()
        assert await wait_for(lambda: entity.brightness == 128)
        assert entity.is_on is True
        assert 4500 <= entity.color_temp_kelvin <= 4700

        await entity.async_turn_on(brightness=128)
        assert bus.requests[-2][2] == "SET"
        assert bus.requests[-2][3] == {
            "channel": 0,
            "light": {"capacity": 4, "luminance": 50},
        }
        assert simulator.light["luminance"] == 50

        await entity.async_turn_on(color_temp_kelvin=3000)
        color_payload = bus.requests[-2][3]["light"]
        assert color_payload == {
            "capacity": 6,
            "temperature": 9,
            "luminance": 50,
        }
        assert simulator.light["temperature"] == 9

        await entity.async_turn_on(
            brightness=255, color_temp_kelvin=2700)
        assert bus.requests[-3][3]["light"] == {
            "capacity": 6, "temperature": 1, "luminance": 100}
        assert bus.requests[-2][3]["light"] == {
            "capacity": 4, "luminance": 100}
        assert bus.requests[-1][3]["light"] == {"onoff": 1}

        await entity.async_turn_off()
        assert bus.requests[-1][3] == {
            "channel": 0, "light": {"onoff": 0}}
        simulator.emit_toggle()
        assert await wait_for(lambda: entity.is_on is False)

        assert not [
            request for request in bus.requests
            if request[2] in ("GET", "GETACK")
        ]
        assert bus.multiples == []
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


async def test_map100_purifier_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(Map100Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["map100"], ["pur1"])
    runtime = adapter.runtimes["pur1"]
    fan = runtime.entities["fan"].values
    try:
        assert await wait_for(lambda: bus.multiples)
        assert await wait_for(lambda: fan)
        assert fan == {"speed": 1, "max_speed": 1}
        assert runtime.entities["filter"].values["value"] == 73

        await adapter.async_send(
            "pur1", "Appliance.Control.Fan", "SET",
            {"fan": [{"channel": 0, "speed": 0}]})
        assert simulator.speed == 0
        assert fan["speed"] == 0

        simulator.life = 40
        simulator.emit()
        assert await wait_for(
            lambda: runtime.entities["filter"].values["value"] == 40)
    finally:
        await adapter.async_stop()


async def test_em06_energy_monitor_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(EMSimulator())
    adapter = await start_adapter_with_bus(hass, bus, ["em"], ["em1"])
    runtime = adapter.runtimes["em1"]
    try:
        assert len(runtime.entities) == 30
        assert {"power_1", "power_2", "voltage_1", "voltage_2",
                "current_1", "current_2", "consumption_1", "consumption_2",
                "power_factor_1", "power_factor_2"} <= set(runtime.entities)
        assert await wait_for(lambda: runtime.entities["power_2"].values)
        assert runtime.entities["power_2"].values["value"] == 1.2
        assert runtime.entities["voltage_2"].values["value"] == 230.0
        assert runtime.entities["consumption_2"].values["value"] == 45.0

        simulator.channels[2]["power"] = 900
        simulator.emit()
        assert await wait_for(
            lambda: runtime.entities["power_2"].values["value"] == 0.9)
    finally:
        await adapter.async_stop()


async def test_msxh0_spray_and_light_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(Msxh0Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["msxh0"], ["sx1"])
    runtime = adapter.runtimes["sx1"]
    try:
        assert await wait_for(lambda: runtime.entities["spray"].values)
        assert runtime.entities["spray"].values["value"] is False
        assert runtime.entities["light"].values["onoff"] == 0

        await adapter.async_send(
            "sx1", "Appliance.Control.Spray", "SET",
            {"spray": {"channel": 0, "mode": 1}})
        assert simulator.mode == 1
        assert runtime.entities["spray"].values["value"] is True
    finally:
        await adapter.async_stop()


async def test_hp110_power_and_light_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(HP110Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["hp110"], ["hp1"])
    runtime = adapter.runtimes["hp1"]
    try:
        assert await wait_for(lambda: runtime.entities["power"].values)
        assert runtime.entities["power"].values["onoff"] == 0
        assert runtime.entities["light"].values["brightness"] == 20

        await adapter.async_send(
            "hp1", "Appliance.Control.ToggleX", "SET",
            {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]})
        assert simulator.onoff == 1
        assert runtime.entities["power"].values["onoff"] == 1
    finally:
        await adapter.async_stop()
