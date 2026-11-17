from homeassistant.components.light import (
    ColorMode,
    valid_supported_color_modes,
)

from custom_components.meross_cloud.light import (
    _active_color_mode,
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
