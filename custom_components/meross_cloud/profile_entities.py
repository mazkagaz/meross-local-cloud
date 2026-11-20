"""Home Assistant entities built from compiled profiles (D3, opt-in).

These entities live beside the historical meross_iot entities until D5. They
use the central scheduler/runtime and distinct unique_ids, and are only
created when the ``profile_entities`` option is enabled.
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

from .common import (
    BROKER_ADAPTER,
    CONF_OPT_PROFILE_ENTITIES,
    DOMAIN,
)
from .profiles.paths import substitute

_LOGGER = logging.getLogger(__name__)

_ENTITY_CATEGORIES = {
    "config": EntityCategory.CONFIG,
    "diagnostic": EntityCategory.DIAGNOSTIC,
}


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
                 template=None) -> Dict[str, Any]:
    if subdevice_id is not None:
        return {
            "identifiers": {(DOMAIN, subdevice_id)},
            "name": (template.name if template is not None else None)
            or subdevice_id,
            "manufacturer": "Meross",
            "via_device": (DOMAIN, device_uuid),
        }
    return {
        "identifiers": {(DOMAIN, device_uuid)},
        "manufacturer": "Meross",
    }


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
        if self._subdevice_id is not None:
            self._attr_unique_id = (
                f"{DOMAIN}:{self._subdevice_id}:{self._template.uid}:"
                f"{spec.key}")
        else:
            self._attr_unique_id = f"{DOMAIN}:{device_uuid}:{spec.uid}"
        self._attr_name = spec.name or spec.key
        self._attr_entity_category = _ENTITY_CATEGORIES.get(
            spec.entity_category)

    @property
    def available(self) -> bool:
        return self._adapter.state == "connected"

    @property
    def device_info(self) -> Dict[str, Any]:
        return _device_info(
            self._device_uuid, self._subdevice_id, self._template)

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self._runtime.add_listener(
            self._on_runtime_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

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

    async def _send(self, command: str, value: Any = None) -> None:
        spec = self._spec.commands.get(command)
        if spec is None:
            return
        values = {"channel": self._spec.channel, "id": self._subdevice_id}
        if value is not None:
            if spec.value_scale is not None:
                value = value * spec.value_scale
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
            values["value"] = value
        payload = substitute(spec.payload, values)
        await self._adapter.async_send(
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

    @property
    def native_value(self):
        value = self._values().get("value")
        return value if isinstance(value, (int, float, str)) else None


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
        value = self._values().get("position")
        return int(value) if value is not None else None

    @property
    def is_closed(self) -> Optional[bool]:
        values = self._values()
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
        await self._send("stop")

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

    @property
    def native_value(self) -> Optional[float]:
        value = self._values().get("value")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        await self._send("set_value", value)


class ProfileButton(ProfileBaseEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self._send("press")


class ProfileClimate(ProfileBaseEntity, ClimateEntity):
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

    @property
    def current_temperature(self) -> Optional[float]:
        value = self._values().get("current_temperature")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def target_temperature(self) -> Optional[float]:
        value = self._values().get("target_temperature")
        return float(value) if isinstance(value, (int, float)) else None

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
        return self._adapter.state == "connected"

    @property
    def device_info(self) -> Dict[str, Any]:
        return _device_info(
            self._device_uuid, self._subdevice_id, self._template)

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
    if config_entry is None or not config_entry.options.get(
            CONF_OPT_PROFILE_ENTITIES, False):
        return
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
    if config_entry is None or not config_entry.options.get(
            CONF_OPT_PROFILE_ENTITIES, False):
        return
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
