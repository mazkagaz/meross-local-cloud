# Copyright (c) 2026 the MRS100 fork contributors.
# MIT License. Part of the MRS100/local-broker HACS fork.
"""Roller-shutter timing entities for Meross cover devices.

These entities expose Appliance.RollerShutter.Config signalOpen/signalClose
(the movement duration in seconds) as Home Assistant number entities. The
local-broker add-on persists and replays this configuration after reconnects.
"""
import logging
from typing import Dict

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
    NumberDeviceClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from meross_iot.controller.mixins.roller_shutter import RollerShutterTimerMixin
from meross_iot.manager import MerossManager
from meross_iot.model.http.device import HttpDeviceInfo

from . import MerossDevice
from .common import DOMAIN, MANAGER, HA_NUMBER, DEVICE_LIST_COORDINATOR

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMER_SECONDS = 50
MIN_TIMER_SECONDS = 10
MAX_TIMER_SECONDS = 120


class RollerShutterTimerNumber(MerossDevice, NumberEntity):
    """Open/close duration for one roller-shutter channel."""

    _device: RollerShutterTimerMixin

    def __init__(self,
                 timer: str,
                 device: RollerShutterTimerMixin,
                 channel: int,
                 device_list_coordinator: DataUpdateCoordinator[Dict[str, HttpDeviceInfo]]):
        super().__init__(
            device=device,
            channel=channel,
            device_list_coordinator=device_list_coordinator,
            platform=HA_NUMBER,
            supplementary_classifiers=[f"{timer}_timer"])
        if timer not in ("open", "close"):
            raise ValueError(f"Invalid roller-shutter timer {timer!r}")
        self._timer = timer
        self._entity_name = f"{device.name} - {'Open' if timer == 'open' else 'Close'} duration"
        self._attr_native_min_value = MIN_TIMER_SECONDS
        self._attr_native_max_value = MAX_TIMER_SECONDS
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_device_class = NumberDeviceClass.DURATION
        self._attr_mode = NumberMode.BOX
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_icon = "mdi:timer-cog-outline"

    def _timer_millis(self, timer: str):
        try:
            if timer == "open":
                return self._device.get_open_timer_duration_millis(channel=self._channel_id)
            return self._device.get_close_timer_duration_millis(channel=self._channel_id)
        except Exception:
            # The config may not have been fetched yet; use the cached mixin dict.
            configs = getattr(self._device, "_shutter__config_by_channel", {}) or {}
            config = configs.get(self._channel_id) or {}
            return config.get("signalOpen" if timer == "open" else "signalClose")

    def _timer_seconds(self, timer: str) -> int:
        millis = self._timer_millis(timer)
        if millis is None:
            return DEFAULT_TIMER_SECONDS
        return max(MIN_TIMER_SECONDS, min(MAX_TIMER_SECONDS, int(round(millis / 1000))))

    @property
    def native_value(self) -> float | None:
        millis = self._timer_millis(self._timer)
        if millis is None:
            return None
        return round(millis / 1000, 0)

    async def async_set_native_value(self, value: float) -> None:
        seconds = int(round(value))
        if self._timer == "open":
            open_seconds, close_seconds = seconds, self._timer_seconds("close")
        else:
            open_seconds, close_seconds = self._timer_seconds("open"), seconds
        await self._device.async_set_config(
            open_timer_seconds=open_seconds,
            close_timer_seconds=close_seconds,
            channel=self._channel_id,
        )
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    def entity_adder_callback():
        manager: MerossManager = hass.data[DOMAIN][MANAGER]
        coordinator = hass.data[DOMAIN][DEVICE_LIST_COORDINATOR]
        devices = manager.find_devices(device_class=[RollerShutterTimerMixin])
        new_entities = []
        for device in devices:
            channels = [c.index for c in (device.channels or [])]
            if not channels:
                channels = [0]
            for channel_index in channels:
                for timer in ("open", "close"):
                    entity = RollerShutterTimerNumber(
                        timer=timer,
                        device=device,
                        channel=channel_index,
                        device_list_coordinator=coordinator,
                    )
                    if entity.unique_id not in hass.data[DOMAIN]["ADDED_ENTITIES_IDS"]:
                        new_entities.append(entity)
        async_add_entities(new_entities, True)

    coordinator = hass.data[DOMAIN][DEVICE_LIST_COORDINATOR]
    coordinator.async_add_listener(entity_adder_callback)
    entity_adder_callback()


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass
