from meross_iot.controller.mixins.light import LightMixin
from meross_iot.model.enums import Namespace

import custom_components.meross_cloud  # noqa: F401 - applies the runtime patches


class _Base:
    async def async_handle_update(self, namespace, data):
        return False


class _FakeLightDevice(LightMixin, _Base):
    def __init__(self):
        self._channel_light_status = {}


async def test_system_all_without_light_digest_is_ignored():
    device = _FakeLightDevice()

    handled = await device.async_handle_update(
        Namespace.SYSTEM_ALL, {"all": {"digest": {"togglex": []}}}
    )

    assert handled is False
    assert device._channel_light_status == {}


async def test_system_all_with_light_digest_is_handled():
    device = _FakeLightDevice()

    handled = await device.async_handle_update(
        Namespace.SYSTEM_ALL,
        {"all": {"digest": {"light": {"channel": 0, "onoff": 1}}}},
    )

    assert handled is True
    assert device._channel_light_status[0].is_on is True
