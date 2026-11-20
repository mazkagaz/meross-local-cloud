"""D5-e: degraded scenarios around catalog matching and transport state."""
from device_simulator import MSS310Simulator
from helpers import entry, setup_entities, start_adapter_with_bus
from mqtt_bus import InMemoryMqttBus

from homeassistant.helpers import issue_registry as ir

from custom_components.meross_cloud.broker_adapter import (
    unsupported_device_issue,
)
from custom_components.meross_cloud.common import DOMAIN, HA_SWITCH


async def test_unsupported_device_repair_is_created_and_cleared(hass):
    bus = InMemoryMqttBus()
    bus.add(MSS310Simulator())
    first = await start_adapter_with_bus(hass, bus, [], ["u1"])
    try:
        issue = ir.async_get(hass).async_get_issue(
            DOMAIN, unsupported_device_issue("u1"))
        assert issue is not None
        assert issue.translation_key == "unsupported_device"
        assert first.summary()["devices_unmatched"] == 1
    finally:
        await first.async_stop()

    second = await start_adapter_with_bus(hass, bus, ["mss310"], ["u1"])
    try:
        assert ir.async_get(hass).async_get_issue(
            DOMAIN, unsupported_device_issue("u1")) is None
        assert second.summary()["devices_matched"] == 1
    finally:
        await second.async_stop()


async def test_transport_disconnect_marks_entities_unavailable(hass):
    bus = InMemoryMqttBus()
    bus.add(MSS310Simulator())
    adapter = await start_adapter_with_bus(hass, bus, ["mss310"], ["u1"])
    switches = await setup_entities(hass, adapter, HA_SWITCH, entry())
    entity = next(iter(switches.entities))
    try:
        assert entity.available is True

        bus.connected = False
        adapter._on_transport_state(False)
        await hass.async_block_till_done()
        assert entity.available is False

        bus.connected = True
        adapter._on_transport_state(True)
        await hass.async_block_till_done()
        assert entity.available is True
    finally:
        await adapter.async_stop()
