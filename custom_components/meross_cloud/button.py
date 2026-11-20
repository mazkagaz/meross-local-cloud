"""Roller-shutter calibration buttons for Meross cover devices.

Calibration uses Appliance.RollerShutter.Adjust. See calibration.py for the
raw-namespace command path and status polling.
"""
import logging
from typing import Dict

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from meross_iot.controller.mixins.roller_shutter import RollerShutterTimerMixin
from meross_iot.manager import MerossManager
from meross_iot.model.http.device import HttpDeviceInfo

from . import MerossDevice
from .calibration import (
    ADJUST_VALUE_START,
    ADJUST_VALUE_STOP,
    async_send_adjust,
    async_start_monitor,
    async_stop_monitor,
    set_adjust_status,
)
from .common import (
    DOMAIN, MANAGER, HA_BUTTON, DEVICE_LIST_COORDINATOR, PROFILE_ONLY,
)
from .profile_entities import async_setup_profile_entities

_LOGGER = logging.getLogger(__name__)


class RollerShutterCalibrationButton(MerossDevice, ButtonEntity):
    """Start or stop roller-shutter calibration on one channel."""

    _device: RollerShutterTimerMixin

    def __init__(self,
                 action: str,
                 device: RollerShutterTimerMixin,
                 channel: int,
                 device_list_coordinator: DataUpdateCoordinator[Dict[str, HttpDeviceInfo]]):
        if action not in ("calibrate", "stop_calibration"):
            raise ValueError(f"Invalid roller-shutter calibration action {action!r}")
        super().__init__(
            device=device,
            channel=channel,
            device_list_coordinator=device_list_coordinator,
            platform=HA_BUTTON,
            supplementary_classifiers=[action])
        self._action = action
        self._value = ADJUST_VALUE_START if action == "calibrate" else ADJUST_VALUE_STOP
        label = "Start calibration" if action == "calibrate" else "Stop calibration"
        self._entity_name = f"{device.name} - {label}"
        self._attr_icon = "mdi:autorenew" if action == "calibrate" else "mdi:stop-circle-outline"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        _LOGGER.info("Sending roller-shutter calibration action %s (value=%d) to %s channel %d",
                     self._action, self._value, self._device.uuid, self._channel_id)
        try:
            response = await async_send_adjust(self._device, self._channel_id, self._value)
        except Exception as err:
            _LOGGER.exception("Calibration command failed for %s channel %d",
                              self._device.uuid, self._channel_id)
            raise HomeAssistantError(
                f"Calibration command failed for {self.name}: {err}") from err

        _LOGGER.debug("Calibration SETACK for %s channel %d: %s",
                      self._device.uuid, self._channel_id, response)
        if self._value == ADJUST_VALUE_START:
            set_adjust_status(self.hass, self._device.uuid, self._channel_id, "in_progress")
            async_start_monitor(self.hass, self._device, self._channel_id)
        else:
            async_stop_monitor(self.hass, self._device.uuid, self._channel_id)
            set_adjust_status(self.hass, self._device.uuid, self._channel_id, "stopped")
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    async_setup_profile_entities(
        hass, config_entry, HA_BUTTON, async_add_entities)
    if PROFILE_ONLY and MANAGER not in hass.data[DOMAIN]:
        return

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
                for action in ("calibrate", "stop_calibration"):
                    entity = RollerShutterCalibrationButton(
                        action=action,
                        device=device,
                        channel=channel_index,
                        device_list_coordinator=coordinator,
                    )
                    if entity.unique_id not in hass.data[DOMAIN]["ADDED_ENTITIES_IDS"]:
                        new_entities.append(entity)
        async_add_entities(new_entities, False)

    coordinator = hass.data[DOMAIN][DEVICE_LIST_COORDINATOR]
    coordinator.async_add_listener(entity_adder_callback)
    entity_adder_callback()


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass
