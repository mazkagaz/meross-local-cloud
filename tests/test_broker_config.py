from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.meross_cloud.broker_config import (
    CONFIG_PATH,
    ChannelState,
    RollerShutterConfigCache,
    async_fetch_roller_shutter_config,
)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def cache(fetch, ttl=600, failure_ttl=60, clock=None):
    return RollerShutterConfigCache(
        SimpleNamespace(cloud_credentials=object()),
        "https://broker:2004",
        ttl=ttl,
        failure_ttl=failure_ttl,
        clock=clock or Clock(),
        fetch=fetch,
    )


PAYLOAD = {
    "u1": {
        "config": [
            {"channel": 0, "config": {"signalOpen": 45000,
                                      "signalClose": 50000}},
        ],
        "position": [{"channel": 0, "position": 40}],
        "adjust": [{"channel": 0, "value": 2}],
    },
}


async def test_channels_are_normalized():
    fetch = AsyncMock(return_value=PAYLOAD)
    config = cache(fetch)

    state = await config.async_get_channel("u1", 0)

    assert state == ChannelState(
        channel=0, signal_open_ms=45000, signal_close_ms=50000,
        position=40, adjust=2)
    assert await config.async_get_channel("u1", 1) is None
    assert await config.async_get_channel("u2", 0) is None


async def test_flat_config_items_are_supported():
    fetch = AsyncMock(return_value={
        "u1": {"config": [{"channel": 0, "signalOpen": 30000,
                           "signalClose": 40000}]},
    })
    config = cache(fetch)

    state = await config.async_get_channel("u1", 0)

    assert state.signal_open_ms == 30000
    assert state.signal_close_ms == 40000


async def test_cache_avoids_fetching_within_ttl():
    clock = Clock()
    fetch = AsyncMock(return_value=PAYLOAD)
    config = cache(fetch, ttl=600, clock=clock)

    await config.async_get("u1")
    clock.advance(599)
    await config.async_get("u1")
    fetch.assert_awaited_once()

    clock.advance(2)
    await config.async_get("u1")
    assert fetch.await_count == 2


async def test_failure_is_cached_and_stale_values_are_kept():
    clock = Clock()
    fetch = AsyncMock(side_effect=[
        PAYLOAD,
        RuntimeError("HTTP 404"),
        {"u1": {"config": []}},
    ])
    config = cache(fetch, ttl=600, failure_ttl=60, clock=clock)

    await config.async_get("u1")
    clock.advance(600)
    state = await config.async_get_channel("u1", 0)
    assert state.signal_open_ms == 45000
    assert "RuntimeError" in config.last_error

    clock.advance(30)
    await config.async_get("u1")
    assert fetch.await_count == 2

    clock.advance(31)
    await config.async_get("u1")
    assert fetch.await_count == 3
    assert config.last_error is None


async def test_malformed_response_is_a_cached_failure():
    fetch = AsyncMock(return_value=["not", "an", "object"])
    config = cache(fetch)

    assert await config.async_get("u1") is None
    assert "malformed" in config.last_error


async def test_invalid_entries_are_ignored():
    fetch = AsyncMock(return_value={
        "u1": {
            "config": [
                {"channel": True, "signalOpen": 1},
                {"channel": -1, "signalOpen": 1},
                {"channel": 0, "config": {"signalOpen": "x",
                                          "signalClose": 5000}},
                {"channel": 2.0, "signalOpen": 1000},
            ],
            "position": "nope",
            "adjust": [{"channel": 0, "adjust": 3}],
        },
        5: {"config": []},
        "": {"config": []},
        "u2": "nope",
    })
    config = cache(fetch)

    states = await config.async_get("u1")

    assert sorted(states) == [0, 2]
    assert states[0].signal_open_ms is None
    assert states[0].signal_close_ms == 5000
    assert states[0].adjust == 3
    assert states[2].signal_open_ms == 1000
    assert await config.async_get("u2") is None


async def test_update_from_set_merges_known_values():
    fetch = AsyncMock(return_value=PAYLOAD)
    config = cache(fetch)
    await config.async_get("u1")

    config.update_from_set("u1", 0, signal_open_ms=60000)
    config.update_from_set("u1", 1, signal_close_ms=70000)

    first = await config.async_get_channel("u1", 0)
    second = await config.async_get_channel("u1", 1)
    assert first.signal_open_ms == 60000
    assert first.signal_close_ms == 50000
    assert first.position == 40
    assert first.adjust == 2
    assert second.signal_close_ms == 70000


async def test_update_from_set_survives_a_failing_endpoint():
    fetch = AsyncMock(side_effect=RuntimeError("HTTP 404"))
    config = cache(fetch)

    config.update_from_set("u1", 0, signal_open_ms=60000)

    state = await config.async_get_channel("u1", 0)
    assert state.signal_open_ms == 60000


@pytest.mark.parametrize("channel", [True, -1, "0", None, 1.5])
async def test_invalid_set_channel_is_ignored(channel):
    fetch = AsyncMock(return_value={})
    config = cache(fetch)

    config.update_from_set("u1", channel, signal_open_ms=60000)

    assert await config.async_get("u1") is None


async def test_refresh_and_invalidate_force_a_fetch():
    fetch = AsyncMock(return_value=PAYLOAD)
    config = cache(fetch)

    await config.async_get("u1")
    await config.async_refresh()
    config.invalidate()
    await config.async_get("u1")

    assert fetch.await_count == 3


async def test_endpoint_path_and_authentication():
    credentials = object()
    client = SimpleNamespace(cloud_credentials=credentials)
    post = AsyncMock(return_value={})
    with patch(
            "meross_iot.http_api.MerossHttpClient."
            "_async_authenticated_post", post):
        result = await async_fetch_roller_shutter_config(
            client, "https://broker:2004/")

    assert result == {}
    assert post.await_args.kwargs["url"] == \
        f"https://broker:2004{CONFIG_PATH}"
    assert post.await_args.kwargs["params_data"] == {}
    assert post.await_args.kwargs["cloud_creds"] is credentials
