"""Home Assistant entities built from compiled device profiles.

They use the central scheduler/runtime and preserve the historical
unique_id and device-registry identifiers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.button import ButtonEntity
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.components.humidifier import HumidifierEntity
from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import Entity, EntityCategory

from .broker_config import ChannelState
from .common import (
    BROKER_ADAPTER,
    DOMAIN,
    SHUTTER_CONFIG_CACHE,
    calculate_id,
    device_internal_id,
)
from .profiles.paths import substitute

_LOGGER = logging.getLogger(__name__)

_ENTITY_CATEGORIES = {
    "config": EntityCategory.CONFIG,
    "diagnostic": EntityCategory.DIAGNOSTIC,
}

_ADJUST_STATUS_NAMES = {
    0: "success",
    1: "timeout",
    2: "motor_blocked",
    3: "failed_3",
    4: "failed_4",
    5: "failed_5",
    6: "failed_6",
}


def _has_quirk(spec, name: str) -> bool:
    return any(quirk.get("name") == name for quirk in spec.quirks)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _enum(value: Optional[str], enum_type):
    if not value:
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in ("on", "true", "1")
    return bool(value)


def _device_info(device_uuid: str, subdevice_id: Optional[str] = None,
                 template=None, descriptor=None) -> Dict[str, Any]:
    if subdevice_id is not None:
        return {
            "identifiers": {
                (DOMAIN, device_internal_id(device_uuid, subdevice_id))},
            "name": (template.name if template is not None else None)
            or subdevice_id,
            "manufacturer": "Meross",
            "via_device": (DOMAIN, device_internal_id(device_uuid)),
        }
    descriptor = descriptor or {}
    info = {
        "identifiers": {(DOMAIN, device_internal_id(device_uuid))},
        "name": descriptor.get("name") or device_uuid,
        "manufacturer": "Meross",
    }
    if descriptor.get("type"):
        info["model"] = descriptor["type"]
    if descriptor.get("firmware"):
        info["sw_version"] = descriptor["firmware"]
    if descriptor.get("hardware"):
        info["hw_version"] = descriptor["hardware"]
    return info


class ProfileBaseEntity(Entity):
    """Common runtime plumbing for one compiled entity."""

    _attr_should_poll = False

    def __init__(self, adapter, device_uuid: str, runtime, spec,
                 subdevice: Optional[Tuple[str, Any]] = None) -> None:
        self._adapter = adapter
        self._device_uuid = device_uuid
        self._runtime = runtime
        self._spec = spec
        self._subdevice_id, self._template = (
            subdevice if subdevice is not None else (None, None))
        self._remove_listener = None
        self._remove_adapter_listener = None
        self._attr_unique_id = calculate_id(
            spec.platform,
            device_internal_id(device_uuid, self._subdevice_id),
            spec.channel if spec.channel is not None else 0,
            list(spec.legacy_classifiers) or None)
        self._attr_name = spec.name or spec.key
        self._attr_entity_category = _ENTITY_CATEGORIES.get(
            spec.entity_category)

    @property
    def available(self) -> bool:
        return self._adapter.device_available(self._device_uuid)

    @property
    def device_info(self) -> Dict[str, Any]:
        descriptor = getattr(self._adapter, "descriptors", {}).get(
            self._device_uuid)
        return _device_info(
            self._device_uuid, self._subdevice_id, self._template,
            descriptor)

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self._runtime.add_listener(
            self._on_runtime_update)
        self._remove_adapter_listener = self._adapter.add_listener(
            self._on_runtime_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        if self._remove_adapter_listener is not None:
            self._remove_adapter_listener()
            self._remove_adapter_listener = None

    def _on_runtime_update(self) -> None:
        self.hass.loop.call_soon_threadsafe(self._write_state)

    def _write_state(self) -> None:
        try:
            self.async_write_ha_state()
        except Exception:  # noqa: BLE001 - entity may already be removed
            _LOGGER.debug("Unable to refresh %s", self._attr_unique_id,
                          exc_info=True)

    def _values(self) -> Dict[str, Any]:
        if self._subdevice_id is not None:
            runtime = self._runtime.subdevices.get(self._subdevice_id)
            state = runtime.entities.get(self._spec.key) if runtime else None
        else:
            state = self._runtime.entities.get(self._spec.key)
        return dict(state.values) if state is not None else {}

    def _command_payload(self, command: str, value: Any = None):
        spec = self._spec.commands.get(command)
        if spec is None:
            return None
        values = {"channel": self._spec.channel, "id": self._subdevice_id}
        if value is not None:
            if spec.value_scale is not None:
                value = value * spec.value_scale
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
            values["value"] = value
        return spec, substitute(spec.payload, values)

    async def _send(self, command: str, value: Any = None) -> None:
        prepared = self._command_payload(command, value)
        if prepared is None:
            return
        spec, payload = prepared
        await self._adapter.async_send(
            self._device_uuid, spec.namespace, "SET", payload)

    async def _send_priority(self, command: str, value: Any = None) -> None:
        prepared = self._command_payload(command, value)
        if prepared is None:
            return
        spec, payload = prepared
        await self._adapter.async_send_priority(
            self._device_uuid, spec.namespace, "SET", payload)


class ProfileSwitch(ProfileBaseEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return _as_bool(self._values().get("onoff"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send("turn_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send("turn_off")


class ProfileLight(ProfileBaseEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        fields = self._spec.state.fields if self._spec.state else {}
        if "rgb" in fields:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        elif "brightness" in fields:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool:
        values = self._values()
        if "onoff" in values:
            return _as_bool(values.get("onoff"))
        return bool(values.get("brightness"))

    @property
    def brightness(self) -> Optional[int]:
        value = self._values().get("brightness")
        if value is None:
            return None
        return round(float(value) * 255 / 100)

    @property
    def rgb_color(self):
        value = self._values().get("rgb")
        if value is None:
            return None
        rgb = int(value)
        return ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get("brightness")
        rgb_color = kwargs.get("rgb_color")
        if rgb_color is not None:
            r, g, b = rgb_color
            await self._send("set_rgb", (r << 16) | (g << 8) | b)
        if brightness is not None:
            await self._send("set_brightness",
                             round(brightness * 100 / 255))
        await self._send("turn_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send("turn_off")


class ProfileSensor(ProfileBaseEntity, SensorEntity):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._spec.unit
        self._attr_device_class = _enum(
            self._spec.device_class, SensorDeviceClass)
        self._adjust_status = _has_quirk(
            self._spec, "adjust_status_names")

    @property
    def native_value(self):
        value = self._values().get("value")
        if self._adjust_status and _is_int(value):
            return _ADJUST_STATUS_NAMES.get(
                value, f"failed_{value}")
        return value if isinstance(value, (int, float, str)) else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if not self._adjust_status:
            return {}
        value = self._values().get("value")
        return {
            "status_code": value if _is_int(value) else None,
            "channel": self._spec.channel,
        }


class ProfileBinarySensor(ProfileBaseEntity, BinarySensorEntity):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_device_class = _enum(
            self._spec.device_class, BinarySensorDeviceClass)

    @property
    def is_on(self) -> Optional[bool]:
        value = self._values().get("value")
        return None if value is None else _as_bool(value)


class ProfileCover(ProfileBaseEntity, CoverEntity):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_device_class = _enum(
            self._spec.device_class, CoverDeviceClass)
        features = CoverEntityFeature(0)
        if "open" in self._spec.commands:
            features |= CoverEntityFeature.OPEN
        if "close" in self._spec.commands:
            features |= CoverEntityFeature.CLOSE
        if "stop" in self._spec.commands:
            features |= CoverEntityFeature.STOP
        if "set_position" in self._spec.commands:
            features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features

    @property
    def current_cover_position(self) -> Optional[int]:
        if _has_quirk(self._spec, "garage_door"):
            return None
        value = self._values().get("position")
        return int(value) if value is not None else None

    @property
    def is_closed(self) -> Optional[bool]:
        values = self._values()
        if _has_quirk(self._spec, "garage_door"):
            opened = values.get("open")
            return None if opened is None else not bool(opened)
        position = values.get("position")
        if position is not None:
            return int(position) == 0
        state = values.get("state")
        if state is not None:
            return int(state) == 2
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._send("open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._send("close")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._send_priority("stop")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._send("set_position", kwargs.get("position"))


class ProfileNumber(ProfileBaseEntity, NumberEntity):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_native_min_value = (
            self._spec.min_value if self._spec.min_value is not None else 0)
        self._attr_native_max_value = (
            self._spec.max_value if self._spec.max_value is not None else 100)
        self._attr_native_step = self._spec.step or 1
        self._attr_native_unit_of_measurement = self._spec.unit
        self._attr_device_class = _enum(
            self._spec.device_class, NumberDeviceClass)
        self._config_persist = _has_quirk(self._spec, "config_persist")
        self._p3_state: Optional[ChannelState] = None

    @property
    def _config_cache(self):
        if not self._config_persist or self.hass is None:
            return None
        return self.hass.data.get(DOMAIN, {}).get(SHUTTER_CONFIG_CACHE)

    async def async_added_to_hass(self) -> None:
        await self._async_refresh_cache()
        await super().async_added_to_hass()

    async def _async_refresh_cache(self) -> None:
        cache = self._config_cache
        if cache is None:
            return
        try:
            state = await cache.async_get_channel(
                self._device_uuid,
                self._spec.channel if self._spec.channel is not None else 0)
        except Exception:  # noqa: BLE001 - cache failures fall back
            state = None
        if state is not None:
            self._p3_state = state

    def _cached_timer_ms(self) -> Optional[int]:
        if self._p3_state is None:
            return None
        if "open_timer" in self._spec.legacy_classifiers:
            return self._p3_state.signal_open_ms
        return self._p3_state.signal_close_ms

    @property
    def native_value(self) -> Optional[float]:
        cached = self._cached_timer_ms()
        if cached is not None:
            return round(cached / 1000, 0)
        value = self._values().get("value")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        await self._send("set_value", value)
        cache = self._config_cache
        if cache is None:
            return
        millis = int(round(value * 1000))
        channel = self._spec.channel if self._spec.channel is not None else 0
        if "open_timer" in self._spec.legacy_classifiers:
            cache.update_from_set(
                self._device_uuid, channel, signal_open_ms=millis)
        else:
            cache.update_from_set(
                self._device_uuid, channel, signal_close_ms=millis)
        self._p3_state = cache.cached_channel(self._device_uuid, channel)
        self.async_write_ha_state()


class ProfileButton(ProfileBaseEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self._send("press")


class ProfileClimate(ProfileBaseEntity, ClimateEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    if not hasattr(ClimateEntity, "native_current_temperature"):
        # Compatibility with Home Assistant before the native-temperature API.
        _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        capabilities = self._spec.capabilities or {}
        modes = []
        for mode in capabilities.get("hvac_modes", ["off", "heat"]):
            try:
                modes.append(HVACMode(mode))
            except ValueError:
                continue
        self._attr_hvac_modes = modes or [HVACMode.OFF, HVACMode.HEAT]
        self._attr_min_temp = capabilities.get("min_temp", 5)
        self._attr_max_temp = capabilities.get("max_temp", 35)
        self._attr_target_temperature_step = capabilities.get(
            "temp_step", 0.5)
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if "turn_on" in self._spec.commands:
            features |= ClimateEntityFeature.TURN_ON
        if "turn_off" in self._spec.commands:
            features |= ClimateEntityFeature.TURN_OFF
        self._attr_supported_features = features
        self._sync_temperature_attributes()

    def _sync_temperature_attributes(self) -> None:
        current = self._values().get("current_temperature")
        target = self._values().get("target_temperature")
        current = float(current) if isinstance(current, (int, float)) else None
        target = float(target) if isinstance(target, (int, float)) else None
        self._attr_current_temperature = current
        self._attr_target_temperature = target
        self._attr_native_current_temperature = current
        self._attr_native_target_temperature = target
        for cached in (
                "current_temperature", "target_temperature",
                "native_current_temperature", "native_target_temperature"):
            self.__dict__.pop(cached, None)

    def _write_state(self) -> None:
        self._sync_temperature_attributes()
        super()._write_state()

    @property
    def hvac_mode(self) -> HVACMode:
        values = self._values()
        onoff = values.get("onoff")
        mode = values.get("mode")
        if onoff == 0 or (onoff is None and mode == 0):
            return HVACMode.OFF
        if HVACMode.HEAT in self._attr_hvac_modes:
            return HVACMode.HEAT
        return self._attr_hvac_modes[0]

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self._send("set_temperature", temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._send("turn_off")
        else:
            await self._send("turn_on")

    async def async_turn_on(self) -> None:
        await self._send("turn_on")

    async def async_turn_off(self) -> None:
        await self._send("turn_off")


class ProfileFan(ProfileBaseEntity, FanEntity):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attr_supported_features = FanEntityFeature.SET_SPEED

    @property
    def is_on(self) -> bool:
        return bool(self.percentage)

    @property
    def percentage(self) -> Optional[int]:
        values = self._values()
        speed = values.get("speed")
        maximum = values.get("max_speed")
        if not isinstance(speed, (int, float)):
            return None
        if not isinstance(maximum, (int, float)) or maximum <= 0:
            return 100 if speed else 0
        return round(speed * 100 / maximum)

    async def async_set_percentage(self, percentage: int) -> None:
        values = self._values()
        maximum = values.get("max_speed")
        maximum = maximum if isinstance(maximum, (int, float)) and maximum else 100
        await self._send("set_speed", round(percentage * maximum / 100))

    async def async_turn_on(self, percentage: Optional[int] = None,
                            preset_mode: Optional[str] = None,
                            **kwargs: Any) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._send("turn_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send("turn_off")


class ProfileHumidifier(ProfileBaseEntity, HumidifierEntity):
    @property
    def is_on(self) -> bool:
        values = self._values()
        if "onoff" in values:
            return _as_bool(values.get("onoff"))
        return bool(values.get("mode"))

    async def async_turn_on(self) -> None:
        await self._send("turn_on")

    async def async_turn_off(self) -> None:
        await self._send("turn_off")


class ProfileUpdateEntity(UpdateEntity):
    """Surface the profile applied to a device and allow re-applying it."""

    _attr_should_poll = False
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(self, adapter, device_uuid: str, runtime,
                 subdevice_id: Optional[str] = None, template=None) -> None:
        self._adapter = adapter
        self._device_uuid = device_uuid
        self._runtime = runtime
        self._subdevice_id = subdevice_id
        self._template = template
        if subdevice_id is not None:
            self._attr_unique_id = (
                f"{DOMAIN}:{subdevice_id}:update:{template.uid}")
            self._attr_title = f"{template.name or subdevice_id} profile"
        else:
            self._attr_unique_id = (
                f"{DOMAIN}:{device_uuid}:update:{runtime.profile.profile_id}")
            self._attr_title = f"{runtime.profile.profile_id} profile"

    @property
    def available(self) -> bool:
        return self._adapter.device_available(self._device_uuid)

    @property
    def device_info(self) -> Dict[str, Any]:
        descriptor = getattr(self._adapter, "descriptors", {}).get(
            self._device_uuid)
        return _device_info(
            self._device_uuid, self._subdevice_id, self._template,
            descriptor)

    @property
    def installed_version(self) -> Optional[str]:
        return self._runtime.profile.version

    @property
    def latest_version(self) -> Optional[str]:
        return self._runtime.profile.version

    @property
    def release_summary(self) -> Optional[str]:
        return self._runtime.profile.description

    async def async_install(self, version: Optional[str],
                            backup: bool, **kwargs: Any) -> None:
        await self._adapter.async_reload_entry()


def async_setup_profile_updates(hass, config_entry, async_add_entities
                                ) -> None:
    data = hass.data.get(DOMAIN, {})
    adapter = data.get(BROKER_ADAPTER)
    if adapter is None:
        return
    added = data.setdefault("ADDED_ENTITIES_IDS", set())

    def add_now() -> None:
        entities: List[Entity] = []

        def add(device_uuid, runtime, subdevice_id=None, template=None):
            entity = ProfileUpdateEntity(
                adapter, device_uuid, runtime, subdevice_id, template)
            if entity.unique_id in added:
                return
            added.add(entity.unique_id)
            entities.append(entity)

        for device_uuid, runtime in adapter.runtimes.items():
            add(device_uuid, runtime)
            for subdevice_id, subdevice in runtime.subdevices.items():
                add(device_uuid, runtime, subdevice_id, subdevice.template)
        if entities:
            async_add_entities(entities, False)

    adapter.add_ready_listener(add_now)


PLATFORM_CLASSES = {
    "switch": ProfileSwitch,
    "light": ProfileLight,
    "sensor": ProfileSensor,
    "binary_sensor": ProfileBinarySensor,
    "cover": ProfileCover,
    "number": ProfileNumber,
    "button": ProfileButton,
    "climate": ProfileClimate,
    "fan": ProfileFan,
    "humidifier": ProfileHumidifier,
}


def async_setup_profile_entities(hass, config_entry, platform: str,
                                 async_add_entities) -> None:
    """Register the platform entities once the profile backend is ready."""
    data = hass.data.get(DOMAIN, {})
    adapter = data.get(BROKER_ADAPTER)
    if adapter is None:
        return
    entity_class = PLATFORM_CLASSES.get(platform)
    if entity_class is None:
        return

    added = data.setdefault("ADDED_ENTITIES_IDS", set())

    def add_now() -> None:
        entities: List[Entity] = []

        def add(device_uuid, runtime, spec, subdevice=None):
            if spec.platform != platform:
                return
            entity = entity_class(
                adapter, device_uuid, runtime, spec, subdevice)
            if entity.unique_id in added:
                return
            added.add(entity.unique_id)
            entities.append(entity)

        for device_uuid, runtime in adapter.runtimes.items():
            for spec in runtime.profile.entities.values():
                add(device_uuid, runtime, spec)
            for subdevice_id, subdevice in runtime.subdevices.items():
                for spec in subdevice.template.entities.values():
                    add(device_uuid, runtime, spec,
                        (subdevice_id, subdevice.template))
        if entities:
            async_add_entities(entities, False)

    adapter.add_ready_listener(add_now)
