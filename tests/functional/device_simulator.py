"""In-memory Meross MRS100 simulator for the H2 functional harness.

It implements the subset of the broker transport used by the adapter and
scheduler: descriptors, GET/SET requests, batched responses and pushes.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.meross_cloud.vendor.merossclient import DeviceDescriptor

STATE = "Appliance.RollerShutter.State"
POSITION = "Appliance.RollerShutter.Position"
CONFIG = "Appliance.RollerShutter.Config"
ADJUST = "Appliance.RollerShutter.Adjust"

MRS100_PAYLOAD = {
    "all": {
        "system": {
            "hardware": {
                "type": "mrs100", "subType": "un", "version": "7.0.0",
                "uuid": "u1", "macAddress": "AA:BB:CC:DD:EE:FF",
            },
            "firmware": {"version": "7.3.3"},
            "online": {"status": 1},
        },
        "digest": {"togglex": [{"channel": 0, "onoff": 1}]},
    },
    "ability": {
        STATE: {},
        POSITION: {},
        CONFIG: {},
        ADJUST: {},
    },
}


class MRS100Simulator:
    uuid = "u1"
    connected = True

    def __init__(self):
        self.position = 0
        self.state = 0
        self.config = {"signalOpen": 45000, "signalClose": 50000}
        self.adjust = 0
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor(MRS100_PAYLOAD)

    def _apply_set(self, namespace, payload):
        if namespace == STATE:
            state = payload.get("state", 0)
            self.state = state
            if state == 1:
                self.position = 100
            elif state == 2:
                self.position = 0
        elif namespace == POSITION:
            self.position = payload.get("position", self.position)
        elif namespace == CONFIG:
            self.config.update(payload.get("config") or {})
        elif namespace == ADJUST:
            self.adjust = payload.get("value", 0)

    def _body(self, namespace):
        if namespace == STATE:
            return {"channel": 0, "state": self.state}
        if namespace == POSITION:
            return {"channel": 0, "position": self.position,
                    "state": self.state}
        if namespace == CONFIG:
            return {"channel": 0, "config": dict(self.config)}
        if namespace == ADJUST:
            return {"channel": 0, "value": self.adjust}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        if method == "SET":
            self._apply_set(namespace, payload)
            body = self._body(namespace)
        else:
            body = self._body(namespace)
        return SimpleNamespace(
            uuid=uuid, namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=body)

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            uuid=uuid, namespace="Appliance.Control.Multiple",
            method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})

    def push(self, adapter, namespace, payload, method="PUSH"):
        adapter._dispatch_message(SimpleNamespace(
            uuid=self.uuid, namespace=namespace, method=method,
            payload=payload))
