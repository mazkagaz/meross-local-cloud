from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.meross_cloud.broker_adapter import BrokerProfileAdapter
from custom_components.meross_cloud.broker_profile_sensor import (
    BrokerProfileSensor,
)
from custom_components.meross_cloud.broker_profiles import async_fetch_revision
from custom_components.meross_cloud.vendor.merossclient import DeviceDescriptor

PAYLOAD = {
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
    "ability": {"Appliance.RollerShutter.State": {}},
}


class FakeTransport:
    connected = True

    async def async_connect(self):
        return None

    async def async_describe(self, device_uuid):
        return DeviceDescriptor(PAYLOAD)

    async def async_stop(self):
        return None


def test_devices_library_is_loaded_lazily():
    from custom_components.meross_cloud.vendor.merossclient import library

    assert not hasattr(library, "DEVICES_LIBRARY")
    assert library.get_devices_library()


def test_vendored_descriptor_reads_broker_payload():
    descriptor = DeviceDescriptor(PAYLOAD)
    assert descriptor.type == "mrs100"
    assert descriptor.uuid == "u1"
    assert descriptor.macAddress_fmt == "aabbccddeeff"
    assert descriptor.fw_version == "7.3.3"
    assert "Appliance.RollerShutter.State" in descriptor.ability


async def test_profile_fetch_signs_the_profiles_path():
    client = SimpleNamespace(cloud_credentials=object())
    post = AsyncMock(return_value={"revision": "abc", "count": 3})
    with patch(
            "custom_components.meross_cloud.broker_profiles."
            "MerossHttpClient._async_authenticated_post", post):
        result = await async_fetch_revision(client, "https://broker:2004")

    assert result["count"] == 3
    assert post.await_args.kwargs["url"] == \
        "https://broker:2004/v1/Device/profiles/rev"
    assert post.await_args.kwargs["cloud_creds"] is client.cloud_credentials


async def test_adapter_builds_descriptors_and_summary():
    coordinator = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
        client=SimpleNamespace(
            async_list_devices=AsyncMock(
                return_value=[SimpleNamespace(uuid="u1")])),
    )
    with patch(
            "custom_components.meross_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=FakeTransport()), \
            patch(
                "custom_components.meross_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(
                    return_value={"revision": "abc", "count": 3})), \
            patch(
                "custom_components.meross_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(
                    return_value={"revision": "abc"})):
        adapter = BrokerProfileAdapter(SimpleNamespace(loop=None), coordinator)
        await adapter.async_start()

    assert adapter.summary()["state"] == "connected"
    assert adapter.summary()["profiles"] == 3
    assert adapter.descriptors["u1"]["type"] == "mrs100"
    assert "Appliance.RollerShutter.State" in \
        adapter.descriptors["u1"]["abilities"]


async def test_adapter_aborts_after_the_first_descriptor_failure():
    class FailingTransport(FakeTransport):
        calls = 0

        async def async_describe(self, device_uuid):
            FailingTransport.calls += 1
            raise TimeoutError("GET Appliance.System.All")

    coordinator = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
        client=SimpleNamespace(
            async_list_devices=AsyncMock(return_value=[
                SimpleNamespace(uuid="u1"), SimpleNamespace(uuid="u2")])),
    )
    with patch(
            "custom_components.meross_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=FailingTransport()), \
            patch(
                "custom_components.meross_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(
                    return_value={"revision": "abc", "count": 3})), \
            patch(
                "custom_components.meross_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(
                    return_value={"revision": "abc"})):
        adapter = BrokerProfileAdapter(SimpleNamespace(loop=None), coordinator)
        await adapter.async_start()

    assert FailingTransport.calls == 1
    assert adapter.summary()["state"] == "error"
    assert adapter.descriptors == {}
    assert "TimeoutError" in adapter.last_error


def test_sensor_shows_starting_before_the_probe_runs():
    adapter = SimpleNamespace(summary=lambda: {
        "state": "starting", "revision": None, "profiles": 0,
        "devices": 0, "last_error": None,
    })
    sensor = BrokerProfileSensor(adapter)

    assert sensor.native_value == "starting"


def test_profile_sensor_exposes_adapter_summary():
    adapter = SimpleNamespace(summary=lambda: {
        "state": "connected", "revision": "abc", "profiles": 3,
        "devices": 1, "last_error": None,
    })
    sensor = BrokerProfileSensor(adapter)

    assert sensor.native_value == "connected"
    assert sensor.extra_state_attributes["profiles"] == 3
    assert sensor.unique_id == "broker_profile_backend"
