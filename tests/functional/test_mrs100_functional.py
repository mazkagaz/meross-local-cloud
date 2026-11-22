"""F3/F7.1 — MRS100 behaviours and reconnect (H2, simulated device)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from device_simulator import ADJUST, CONFIG, POSITION, MRS100Simulator
from helpers import catalog_entry, wait_for

from custom_components.meross_local_cloud.broker_adapter import BrokerProfileAdapter


async def start_adapter(hass, simulator):
    coordinator = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key", token="t"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
    )
    with patch(
            "custom_components.meross_local_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=simulator), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_list_devices", AsyncMock(return_value=[
                    SimpleNamespace(uuid="u1")])), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(return_value={
                    "revision": "rev1", "count": 1})), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(return_value={
                    "schema_version": 1, "revision": "rev1",
                    "profiles": [catalog_entry("mrs100")]})):
        adapter = BrokerProfileAdapter(hass, coordinator)
        await adapter.async_start()
    assert await wait_for(
        lambda: adapter.runtimes["u1"].entities["cover"].values)
    return adapter


async def test_f3_1_open_close_stop(hass):
    simulator = MRS100Simulator()
    adapter = await start_adapter(hass, simulator)
    cover = adapter.runtimes["u1"].entities["cover"]
    try:
        await adapter.async_send(
            "u1", POSITION, "SET",
            {"position": {"channel": 0, "position": 100}})
        assert cover.values["position"] == 100
        assert simulator.state == 1

        await adapter.async_send(
            "u1", POSITION, "SET",
            {"position": {"channel": 0, "position": 0}})
        assert cover.values["position"] == 0
        assert simulator.state == 2

        await adapter.async_send(
            "u1", POSITION, "SET",
            {"position": {"channel": 0, "position": -1}})
        assert simulator.state == 0
    finally:
        await adapter.async_stop()


async def test_f3_2_positions(hass):
    simulator = MRS100Simulator()
    adapter = await start_adapter(hass, simulator)
    cover = adapter.runtimes["u1"].entities["cover"]
    try:
        for position in (0, 50, 100):
            await adapter.async_send(
                "u1", POSITION, "SET",
                {"position": {"channel": 0, "position": position}})
            assert cover.values["position"] == position
            assert simulator.position == position
    finally:
        await adapter.async_stop()


async def test_f3_3_durations_are_set_and_kept(hass):
    simulator = MRS100Simulator()
    adapter = await start_adapter(hass, simulator)
    runtime = adapter.runtimes["u1"]
    try:
        await adapter.async_send("u1", CONFIG, "SET", {
            "config": {
                "channel": 0,
                "signalOpen": 60000,
                "signalClose": 70000,
            },
        })

        assert simulator.config == {
            "signalOpen": 60000, "signalClose": 70000}
        assert runtime.entities["open_duration"].values["value"] == 60.0
        assert runtime.entities["close_duration"].values["value"] == 70.0
    finally:
        await adapter.async_stop()


async def test_f3_4_calibration_status(hass):
    simulator = MRS100Simulator()
    adapter = await start_adapter(hass, simulator)
    status = adapter.runtimes["u1"].entities["calibration_status"]
    try:
        await adapter.async_send(
            "u1", ADJUST, "SET",
            {"adjust": {"channel": 0, "value": 1}})
        assert status.values["value"] == 1

        simulator.push(adapter, ADJUST, {
            "adjust": [{"channel": 0, "status": 2}]})
        assert status.values["value"] == 2

        await adapter.async_send(
            "u1", ADJUST, "SET",
            {"adjust": {"channel": 0, "value": 2}})
        assert status.values["value"] == 2
    finally:
        await adapter.async_stop()


async def test_f7_1_reconnect_rehydrates_without_extra_gets(hass):
    simulator = MRS100Simulator()
    simulator.position = 40
    simulator.state = 0

    first = await start_adapter(hass, simulator)
    try:
        assert first.runtimes["u1"].entities["cover"].values[
            "position"] == 40
    finally:
        await first.async_stop()

    second = await start_adapter(hass, simulator)
    try:
        await asyncio.sleep(0)
        assert second.runtimes["u1"].entities["cover"].values[
            "position"] == 40
        assert len(simulator.multiples) == 2
        assert not [request for request in simulator.requests
                    if request[2] == "GET"]
    finally:
        await second.async_stop()
