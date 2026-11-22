from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.meross_local_cloud.broker_adapter import BrokerProfileAdapter
from custom_components.meross_local_cloud.broker_profile_sensor import (
    BrokerProfileSensor,
)
from custom_components.meross_local_cloud.broker_profiles import async_fetch_revision
from custom_components.meross_local_cloud.vendor.merossclient import DeviceDescriptor

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


async def test_app_client_resolves_pending_transactions(hass):
    import json
    import ssl
    from types import SimpleNamespace as NS

    from custom_components.meross_local_cloud.broker_transport import (
        _BrokerAppClient,
    )
    from custom_components.meross_local_cloud.vendor.merossclient import (
        HostAddress,
    )

    connection = _BrokerAppClient(
        HostAddress("localhost", 2001),
        NS(log=lambda *a, **k: None, getEffectiveLevel=lambda: 0,
           isEnabledFor=lambda level: False),
        user_id="1",
        key="key",
        sslcontext=ssl.create_default_context(),
        loop=hass.loop,
    )
    from unittest.mock import Mock
    transaction = Mock()
    connection._transactions["m1"] = transaction
    payload = json.dumps({
        "header": {
            "messageId": "m1", "namespace": "Appliance.System.All",
            "method": "GETACK", "from": "/appliance/uuid/publish",
        },
        "payload": {"all": {}},
    }).encode()

    connection.on_message(SimpleNamespace(
        payload=payload, topic="/app/1-app/subscribe"))

    transaction.set_result.assert_called_once()
    assert transaction.set_result.call_args.args[0].messageid == "m1"


async def test_app_client_notifies_the_payload_listener(hass):
    import json
    import ssl
    from types import SimpleNamespace as NS

    from custom_components.meross_local_cloud.broker_transport import (
        _BrokerAppClient,
    )
    from custom_components.meross_local_cloud.vendor.merossclient import (
        HostAddress,
    )

    connection = _BrokerAppClient(
        HostAddress("localhost", 2001),
        NS(log=lambda *a, **k: None, getEffectiveLevel=lambda: 0,
           isEnabledFor=lambda level: False),
        user_id="1",
        key="key",
        sslcontext=ssl.create_default_context(),
        loop=hass.loop,
    )
    seen = []
    connection.message_listener = seen.append

    def deliver(message):
        connection.on_message(SimpleNamespace(
            payload=json.dumps(message).encode(),
            topic="/app/1-app/subscribe"))

    deliver({
        "header": {
            "messageId": "m1", "namespace": "Appliance.Control.ToggleX",
            "method": "PUSH", "from": "/appliance/uuid/publish",
        },
        "payload": {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]},
    })
    deliver({"payload": {}})
    deliver({"header": {}, "payload": {}})

    from unittest.mock import Mock
    transaction = Mock()
    connection._transactions["m2"] = transaction
    deliver({
        "header": {
            "messageId": "m2", "namespace": "Appliance.System.All",
            "method": "GETACK", "from": "/appliance/uuid/publish",
        },
        "payload": {"all": {}},
    })

    transaction.set_result.assert_called_once()
    assert len(seen) == 1
    assert seen[0].namespace == "Appliance.Control.ToggleX"


def test_transport_reports_connection_state_changes():
    from custom_components.meross_local_cloud.broker_transport import (
        BrokerMqttTransport,
    )

    seen = []
    transport = BrokerMqttTransport(
        "localhost", 2001, "1", "key", None, None,
        state_listener=seen.append)

    transport._on_connect(None)
    transport._on_disconnect(None)

    assert seen == [True, False]


async def test_priority_publish_bypasses_the_rate_limit():
    from custom_components.meross_local_cloud.broker_transport import (
        BrokerMqttTransport,
    )

    class Connection:
        rl_rate = 1.0

        def __init__(self):
            self.calls = []

        async def async_publish_raw(self, request, **kwargs):
            self.calls.append(
                (request.namespace, request.method, request.payload,
                 kwargs["uuid"], self.rl_rate))

    connection = Connection()
    client = SimpleNamespace(
        key="key", from_="/app/1/sub", shutdown=lambda: None)
    transport = BrokerMqttTransport(
        "localhost", 2001, "1", "key", None, None)
    transport._connection = connection
    transport._device_client = lambda uuid: client

    await transport.async_publish_priority(
        "u1", "Appliance.RollerShutter.Position", "SET",
        {"position": {"channel": 0, "position": -1}})

    assert connection.calls == [(
        "Appliance.RollerShutter.Position", "SET",
        {"position": {"channel": 0, "position": -1}}, "u1", 0)]
    assert connection.rl_rate == 1.0


async def test_local_connection_uses_the_relaxed_rate_limit(monkeypatch):
    from custom_components.meross_local_cloud import broker_transport as module

    created = {}

    class Connection:
        def __init__(self, *args, **kwargs):
            created["connection"] = self
            self.rl_rate = None
            self.rl_window_size = None
            self.connect_broadcast = SimpleNamespace(add=lambda cb: None)
            self.disconnect_broadcast = SimpleNamespace(add=lambda cb: None)

        async def async_connect(self, timeout=None):
            return None

    monkeypatch.setattr(module, "_BrokerAppClient", Connection)
    transport = module.BrokerMqttTransport(
        "localhost", 2001, "1", "key", None, None)

    await transport.async_connect()

    connection = created["connection"]
    assert connection.rl_rate == module.LOCAL_MQTT_RATE == 1.0
    assert connection.rl_window_size == module.LOCAL_MQTT_BURST == 5


def test_devices_library_is_loaded_lazily():
    from custom_components.meross_local_cloud.vendor.merossclient import library

    assert not hasattr(library, "DEVICES_LIBRARY")
    assert library.get_devices_library()


def test_vendored_descriptor_reads_broker_payload():
    descriptor = DeviceDescriptor(PAYLOAD)
    assert descriptor.type == "mrs100"
    assert descriptor.uuid == "u1"
    assert descriptor.macAddress_fmt == "aabbccddeeff"
    assert descriptor.fw_version == "7.3.3"
    assert "Appliance.RollerShutter.State" in descriptor.ability


async def test_profile_fetch_uses_the_signed_http_client():
    http = SimpleNamespace(
        async_post=AsyncMock(return_value={"revision": "abc", "count": 3}))

    result = await async_fetch_revision(http)

    assert result["count"] == 3
    http.async_post.assert_awaited_once_with("/v1/Device/profiles/rev")


async def test_adapter_builds_descriptors_and_summary():
    coordinator = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key", token="t"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
        client=SimpleNamespace(
            async_list_devices=AsyncMock(
                return_value=[SimpleNamespace(uuid="u1")])),
    )
    with patch(
            "custom_components.meross_local_cloud.broker_adapter."
            "async_list_devices", AsyncMock(
                return_value=[SimpleNamespace(uuid="u1")])), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=FakeTransport()), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(
                    return_value={"revision": "abc", "count": 3})), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(
                    return_value={"revision": "abc"})):
        adapter = BrokerProfileAdapter(SimpleNamespace(loop=None), coordinator)
        await adapter.async_start()

    assert adapter.summary()["state"] == "connected"
    assert adapter.summary()["profiles"] == 3
    assert adapter.descriptors["u1"]["type"] == "mrs100"
    assert "Appliance.RollerShutter.State" in \
        adapter.descriptors["u1"]["abilities"]


async def test_adapter_opens_a_single_mqtt_transport():
    coordinator_stub = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key", token="t"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
    )
    with patch(
            "custom_components.meross_local_cloud.broker_adapter."
            "async_list_devices", AsyncMock(
                return_value=[SimpleNamespace(uuid="u1")])), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "BrokerMqttTransport",
                return_value=FakeTransport()) as factory, \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(
                    return_value={"revision": "abc", "count": 0})), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_catalog", AsyncMock(
                    return_value={"revision": "abc", "profiles": []})):
        adapter = BrokerProfileAdapter(
            SimpleNamespace(loop=None), coordinator_stub)
        await adapter.async_start()

    factory.assert_called_once()
    assert adapter.summary()["state"] == "connected"


async def test_adapter_aborts_after_the_first_descriptor_failure():
    class FailingTransport(FakeTransport):
        calls = 0

        async def async_describe(self, device_uuid):
            FailingTransport.calls += 1
            raise TimeoutError("GET Appliance.System.All")

    coordinator = SimpleNamespace(
        credentials=SimpleNamespace(user_id="1", key="key", token="t"),
        mqtt_address=("localhost", 2001),
        mqtt_ssl_context=object(),
        http_api_endpoint="https://broker:2004",
        client=SimpleNamespace(
            async_list_devices=AsyncMock(return_value=[
                SimpleNamespace(uuid="u1"), SimpleNamespace(uuid="u2")])),
    )
    with patch(
            "custom_components.meross_local_cloud.broker_adapter."
            "async_list_devices", AsyncMock(
                return_value=[SimpleNamespace(uuid="u1"),
                              SimpleNamespace(uuid="u2")])), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
            "BrokerMqttTransport", return_value=FailingTransport()), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
                "async_fetch_revision", AsyncMock(
                    return_value={"revision": "abc", "count": 3})), \
            patch(
                "custom_components.meross_local_cloud.broker_adapter."
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
