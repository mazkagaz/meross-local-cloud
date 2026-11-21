"""F3.6/F3.10 — MSS310 and hub flows over the in-memory MQTT bus."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from device_simulator import HubSimulator, MSS310Simulator, MSS425Simulator
from helpers import start_adapter_with_bus, wait_for
from mqtt_bus import InMemoryMqttBus

from custom_components.meross_cloud.broker_adapter import BrokerProfileAdapter

TOGGLE = "Appliance.Control.ToggleX"
ELECTRICITY = "Appliance.Control.Electricity"
MTS_MODE = "Appliance.Hub.Mts100.Mode"
MTS_TEMPERATURE = "Appliance.Hub.Mts100.Temperature"


async def test_mss310_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(MSS310Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["mss310"], ["u1"])
    runtime = adapter.runtimes["u1"]
    try:
        assert await wait_for(lambda: bus.multiples)
        assert await wait_for(
            lambda: runtime.entities["switch"].values)
        assert runtime.entities["switch"].values["onoff"] == 1
        assert {request[0] for request in bus.multiples[0][1]} == {
            TOGGLE, ELECTRICITY}

        await adapter.async_send("u1", TOGGLE, "SET", {
            "channel": 0, "togglex": [{"channel": 0, "onoff": 0}]})
        assert simulator.onoff == 0
        assert runtime.entities["switch"].values["onoff"] == 0

        simulator.power = 99
        simulator.emit(ELECTRICITY, {
            "channel": 0,
            "electricity": {"power": 99, "voltage": 2300, "current": 50},
        })
        assert runtime.entities["power"].values["value"] == 99

        bus.offline.add("u1")
        adapter.schedulers["u1"].request_refresh()
        assert await wait_for(lambda: adapter.schedulers["u1"].errors >= 1)
        bus.offline.discard("u1")
        adapter.schedulers["u1"].request_refresh()
        assert await wait_for(
            lambda: adapter.schedulers["u1"].errors == 1
            and runtime.entities["switch"].values)
    finally:
        await adapter.async_stop()


async def test_hub_subdevices_over_the_bus(hass):
    bus = InMemoryMqttBus()
    hub = bus.add(HubSimulator())
    adapter = await start_adapter_with_bus(hass, bus, ["msh300"], ["hub1"])
    runtime = adapter.runtimes["hub1"]
    try:
        assert adapter.subdevices_matched == 3
        assert set(runtime.subdevices) == {"sub1", "sensor1", "valve1"}
        assert await wait_for(lambda: runtime.entities["online"].values)

        hub.push_all()
        assert await wait_for(lambda: "value" in runtime.subdevices[
            "sub1"].entities["temperature"].values)
        assert runtime.subdevices["sub1"].entities[
            "temperature"].values["value"] == 21.5
        assert runtime.subdevices["sensor1"].entities[
            "temperature"].values["value"] == 21.5
        climate = runtime.subdevices["valve1"].entities["climate"].values
        assert climate["current_temperature"] == 22.0
        assert climate["target_temperature"] == 20.0

        await adapter.async_send("hub1", MTS_MODE, "SET", {
            "mode": [{"id": "valve1", "state": 0}]})
        assert hub.valve["mode"] == 0
        hub.emit("Appliance.Hub.Mts100.All")
        await asyncio.sleep(0)
        assert climate["mode"] == 0

        await adapter.async_send("hub1", MTS_TEMPERATURE, "SET", {
            "temperature": [{"id": "valve1", "currentSet": 50}]})
        assert hub.valve["currentSet"] == 50
        hub.emit("Appliance.Hub.Mts100.All")
        await asyncio.sleep(0)
        assert climate["target_temperature"] == 25.0
    finally:
        await adapter.async_stop()


async def test_mss425_over_the_bus(hass):
    bus = InMemoryMqttBus()
    simulator = bus.add(MSS425Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["mss425"], ["strip1"])
    runtime = adapter.runtimes["strip1"]
    try:
        assert set(runtime.entities) == {
            "outlet_0", "outlet_1", "outlet_2"}
        assert await wait_for(
            lambda: all(entity.values for entity in runtime.entities.values()))
        assert runtime.entities["outlet_0"].values["onoff"] == 1
        assert runtime.entities["outlet_2"].values["onoff"] == 1

        await adapter.async_send("strip1", TOGGLE, "SET", {
            "channel": 1,
            "togglex": [{"channel": 1, "onoff": 0}]})
        assert simulator.onoff[1] == 0
        assert runtime.entities["outlet_1"].values["onoff"] == 0
        assert runtime.entities["outlet_0"].values["onoff"] == 1

        simulator.onoff[2] = 0
        simulator.emit()
        assert await wait_for(
            lambda: runtime.entities["outlet_2"].values["onoff"] == 0)
    finally:
        await adapter.async_stop()
