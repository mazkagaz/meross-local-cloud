from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from custom_components.meross_cloud.broker_adapter import BrokerProfileAdapter
from custom_components.meross_cloud.vendor.merossclient import DeviceDescriptor

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"

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


HUB_PAYLOAD = {
    "all": {
        "system": {
            "hardware": {
                "type": "msh300", "subType": "un", "version": "1.0.0",
                "uuid": "h1", "macAddress": "AA:BB:CC:DD:EE:01",
            },
            "firmware": {"version": "3.0.0"},
            "online": {"status": 1},
        },
        "digest": {
            "hub": {
                "subdevice": [
                    {"id": "sub1", "ms100": {}},
                ],
            },
        },
    },
    "ability": {"Appliance.Hub.Sensor.TempHum": {}},
}

SUBDEVICE_NS = "Appliance.Hub.Sensor.TempHum"
HUB_CATALOG = {
    "schema_version": 2,
    "revision": "abc",
    "profiles": [{
        "id": "test.hub",
        "version": "1",
        "hash": "hub-fixture",
        "profile": {
            "schema_version": 2,
            "profile": {"id": "test.hub", "version": "1"},
            "match": {"kind": "hub", "type": ["msh300"]},
            "payloads": {},
            "entities": [],
            "subdevices": [{
                "match": {"type": ["ms100"]},
                "payloads": {
                    SUBDEVICE_NS: {"methods": ["GETACK", "PUSH"],
                                   "fields": {}},
                },
                "entities": [{
                    "key": "temperature",
                    "platform": "sensor",
                    "state": {
                        "namespace": SUBDEVICE_NS,
                        "fields": {"value": "temperature"},
                    },
                }],
            }],
        },
    }],
}


class FakeTransport:
    connected = True

    async def async_connect(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor(MSS310_PAYLOAD)

    async def async_stop(self):
        return None


def profile_entry(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return {
        "id": data["profile"]["id"],
        "version": data["profile"]["version"],
        "hash": "fixture",
        "profile": data,
    }


def coordinator():
    return SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
        client=SimpleNamespace(
            async_list_devices=AsyncMock(
                return_value=[SimpleNamespace(uuid="u1")])),
    )


class FakeHubTransport(FakeTransport):
    async def async_describe(self, device_uuid):
        return DeviceDescriptor(HUB_PAYLOAD)


async def run_adapter(catalog, transport=FakeTransport):
    with patch(
            "custom_components.meross_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=transport()), \
            patch(
                "custom_components.meross_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(
                    return_value={"revision": "abc", "count": 1})), \
            patch(
                "custom_components.meross_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(return_value=catalog)):
        adapter = BrokerProfileAdapter(SimpleNamespace(loop=None), coordinator())
        await adapter.async_start()
    return adapter


async def test_matching_device_is_compiled_lazily():
    adapter = await run_adapter({
        "schema_version": 1,
        "revision": "abc",
        "profiles": [profile_entry("mss310")],
    })

    summary = adapter.summary()
    assert summary["state"] == "connected"
    assert summary["devices_matched"] == 1
    assert summary["devices_unmatched"] == 0
    assert summary["profiles_compiled"] == 1
    assert summary["match_ambiguities"] == 0
    assert summary["compile_errors"] == []
    assert adapter.compiler.cache_size == 1


async def test_unrelated_device_stays_unmatched():
    adapter = await run_adapter({
        "schema_version": 1,
        "revision": "abc",
        "profiles": [profile_entry("mrs100")],
    })

    summary = adapter.summary()
    assert summary["devices_matched"] == 0
    assert summary["devices_unmatched"] == 1
    assert summary["profiles_compiled"] == 0


async def test_compile_errors_are_reported_without_failing_the_probe():
    data = profile_entry("mss310")["profile"]
    data["entities"][0]["state"]["namespace"] = "Appliance.Unknown"

    adapter = await run_adapter({
        "schema_version": 1,
        "revision": "abc",
        "profiles": [{
            "id": data["profile"]["id"],
            "version": data["profile"]["version"],
            "hash": "broken",
            "profile": data,
        }],
    })

    summary = adapter.summary()
    assert summary["state"] == "connected"
    assert summary["devices_matched"] == 1
    assert any("unknown state namespace" in error
               for error in summary["compile_errors"])


async def test_hub_subdevices_are_matched_to_templates():
    adapter = await run_adapter(HUB_CATALOG, FakeHubTransport)

    summary = adapter.summary()
    assert summary["state"] == "connected"
    assert summary["devices_matched"] == 1
    assert summary["subdevices_matched"] == 1
    assert summary["subdevices_unmatched"] == 0
    assert summary["compile_errors"] == []


async def test_unmatched_hub_subdevice_is_counted():
    catalog = {
        "schema_version": 2,
        "revision": "abc",
        "profiles": [],
    }
    catalog["profiles"] = [{
        **HUB_CATALOG["profiles"][0],
        "profile": {
            **HUB_CATALOG["profiles"][0]["profile"],
            "subdevices": [{
                "match": {"type": ["ms200"]},
                "entities": [],
            }],
        },
    }]

    adapter = await run_adapter(catalog, FakeHubTransport)

    summary = adapter.summary()
    assert summary["devices_matched"] == 1
    assert summary["subdevices_matched"] == 0
    assert summary["subdevices_unmatched"] == 1


async def test_without_a_catalog_nothing_is_matched():
    adapter = await run_adapter({"revision": "abc"})

    summary = adapter.summary()
    assert summary["devices_matched"] == 0
    assert summary["devices_unmatched"] == 1
    assert summary["profiles_compiled"] == 0
