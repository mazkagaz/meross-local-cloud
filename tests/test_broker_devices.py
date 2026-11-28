from unittest.mock import AsyncMock

import pytest

from custom_components.meross_local_cloud.broker_http import BrokerHttpError
from custom_components.meross_local_cloud.broker_devices import (
    DEVICE_LIST_PATH,
    BrokerDeviceInfo,
    async_list_devices,
    parse_devices,
)


def test_parse_devices():
    devices = parse_devices([
        {
            "uuid": "u1",
            "devName": "Shutter",
            "deviceType": "mrs100",
            "subType": "un",
            "onlineStatus": 1,
            "fmwareVersion": "7.3.3",
            "hdwareVersion": "7.0.0",
            "channels": [{"channel": 0}, {"channel": 1}],
        },
    ])

    assert devices == [BrokerDeviceInfo(
        uuid="u1", name="Shutter", device_type="mrs100", sub_type="un",
        online=True, firmware="7.3.3", hardware="7.0.0",
        channels=(0, 1))]


def test_parse_devices_ignores_malformed_entries():
    devices = parse_devices([
        None,
        {},
        {"uuid": ""},
        {"uuid": "u2", "onlineStatus": 2},
        {"uuid": "u3", "channels": [{"channel": -1}, {"channel": True}]},
    ])

    assert [device.uuid for device in devices] == ["u2", "u3"]
    assert devices[0].online is False
    assert devices[1].channels == ()


@pytest.mark.parametrize("payload", [None, {}, "nope", 5])
def test_non_list_payload_yields_no_devices(payload):
    assert parse_devices(payload) == []


async def test_async_list_devices_uses_the_signed_client():
    http = AsyncMock()
    http.async_post.return_value = [{"uuid": "u1", "onlineStatus": 1}]

    devices = await async_list_devices(http)

    assert devices[0].uuid == "u1"
    http.async_post.assert_awaited_once_with(DEVICE_LIST_PATH)


async def test_async_list_devices_rejects_a_malformed_payload():
    http = AsyncMock()
    http.async_post.return_value = {"unexpected": "object"}
    with pytest.raises(BrokerHttpError):
        await async_list_devices(http)
