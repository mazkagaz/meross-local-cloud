import logging
from typing import Optional, Dict

from homeassistant.core import HomeAssistant
from meross_iot.controller.device import BaseDevice
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.controller.mixins.diffuser_light import DiffuserLightMixin
from meross_iot.controller.mixins.toggle import ToggleMixin, ToggleXMixin
from meross_iot.model.enums import Namespace, LightMode
from meross_iot.manager import MerossManager
from meross_iot.model.http.device import HttpDeviceInfo
from meross_iot.model.enums import DiffuserLightMode
import homeassistant.util.color as color_util
from homeassistant.components.light import LightEntity
from homeassistant.components.light import ColorMode, \
    ATTR_HS_COLOR, ATTR_COLOR_TEMP_KELVIN, ATTR_BRIGHTNESS, ATTR_RGB_COLOR
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from . import MerossDevice
from .common import (DOMAIN, MANAGER, HA_LIGHT, DEVICE_LIST_COORDINATOR)
from .version import MEROSS_INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)

MIN_KELVIN = 2000
MAX_KELVIN = 6500


def _meross_temperature_from_kelvin(kelvin: int) -> float:
    kelvin = max(MIN_KELVIN, min(MAX_KELVIN, kelvin))
    return (kelvin - MIN_KELVIN) * 100 / (MAX_KELVIN - MIN_KELVIN)


def _kelvin_from_meross_temperature(value: float) -> int:
    value = max(0, min(100, value))
    return round(MIN_KELVIN + (value / 100) * (MAX_KELVIN - MIN_KELVIN))


def _supported_color_modes(supports_rgb: bool, supports_luminance: bool,
                           supports_temperature: bool) -> set[ColorMode]:
    """Build a Home Assistant-valid color mode set.

    ColorMode.WHITE is only legal alongside a color mode; a brightness-only
    light must use ColorMode.BRIGHTNESS instead.
    """
    modes = set()
    if supports_rgb:
        modes.add(ColorMode.RGB)
    if supports_temperature:
        modes.add(ColorMode.COLOR_TEMP)
    if not modes:
        modes.add(ColorMode.BRIGHTNESS if supports_luminance else ColorMode.ONOFF)
    return modes


def _active_color_mode(supports_rgb: bool, supports_luminance: bool,
                       supports_temperature: bool) -> ColorMode:
    if supports_rgb:
        return ColorMode.RGB
    if supports_temperature:
        return ColorMode.COLOR_TEMP
    if supports_luminance:
        return ColorMode.BRIGHTNESS
    return ColorMode.ONOFF


def _is_cover_light(device) -> bool:
    """Covers report ToggleX in their ability, but its payload is not usable.

    meross_lan ignores ToggleX for roller shutters/garage openers for the same
    reason; their light must be driven through Appliance.Control.Light.
    """
    abilities = getattr(device, "abilities", {}) or {}
    return (Namespace.ROLLER_SHUTTER_STATE.value in abilities
            or Namespace.GARAGE_DOOR_STATE.value in abilities)


def _cover_light_payload(channel: int, onoff: bool,
                         luminance: Optional[int] = None) -> Dict:
    """Build the CONTROL_LIGHT payload used by meross_lan for covers.

    A plain on/off is sent with the onoff field only. Luminance and the
    luminance capacity are added only when an actual brightness is requested.
    """
    light = {
        "channel": channel,
        "onoff": 1 if onoff else 0,
    }
    if onoff and luminance is not None:
        light["luminance"] = max(1, min(100, int(luminance)))
        light["capacity"] = LightMode.MODE_LUMINANCE.value
    return {"light": light}


class MerossOilDiffuserLightDevice(DiffuserLightMixin, BaseDevice):
    """
    Type hints helper
    """
    pass


class MerossLightDevice(LightMixin, BaseDevice):
    """
    Type hints helper
    """
    pass


class DiffuserLightEntityWrapper(MerossDevice, LightEntity):
    """Wrapper class to adapt the Meross OilDiffuserLight"""
    _device: MerossOilDiffuserLightDevice
    # For now, we assume OilDiffuserLight supports all the following features.
    # From Meross API it is in fact impossible to determine which exact features are supported by the device.
    _attr_supported_color_modes = {ColorMode.WHITE, ColorMode.RGB, ColorMode.COLOR_TEMP}

    def __init__(self,
                 channel: int,
                 device: MerossOilDiffuserLightDevice,
                 device_list_coordinator: DataUpdateCoordinator[Dict[str, HttpDeviceInfo]]):

        super().__init__(
            device=device,
            channel=channel,
            device_list_coordinator=device_list_coordinator,
            platform=HA_LIGHT)

    async def async_turn_off(self, **kwargs) -> None:
        await self._device.async_turn_off(channel=self._channel_id, skip_rate_limits=True)

    async def async_turn_on(self, **kwargs) -> None:
        if not self.is_on:
            await self._device.async_turn_on(channel=self._channel_id, skip_rate_limits=True)

        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            rgb = color_util.color_hsv_to_RGB(h, s, 100)
            _LOGGER.debug("color change: rgb=%r -- h=%r s=%r" % (rgb, h, s))
            await self._device.async_set_light_mode(channel=self._channel_id, mode=DiffuserLightMode.FIXED_RGB, rgb=rgb, onoff=True, skip_rate_limits=True)
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            temperature = _meross_temperature_from_kelvin(kelvin)
            _LOGGER.debug("temperature change: kelvin=%r meross=%r" % (kelvin, temperature))
            await self._device.async_set_light_mode(channel=self._channel_id, mode=DiffuserLightMode.FIXED_LUMINANCE, onoff=True, rgb=65293, brightness=temperature, skip_rate_limits=True)

        # Brightness must always be set, so take previous luminance if not explicitly set now.
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS] * 100 / 255
            _LOGGER.debug("brightness change: %r" % brightness)
            await self._device.async_set_light_mode(channel=self._channel_id, luminance=brightness, skip_rate_limits=True)

    @property
    def is_on(self) -> Optional[bool]:
        return self._device.get_light_is_on(channel=self._channel_id)

    @property
    def hs_color(self):
        rgb = self._device.get_light_rgb_color(channel=self._channel_id)
        if rgb is not None and isinstance(rgb, tuple) and len(rgb) == 3:
            return color_util.color_RGB_to_hs(*rgb)
        else:
            return None  # Return None if RGB value is not available

    @property
    def brightness(self):
        luminance = self._device.get_light_brightness()
        if luminance is not None:
            return float(luminance) / 100 * 255
        return None


class LightEntityWrapper(MerossDevice, LightEntity):
    """Wrapper class to adapt the Meross bulbs into the Homeassistant platform"""
    _device: MerossLightDevice

    def __init__(self,
                 channel: int,
                 device: MerossLightDevice,
                 device_list_coordinator: DataUpdateCoordinator[Dict[str, HttpDeviceInfo]]):

        super().__init__(
            device=device,
            channel=channel,
            device_list_coordinator=device_list_coordinator,
            platform=HA_LIGHT)
        self._last_onoff: Optional[bool] = None

    def _debug_state(self) -> str:
        parts = []
        try:
            parts.append(f"is_on={self.is_on}")
        except Exception:  # noqa: BLE001 - diagnostic only
            parts.append("is_on=?")
        try:
            parts.append(f"luminance={self._device.get_luminance(channel=self._channel_id)}")
        except Exception:  # noqa: BLE001 - diagnostic only
            parts.append("luminance=?")
        info = self._device._channel_light_status.get(self._channel_id)
        if info is None:
            parts.append("light_info=none")
        else:
            parts.append(
                f"light_info(onoff={info._onoff},lum={info._luminance},"
                f"rgb={info._rgb},temp={info._temperature})")
        parts.append(f"last_onoff={self._last_onoff}")
        return " ".join(parts)

    async def _async_set_cover_light(self, onoff: bool,
                                     brightness: Optional[int] = None) -> None:
        luminance = (
            round(brightness * 100 / 255) if brightness is not None else None
        )
        payload = _cover_light_payload(self._channel_id, onoff, luminance)
        _LOGGER.debug("cover light SET %s: %s", self._device.uuid, payload)
        try:
            result = await self._device._execute_command(
                method="SET", namespace=Namespace.CONTROL_LIGHT, payload=payload)
        except Exception as err:
            _LOGGER.debug("cover light SET %s failed: %s", self._device.uuid, err)
            raise
        _LOGGER.debug("cover light SET %s ack: %s", self._device.uuid, result)
        self._last_onoff = onoff
        self._device._update_channel_status(
            channel=self._channel_id,
            luminance=payload["light"].get("luminance"),
            onoff=payload["light"]["onoff"])

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.debug("turn_off %s channel=%s %s",
                      self._device.uuid, self._channel_id, self._debug_state())
        if _is_cover_light(self._device):
            await self._async_set_cover_light(False)
            return
        await self._device.async_turn_off(channel=self._channel_id, skip_rate_limits=True)

    async def async_turn_on(self, **kwargs) -> None:
        device = self._device
        toggled = isinstance(device, (ToggleXMixin, ToggleMixin))
        _LOGGER.debug(
            "turn_on %s channel=%s kwargs=%s toggled=%s %s",
            device.uuid, self._channel_id, kwargs, toggled,
            self._debug_state())
        if _is_cover_light(device):
            await self._async_set_cover_light(True, kwargs.get(ATTR_BRIGHTNESS))
            return
        if not kwargs and not toggled:
            # Some devices keep reporting onoff=1 even when the light is off.
            # meross_iot then omits the onoff field and sends nothing; include
            # a luminance value so the CONTROL_LIGHT command is emitted.
            try:
                luminance = device.get_luminance(channel=self._channel_id)
            except Exception:  # noqa: BLE001 - state may not be available yet
                luminance = None
            await device.async_set_light_color(
                channel=self._channel_id,
                onoff=True,
                luminance=luminance if luminance else 100,
                skip_rate_limits=True)
            return

        await device.async_turn_on(channel=self._channel_id, skip_rate_limits=True)

        # Color is taken from either of these 2 values, but not both.
        if ATTR_RGB_COLOR in kwargs:
            await self._device.async_set_light_color(channel=self._channel_id, rgb=kwargs[ATTR_RGB_COLOR], onoff=True, skip_rate_limits=True)
        elif ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            rgb = color_util.color_hsv_to_RGB(h, s, 100)
            _LOGGER.debug("color change: rgb=%r -- h=%r s=%r" % (rgb, h, s))
            await self._device.async_set_light_color(channel=self._channel_id, rgb=rgb, onoff=True, skip_rate_limits=True)
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            temperature = _meross_temperature_from_kelvin(kelvin)
            _LOGGER.debug("temperature change: kelvin=%r meross=%r" % (kelvin, temperature))
            await self._device.async_set_light_color(channel=self._channel_id, temperature=temperature, skip_rate_limits=True)

        # Brightness must always be set, so take previous luminance if not explicitly set now.
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS] * 100 / 255
            _LOGGER.debug("brightness change: %r" % brightness)
            await self._device.async_set_light_color(channel=self._channel_id, luminance=brightness, skip_rate_limits=True)

    @property
    def supported_color_modes(self) -> set[ColorMode] | set[str] | None:
        return _supported_color_modes(
            supports_rgb=self._device.get_supports_rgb(channel=self._channel_id),
            supports_luminance=self._device.get_supports_luminance(channel=self._channel_id),
            supports_temperature=self._device.get_supports_temperature(channel=self._channel_id),
        )

    @property
    def is_on(self) -> Optional[bool]:
        if _is_cover_light(self._device):
            info = self._device._channel_light_status.get(self._channel_id)
            if info is not None and info.is_on is not None:
                return info.is_on
            return self._last_onoff
        return self._device.get_light_is_on(channel=self._channel_id)

    @property
    def brightness(self):
        if not self._device.get_supports_luminance(self._channel_id):
            return None

        luminance = self._device.get_luminance()
        if luminance is not None:
            return float(luminance) / 100 * 255

        return None

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the color mode of the light."""
        # TODO: we need support from low-level library in order to keep track of mode that haas been set.
        return _active_color_mode(
            supports_rgb=self._device.get_supports_rgb(channel=self._channel_id),
            supports_luminance=self._device.get_supports_luminance(channel=self._channel_id),
            supports_temperature=self._device.get_supports_temperature(channel=self._channel_id),
        )

    @property
    def hs_color(self):
        rgb = self._device.get_rgb_color(channel=self._channel_id)
        if rgb is not None and isinstance(rgb, tuple) and len(rgb) == 3:
            return color_util.color_RGB_to_hs(*rgb)
        else:
            return None  # Return None if RGB value is not available

    @property
    def color_temp_kelvin(self) -> int | None:
        if self._device.get_supports_temperature(channel=self._channel_id):
            value = self._device.get_color_temperature()
            return _kelvin_from_meross_temperature(value)
        return None


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    def entity_adder_callback():
        """Discover and adds new Meross entities"""
        manager: MerossManager = hass.data[DOMAIN][MANAGER]  # type
        coordinator = hass.data[DOMAIN][DEVICE_LIST_COORDINATOR]
        devices = manager.find_devices()

        new_entities = []

        light_devs = filter(lambda d: isinstance(d, LightMixin), devices)
        for d in light_devs:
            channels = [c.index for c in (d.channels or [])] or [0]
            _LOGGER.debug(
                "Light device %s (%s) [integration %s]: abilities=%s toggle=%s channels=%s",
                d.name, d.uuid, MEROSS_INTEGRATION_VERSION,
                sorted((d.abilities or {}).keys()),
                isinstance(d, (ToggleXMixin, ToggleMixin)), channels)
            for channel_index in channels:
                w = LightEntityWrapper(device=d, channel=channel_index, device_list_coordinator=coordinator)
                if w.unique_id not in hass.data[DOMAIN]["ADDED_ENTITIES_IDS"]:
                    new_entities.append(w)

        diffuser_devs = filter(lambda d: isinstance(d, DiffuserLightMixin), devices)
        for d in diffuser_devs:
            channels = [c.index for c in (d.channels or [])] or [0]
            for channel_index in channels:
                w = DiffuserLightEntityWrapper(device=d, channel=channel_index, device_list_coordinator=coordinator)
                if w.unique_id not in hass.data[DOMAIN]["ADDED_ENTITIES_IDS"]:
                    new_entities.append(w)

        async_add_entities(new_entities, True)

    coordinator = hass.data[DOMAIN][DEVICE_LIST_COORDINATOR]
    coordinator.async_add_listener(entity_adder_callback)
    # Run the entity adder a first time during setup
    entity_adder_callback()


# TODO: Implement entry unload
# TODO: Unload entry
# TODO: Remove entry


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass
