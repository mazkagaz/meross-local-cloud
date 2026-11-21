"""D5-e: bounded refresh burst after an MQTT reconnect."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.meross_cloud import broker_adapter as module
from custom_components.meross_cloud.broker_adapter import BrokerProfileAdapter
from custom_components.meross_cloud.common import DOMAIN, SHUTTER_CONFIG_CACHE


def adapter(hass, refresh):
    instance = BrokerProfileAdapter.__new__(BrokerProfileAdapter)
    instance._hass = hass
    instance.state = "connected"
    instance._listeners = []
    instance._ever_connected = False
    instance._transport_lost = False
    instance._reconnect_task = None
    instance._coordinator = SimpleNamespace(async_request_refresh=refresh)
    instance.schedulers = {
        "u1": SimpleNamespace(request_refresh=Mock())}
    hass.data[DOMAIN] = {
        SHUTTER_CONFIG_CACHE: SimpleNamespace(invalidate=Mock())}
    return instance


async def test_initial_connect_does_not_start_a_burst(hass):
    refresh = AsyncMock()
    instance = adapter(hass, refresh)

    instance._on_transport_state(True)
    await hass.async_block_till_done()

    refresh.assert_not_awaited()


async def test_reconnect_refreshes_devices_cache_and_schedulers(hass, monkeypatch):
    monkeypatch.setattr(module, "RECONNECT_REFRESH_DELAYS", (0.0, 0.0, 0.0))
    refresh = AsyncMock()
    instance = adapter(hass, refresh)

    instance._on_transport_state(True)
    instance._on_transport_state(False)
    instance._on_transport_state(True)
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    assert refresh.await_count == 3
    assert hass.data[DOMAIN][
        SHUTTER_CONFIG_CACHE].invalidate.call_count == 3
    assert instance.schedulers["u1"].request_refresh.call_count == 3


def test_catalog_watch_uses_a_background_task(hass, monkeypatch):
    seen = []

    async def watch():
        return None

    class Task:
        def done(self):
            return False

    def create_background(coro, name=None):
        seen.append(name)
        coro.close()
        return Task()

    def create_foreground(coro):
        raise AssertionError("catalog watch must not be a foreground task")

    monkeypatch.setattr(
        hass, "async_create_background_task", create_background,
        raising=False)
    monkeypatch.setattr(
        hass, "async_create_task", create_foreground, raising=False)
    instance = BrokerProfileAdapter.__new__(BrokerProfileAdapter)
    instance._hass = hass
    instance._entry_id = "entry1"
    instance._watch_task = None
    instance._async_watch_catalog = watch

    instance._start_catalog_watch()

    assert seen == ["meross_cloud_catalog_watch"]


async def test_one_failed_refresh_does_not_stop_the_burst(hass, monkeypatch):
    monkeypatch.setattr(module, "RECONNECT_REFRESH_DELAYS", (0.0, 0.0, 0.0))
    refresh = AsyncMock(side_effect=[RuntimeError("offline"), None, None])
    instance = adapter(hass, refresh)

    instance._on_transport_state(True)
    instance._on_transport_state(False)
    instance._on_transport_state(True)
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()

    assert refresh.await_count == 3
    assert instance._reconnect_task is None
