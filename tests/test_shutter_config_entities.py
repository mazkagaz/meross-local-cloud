import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.entity_component import EntityComponent
from meross_iot.controller.mixins.roller_shutter import RollerShutterTimerMixin
from meross_iot.model.enums import OnlineStatus

from custom_components.meross_cloud.broker_config import RollerShutterConfigCache
from custom_components.meross_cloud.common import (
    DOMAIN,
    DEVICE_LIST_COORDINATOR,
    MANAGER,
    SHUTTER_CONFIG_CACHE,
)
from custom_components.meross_cloud.number import (
    async_setup_entry as setup_numbers,
)

_LOGGER = logging.getLogger(__name__)


class FakeShutter(RollerShutterTimerMixin):
    def __init__(self):
        self.uuid = "mrs100-test"
        self.internal_id = "mrs100-test"
        self.name = "Test Shutter"
        self.type = "mrs100"
        self.online_status = OnlineStatus.ONLINE
        self.channels = [SimpleNamespace(
            index=0, name="Main", type=None, is_master_channel=True)]
        self.updates = 0
        self.set_calls = []
        self._shutter__config_by_channel = {
            0: {"signalOpen": 30000, "signalClose": 40000},
        }

    async def async_update(self):
        self.updates += 1

    def check_full_update_done(self):
        return True

    def get_open_timer_duration_millis(self, channel=0):
        return self._shutter__config_by_channel.get(channel, {}).get(
            "signalOpen")

    def get_close_timer_duration_millis(self, channel=0):
        return self._shutter__config_by_channel.get(channel, {}).get(
            "signalClose")

    async def async_set_config(self, open_timer_seconds,
                               close_timer_seconds, channel=0):
        self.set_calls.append(
            (open_timer_seconds, close_timer_seconds, channel))
        self._shutter__config_by_channel[channel] = {
            "signalOpen": open_timer_seconds * 1000,
            "signalClose": close_timer_seconds * 1000,
        }


class FakeCoordinator:
    def __init__(self, device_uuid):
        self.data = {
            device_uuid: SimpleNamespace(online_status=OnlineStatus.ONLINE),
        }
        self.last_update_success = True

    def async_add_listener(self, callback):
        return lambda: None


class FakeManager:
    def __init__(self, device):
        self.device = device

    def find_devices(self, device_class=None, **kwargs):
        if device_class and not any(
                isinstance(self.device, cls) for cls in device_class):
            return []
        return [self.device]


async def setup(hass, fetch, with_cache=True):
    device = FakeShutter()
    cache = RollerShutterConfigCache(SimpleNamespace(), fetch=fetch)
    hass.data[DOMAIN] = {
        MANAGER: FakeManager(device),
        DEVICE_LIST_COORDINATOR: FakeCoordinator(device.uuid),
        "ADDED_ENTITIES_IDS": set(),
    }
    if with_cache:
        hass.data[DOMAIN][SHUTTER_CONFIG_CACHE] = cache

    component = EntityComponent(_LOGGER, "number", hass)

    def add_entities(entities, update_before_add=False):
        hass.async_create_task(component.async_add_entities(
            entities, update_before_add=update_before_add))

    await setup_numbers(hass, None, add_entities)
    await hass.async_block_till_done()

    entities = {entity._timer: entity for entity in component.entities}
    return SimpleNamespace(
        hass=hass, device=device, cache=cache,
        open=entities["open"], close=entities["close"],
    )


def payload(open_ms=45000, close_ms=50000):
    return {
        "mrs100-test": {
            "config": [{
                "channel": 0,
                "signalOpen": open_ms,
                "signalClose": close_ms,
            }],
        },
    }


async def test_p3_cache_is_preferred_over_device_updates(hass):
    fetch = AsyncMock(return_value=payload())

    runtime = await setup(hass, fetch)

    assert runtime.open.native_value == 45
    assert runtime.close.native_value == 50
    assert runtime.device.updates == 0
    fetch.assert_awaited_once()


async def test_missing_endpoint_falls_back_to_the_device(hass):
    fetch = AsyncMock(side_effect=RuntimeError("HTTP 404"))

    runtime = await setup(hass, fetch)

    assert runtime.open.native_value == 30
    assert runtime.close.native_value == 40
    assert runtime.device.updates > 0
    assert "RuntimeError" in runtime.cache.last_error


async def test_set_updates_the_p3_cache(hass):
    fetch = AsyncMock(return_value=payload())
    runtime = await setup(hass, fetch)

    await runtime.open.async_set_native_value(60)

    assert runtime.device.set_calls[-1] == (60, 50, 0)
    state = runtime.cache.cached_channel("mrs100-test", 0)
    assert state.signal_open_ms == 60000
    assert state.signal_close_ms == 50000
    assert runtime.open.native_value == 60
    assert runtime.close.native_value == 50


async def test_no_cache_keeps_the_previous_behaviour(hass):
    fetch = AsyncMock(return_value=payload())

    runtime = await setup(hass, fetch, with_cache=False)

    assert runtime.open.native_value == 30
    assert runtime.device.updates > 0
    fetch.assert_not_awaited()
