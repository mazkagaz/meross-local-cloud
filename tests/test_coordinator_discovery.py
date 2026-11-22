from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.meross_local_cloud import MerossCoordinator
from custom_components.meross_local_cloud import broker_http
from custom_components.meross_local_cloud.broker_devices import BrokerDeviceInfo


def coordinator():
    instance = object.__new__(MerossCoordinator)
    instance._broker_http = object()
    instance._missing_tracker = SimpleNamespace(
        async_update=AsyncMock())
    return instance


async def test_poll_uses_the_broker_client():
    instance = coordinator()
    devices = [BrokerDeviceInfo(uuid="u1", name="Shutter",
                                device_type="mrs100", online=True)]

    with patch(
            "custom_components.meross_local_cloud.async_list_devices",
            AsyncMock(return_value=devices)):
        data = await instance._async_fetch_http_data()

    assert data == {"u1": devices[0]}
    instance._missing_tracker.async_update.assert_awaited_once()
    assert list(instance._missing_tracker.async_update.await_args.args[0]) == \
        devices


async def test_poll_without_client_returns_empty():
    instance = coordinator()
    instance._broker_http = None

    assert await instance._async_fetch_http_data() == {}


@pytest.mark.parametrize("error,expected", [
    (broker_http.BrokerTokenError("expired"), ConfigEntryAuthFailed),
    (broker_http.BrokerAuthError("denied"), ConfigEntryAuthFailed),
    (broker_http.BrokerHttpError("boom"), UpdateFailed),
])
async def test_poll_errors_are_mapped(error, expected):
    instance = coordinator()

    with patch(
            "custom_components.meross_local_cloud.async_list_devices",
            AsyncMock(side_effect=error)):
        with pytest.raises(expected):
            await instance._async_fetch_http_data()
