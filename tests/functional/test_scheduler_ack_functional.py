"""F4/F5/F7 — scheduler, ACK routing and payload resilience (H2)."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from helpers import catalog_entry, wait_for

from custom_components.meross_local_cloud.broker_adapter import BrokerProfileAdapter
from custom_components.meross_local_cloud.vendor.merossclient import DeviceDescriptor
from custom_components.meross_local_cloud.vendor.merossclient.protocol.message import (
    MerossResponse,
)

TOGGLE = "Appliance.Control.ToggleX"
ELECTRICITY = "Appliance.Control.Electricity"

MSS310_PAYLOAD = {
    "all": {
        "system": {
            "hardware": {
                "type": "mss310", "subType": "un", "version": "1.0.0",
                "uuid": "u1", "macAddress": "AA:BB:CC:DD:EE:FF",
            },
            "firmware": {"version": "3.0.0"},
            "online": {"status": 1},
        },
        "digest": {"togglex": [{"channel": 0, "onoff": 1}]},
    },
    "ability": {"Appliance.Control.ToggleX": {}},
}


class FunctionalTransport:
    connected = True

    def __init__(self):
        self.requests = []
        self.multiples = []

    async def async_connect(self):
        return None

    async def async_stop(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor(MSS310_PAYLOAD)

    def _body(self, namespace):
        if namespace == TOGGLE:
            return {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]}
        if namespace == ELECTRICITY:
            return {"channel": 0,
                    "electricity": {"power": 10, "voltage": 2300,
                                    "current": 50}}
        return {}

    async def async_request(self, uuid, namespace, method, payload):
        self.requests.append((uuid, namespace, method, payload))
        return SimpleNamespace(
            uuid=uuid,
            namespace=namespace,
            method="SETACK" if method == "SET" else "GETACK",
            payload=payload)

    async def async_request_multiple(self, uuid, requests):
        requests = list(requests)
        self.multiples.append(requests)
        return SimpleNamespace(
            namespace="Appliance.Control.Multiple", method="SETACK",
            payload={"multiple": [{
                "header": {"namespace": namespace, "method": "GETACK"},
                "payload": self._body(namespace),
            } for namespace, _, _ in requests]})


def message(payload, uuid="u1", namespace=TOGGLE, method="PUSH"):
    return MerossResponse(json.dumps({
        "header": {"messageId": "m1", "namespace": namespace,
                   "method": method, "from": f"/appliance/{uuid}/publish"},
        "payload": payload,
    }))


async def start_adapter(hass):
    transport = FunctionalTransport()
    coordinator = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key", token="t"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
    )
    with patch(
            "custom_components.meross_local_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=transport), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_list_devices", AsyncMock(return_value=[
                    SimpleNamespace(uuid="u1")])), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(return_value={
                    "revision": "rev1", "count": 1})), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(return_value={
                    "schema_version": 1, "revision": "rev1",
                    "profiles": [catalog_entry("mss310")]})):
        adapter = BrokerProfileAdapter(hass, coordinator)
        await adapter.async_start()
    return adapter, transport


async def test_f4_initial_batching_and_push_suppression(hass):
    adapter, transport = await start_adapter(hass)
    try:
        assert await wait_for(lambda: transport.multiples)
        assert await wait_for(
            lambda: adapter.runtimes["u1"].entities["switch"].values)

        await asyncio.sleep(0.15)
        assert len(transport.multiples) == 1
        assert {entry[0] for entry in transport.multiples[0]} == {
            TOGGLE, ELECTRICITY}
        assert not [request for request in transport.requests
                    if request[2] == "GET"]
        assert adapter.runtimes["u1"].entities["switch"].values["onoff"] == 1
    finally:
        await adapter.async_stop()


async def test_f5_set_updates_state_and_polls_lazily(hass):
    adapter, transport = await start_adapter(hass)
    try:
        assert await wait_for(lambda: transport.multiples)
        assert await wait_for(
            lambda: adapter.runtimes["u1"].entities["switch"].values)

        await adapter.async_send("u1", TOGGLE, "SET", {
            "channel": 0, "togglex": [{"channel": 0, "onoff": 0}]})

        assert adapter.runtimes["u1"].entities["switch"].values["onoff"] == 0
        assert (await wait_for(
            lambda: any(request[2] == "GET"
                        for request in transport.requests)))
    finally:
        await adapter.async_stop()


async def test_f7_malformed_and_foreign_payloads_are_isolated(hass):
    adapter, transport = await start_adapter(hass)
    try:
        assert await wait_for(lambda: transport.multiples)
        before = adapter.summary()

        adapter._dispatch_message(
            MerossResponse(json.dumps({"payload": {}})))
        adapter._dispatch_message(message([]))
        adapter._dispatch_message(message(
            {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]},
            uuid="foreign"))

        assert adapter.runtimes["u1"].entities["switch"].values["onoff"] == 1
        assert adapter.summary()["runtime_messages"] >= \
            before["runtime_messages"]
    finally:
        await adapter.async_stop()
