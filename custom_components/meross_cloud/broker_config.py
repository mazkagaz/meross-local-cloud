"""P3: broker-side roller-shutter configuration with a TTL cache.

This is the integration interface for the dedicated broker endpoint
(D2.3). It replaces per-entity ``Appliance.RollerShutter.Config`` GETs with
one account-wide call. Until the endpoint exists, failures are cached briefly
and the last known values are kept, so callers never break.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from .broker_http import BrokerHttpClient

_LOGGER = logging.getLogger(__name__)

CONFIG_PATH = "/v1/Device/rollerShutterConfig"
DEFAULT_TTL = 600.0
FAILURE_TTL = 60.0
FETCH_TIMEOUT = 10.0


@dataclass(frozen=True)
class ChannelState:
    """Known roller-shutter values for one channel."""

    channel: int
    signal_open_ms: Optional[int] = None
    signal_close_ms: Optional[int] = None
    position: Optional[int] = None
    adjust: Optional[int] = None


def _integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _non_negative(value: Any) -> Optional[int]:
    number = _integer(value)
    return number if number is not None and number >= 0 else None


def _parse_channels(entry: Dict[str, Any]) -> Dict[int, ChannelState]:
    buckets: Dict[int, Dict[str, Optional[int]]] = {}

    def bucket(channel: int) -> Dict[str, Optional[int]]:
        return buckets.setdefault(channel, {
            "signal_open_ms": None,
            "signal_close_ms": None,
            "position": None,
            "adjust": None,
        })

    config = entry.get("config")
    if isinstance(config, list):
        for item in config:
            if not isinstance(item, dict):
                continue
            channel = _non_negative(item.get("channel"))
            if channel is None:
                continue
            source = item.get("config")
            if not isinstance(source, dict):
                source = item
            values = bucket(channel)
            values["signal_open_ms"] = _non_negative(source.get("signalOpen"))
            values["signal_close_ms"] = _non_negative(source.get("signalClose"))

    position = entry.get("position")
    if isinstance(position, list):
        for item in position:
            if not isinstance(item, dict):
                continue
            channel = _non_negative(item.get("channel"))
            if channel is None:
                continue
            bucket(channel)["position"] = _non_negative(item.get("position"))

    adjust = entry.get("adjust")
    if isinstance(adjust, list):
        for item in adjust:
            if not isinstance(item, dict):
                continue
            channel = _non_negative(item.get("channel"))
            if channel is None:
                continue
            value = item.get("value", item.get("adjust"))
            bucket(channel)["adjust"] = _non_negative(value)

    return {
        channel: ChannelState(channel=channel, **values)
        for channel, values in buckets.items()
    }


async def async_fetch_roller_shutter_config(
        http: BrokerHttpClient) -> Any:
    return await http.async_post(CONFIG_PATH)


FetchFunc = Callable[[BrokerHttpClient], Awaitable[Any]]


class RollerShutterConfigCache:
    """Account-wide cache for POST /v1/Device/rollerShutterConfig."""

    def __init__(self, http: BrokerHttpClient,
                 ttl: float = DEFAULT_TTL,
                 failure_ttl: float = FAILURE_TTL,
                 clock: Callable[[], float] = time.monotonic,
                 fetch: FetchFunc = async_fetch_roller_shutter_config) -> None:
        self._http = http
        self._ttl = ttl
        self._failure_ttl = failure_ttl
        self._clock = clock
        self._fetch = fetch
        self._lock = asyncio.Lock()
        self._states: Dict[str, Dict[int, ChannelState]] = {}
        self._fetched_at: Optional[float] = None
        self._healthy = False
        self.last_error: Optional[str] = None

    async def async_get(self,
                        uuid: str) -> Optional[Dict[int, ChannelState]]:
        await self._async_ensure()
        return self._states.get(uuid)

    async def async_get_channel(self, uuid: str,
                                channel: int) -> Optional[ChannelState]:
        states = await self.async_get(uuid)
        if states is None:
            return None
        return states.get(channel)

    def cached_channel(self, uuid: str,
                       channel: int) -> Optional[ChannelState]:
        """Return a cached channel without triggering a fetch."""
        return self._states.get(uuid, {}).get(channel)

    async def async_refresh(self) -> None:
        await self._async_fetch(force=True)

    def update_from_set(self, uuid: str, channel: int,
                        signal_open_ms: Optional[int] = None,
                        signal_close_ms: Optional[int] = None) -> None:
        """Apply a known SET without waiting for the broker refresh."""
        if (not uuid or isinstance(channel, bool)
                or not isinstance(channel, int) or channel < 0):
            return
        signal_open_ms = _non_negative(signal_open_ms)
        signal_close_ms = _non_negative(signal_close_ms)
        states = self._states.setdefault(uuid, {})
        previous = states.get(channel)
        states[channel] = ChannelState(
            channel=channel,
            signal_open_ms=(signal_open_ms if signal_open_ms is not None
                            else previous.signal_open_ms if previous else None),
            signal_close_ms=(signal_close_ms if signal_close_ms is not None
                             else previous.signal_close_ms if previous else None),
            position=previous.position if previous else None,
            adjust=previous.adjust if previous else None,
        )

    def invalidate(self) -> None:
        self._fetched_at = None

    async def _async_ensure(self) -> None:
        if self._fetched_at is None:
            await self._async_fetch(force=False)
            return
        age = self._clock() - self._fetched_at
        ttl = self._ttl if self._healthy else self._failure_ttl
        if age >= ttl:
            await self._async_fetch(force=False)

    async def _async_fetch(self, force: bool) -> None:
        async with self._lock:
            now = self._clock()
            if not force and self._fetched_at is not None:
                ttl = self._ttl if self._healthy else self._failure_ttl
                if now - self._fetched_at < ttl:
                    return
            try:
                async with asyncio.timeout(FETCH_TIMEOUT):
                    raw = await self._fetch(self._http)
            except Exception as err:  # noqa: BLE001 - endpoint may be absent
                self.last_error = f"{type(err).__name__}: {err}"
                self._healthy = False
                self._fetched_at = self._clock()
                _LOGGER.debug("Roller-shutter config unavailable: %s", err)
                return
            if not isinstance(raw, dict):
                self.last_error = "malformed roller-shutter config response"
                self._healthy = False
                self._fetched_at = self._clock()
                return
            states = {}
            for uuid, entry in raw.items():
                if not isinstance(uuid, str) or not uuid:
                    continue
                if not isinstance(entry, dict):
                    continue
                states[uuid] = _parse_channels(entry)
            self._states = states
            self._healthy = True
            self.last_error = None
            self._fetched_at = self._clock()
