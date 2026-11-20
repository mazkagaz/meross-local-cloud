"""Central per-device polling scheduler (D3).

One task and one loop per device drive every namespace declared by the
compiled profile: pending namespaces are batched in a single
``Appliance.Control.Multiple`` request, responses feed the device runtime and
namespaces declaring PUSH are polled once then left to their pushes.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .models import CompiledProfile
from .runtime import DeviceRuntime

_LOGGER = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 1.0
FAILURE_BACKOFF = 60.0
MAX_IDLE_SLEEP = 30.0
POLL_METHODS = frozenset({"GET", "GETACK"})
KEY_MULTIPLE = "multiple"
KEY_HEADER = "header"
KEY_NAMESPACE = "namespace"
KEY_METHOD = "method"
KEY_PAYLOAD = "payload"

Request = Tuple[str, str, Dict[str, Any]]


@dataclass
class PollState:
    namespace: str
    period_s: Optional[float]
    next_due: float


class DeviceScheduler:
    """Poll one device through its compiled namespace plan."""

    def __init__(self, uuid: str, profile: CompiledProfile,
                 runtime: DeviceRuntime, sender,
                 *, rate_limit: float = DEFAULT_RATE_LIMIT,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.uuid = uuid
        self.profile = profile
        self.runtime = runtime
        self._sender = sender
        self._rate_limit = rate_limit
        self._clock = clock
        now = clock()
        self._plan: Dict[str, PollState] = {}
        for spec in profile.namespaces.values():
            if not set(spec.methods) & POLL_METHODS:
                continue
            polling = spec.polling
            if polling.strategy == "once" or polling.push:
                period = None
            else:
                period = polling.period_s
                if not period or period <= 0:
                    period = None
            self._plan[spec.namespace] = PollState(
                namespace=spec.namespace,
                period_s=float(period) if period is not None else None,
                next_due=now,
            )
        self._task: Optional[asyncio.Task] = None
        self._wake = asyncio.Event()
        self._stopped = False
        self._lazy_pending: Set[str] = set()
        self._last_request_at: Optional[float] = None
        self.polls = 0
        self.batches = 0
        self.errors = 0
        self.lazy = 0

    def start(self) -> Optional[asyncio.Task]:
        if not self._plan:
            return None
        if self._task is None or self._task.done():
            self._stopped = False
            self._task = asyncio.get_running_loop().create_task(
                self._async_run())
        return self._task

    async def async_stop(self) -> None:
        self._stopped = True
        self._wake.set()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def request_refresh(self, namespace: Optional[str] = None) -> None:
        now = self._clock()
        self.lazy += 1
        if namespace is None:
            self._lazy_pending.update(self._plan)
            for state in self._plan.values():
                state.next_due = now
        elif namespace in self._plan:
            self._lazy_pending.add(namespace)
            self._plan[namespace].next_due = now
        self._wake.set()

    def summary(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "polls": self.polls,
            "batches": self.batches,
            "errors": self.errors,
            "lazy": self.lazy,
            "namespaces": len(self._plan),
        }

    async def _async_run(self) -> None:
        try:
            while not self._stopped:
                self._wake.clear()
                now = self._clock()
                due = [state for state in self._plan.values()
                       if state.next_due <= now]
                if due:
                    await self._poll_due(due)
                    continue
                delay = self._next_delay(now)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - a device never kills HA
            self.errors += 1
            _LOGGER.debug("Scheduler for %s stopped: %s", self.uuid, err)

    def _next_delay(self, now: float) -> float:
        next_due = min((state.next_due for state in self._plan.values()),
                       default=now + MAX_IDLE_SLEEP)
        return max(0.01, min(MAX_IDLE_SLEEP, next_due - now))

    async def _poll_due(self, due: List[PollState]) -> None:
        # Requests already covered by this poll are consumed; requests arriving
        # while it runs are re-added by request_refresh and served afterwards.
        self._lazy_pending.difference_update(
            state.namespace for state in due)
        await self._async_rate_limit()
        requests: List[Request] = [
            (state.namespace, "GET", {}) for state in due]
        success = True
        try:
            if len(requests) > 1:
                response = await self._sender.async_request_multiple(
                    self.uuid, requests)
                self.batches += 1
                self._dispatch_multiple(response)
            else:
                namespace, method, payload = requests[0]
                response = await self._sender.async_request(
                    self.uuid, namespace, method, payload)
                self._dispatch_message(response)
            self.polls += len(requests)
        except Exception as err:  # noqa: BLE001 - retry after backoff
            success = False
            self.errors += 1
            _LOGGER.debug("Polling %s failed: %s", self.uuid, err)
        finally:
            now = self._clock()
            for state in due:
                if success and state.period_s is not None:
                    state.next_due = now + state.period_s
                elif success:
                    state.next_due = math.inf
                else:
                    state.next_due = now + max(
                        state.period_s or 0, FAILURE_BACKOFF)
            for namespace in self._lazy_pending:
                state = self._plan.get(namespace)
                if state is not None:
                    state.next_due = now
            self._lazy_pending.clear()

    async def _async_rate_limit(self) -> None:
        if self._rate_limit <= 0:
            return
        now = self._clock()
        if self._last_request_at is not None:
            wait = self._rate_limit - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_request_at = self._clock()

    def _dispatch_message(self, message: Any) -> None:
        try:
            namespace = message.namespace
            method = message.method
            payload = message.payload
        except Exception:  # noqa: BLE001 - malformed reply ignored
            return
        self.runtime.dispatch(namespace, method, payload)

    def _dispatch_multiple(self, response: Any) -> None:
        try:
            payload = response.payload
        except Exception:  # noqa: BLE001 - malformed reply ignored
            return
        if not isinstance(payload, dict):
            return
        entries = payload.get(KEY_MULTIPLE)
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            header = entry.get(KEY_HEADER)
            if not isinstance(header, dict):
                continue
            namespace = header.get(KEY_NAMESPACE)
            method = header.get(KEY_METHOD)
            if isinstance(namespace, str):
                self.runtime.dispatch(
                    namespace, method, entry.get(KEY_PAYLOAD))
