from homeassistant.components.light import (
    ColorMode,
    valid_supported_color_modes,
)

from custom_components.meross_cloud.light import (
    _active_color_mode,
    _cover_light_payload,
    _is_cover_light,
    _supported_color_modes,
)


def test_brightness_only_uses_brightness_not_white():
    modes = _supported_color_modes(False, True, False)
    assert modes == {ColorMode.BRIGHTNESS}
    assert _active_color_mode(False, True, False) == ColorMode.BRIGHTNESS


def test_rgb_and_temperature_coexist():
    modes = _supported_color_modes(True, True, True)
    assert modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    assert _active_color_mode(True, True, True) == ColorMode.RGB


def test_temperature_with_luminance():
    assert _supported_color_modes(False, True, True) == {ColorMode.COLOR_TEMP}
    assert _active_color_mode(False, True, True) == ColorMode.COLOR_TEMP


def test_on_off_fallback():
    assert _supported_color_modes(False, False, False) == {ColorMode.ONOFF}
    assert _active_color_mode(False, False, False) == ColorMode.ONOFF


def test_cover_light_payload_plain_on_carries_only_onoff():
    light = _cover_light_payload(0, True)["light"]
    assert light == {"channel": 0, "onoff": 1}


def test_cover_light_payload_on_with_brightness_adds_capacity():
    light = _cover_light_payload(0, True, luminance=42)["light"]
    assert light["onoff"] == 1
    assert light["luminance"] == 42
    assert light["capacity"] == 4
    assert light["channel"] == 0


def test_cover_light_payload_off_carries_only_onoff():
    light = _cover_light_payload(1, False)["light"]
    assert light == {"channel": 1, "onoff": 0}


def test_cover_devices_are_detected():
    from meross_iot.model.enums import Namespace

    from types import SimpleNamespace

    roller = SimpleNamespace(abilities={Namespace.ROLLER_SHUTTER_STATE.value: {}})
    garage = SimpleNamespace(abilities={Namespace.GARAGE_DOOR_STATE.value: {}})
    bulb = SimpleNamespace(abilities={"Appliance.Control.Light": {}})
    assert _is_cover_light(roller)
    assert _is_cover_light(garage)
    assert not _is_cover_light(bulb)


def test_all_combinations_pass_home_assistant_validation():
    for supports_rgb in (False, True):
        for supports_luminance in (False, True):
            for supports_temperature in (False, True):
                modes = _supported_color_modes(
                    supports_rgb, supports_luminance, supports_temperature)
                valid_supported_color_modes(modes)
                assert _active_color_mode(
                    supports_rgb, supports_luminance,
                    supports_temperature) in modes
