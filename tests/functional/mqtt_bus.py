"""In-memory MQTT bus connecting the adapter to device simulators (H2)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace


class InMemoryMqttBus:
    connected = True

    def __init__(self, latency: float = 0.0):
        self.latency = latency
        self.devices = {}
        self.requests = []
        self.multiples = []
        self.offline = set()
        self.message_listener = None

    def add(self, device):
        device.bus = self
        self.devices[device.uuid] = device
        return device

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return await self.devices[device_uuid].async_describe(device_uuid)

    async def _delay(self):
        if self.latency:
            await asyncio.sleep(self.latency)

    def _check(self, device_uuid):
        if device_uuid in self.offline:
            raise TimeoutError(f"device {device_uuid} is offline")

    async def async_request(self, device_uuid, namespace, method, payload):
        self.requests.append((device_uuid, namespace, method, payload))
        await self._delay()
        self._check(device_uuid)
        return await self.devices[device_uuid].async_request(
            device_uuid, namespace, method, payload)

    async def async_request_multiple(self, device_uuid, requests):
        requests = list(requests)
        self.multiples.append((device_uuid, requests))
        await self._delay()
        self._check(device_uuid)
        return await self.devices[device_uuid].async_request_multiple(
            device_uuid, requests)

    def publish(self, device_uuid, namespace, payload, method="PUSH"):
        if device_uuid in self.offline:
            return
        listener = self.message_listener
        if listener is not None:
            listener(SimpleNamespace(
                uuid=device_uuid, namespace=namespace, method=method,
                payload=payload))
