"""MQTT transport to the local broker using the vendored merossclient."""
from __future__ import annotations

import asyncio
import logging
import ssl

from .vendor.merossclient import DeviceDescriptor, HostAddress
from .vendor.merossclient.client.mqtt import MQTTAppClient
from .vendor.merossclient.protocol.message import MerossRequest, MerossResponse

_LOGGER = logging.getLogger(__name__)

# The vendored client keeps the Meross cloud guard (200 messages/hour,
# 5-message burst over 90 s). The local broker has no cloud-ban risk and
# interactive cover commands need a much shorter window.
LOCAL_MQTT_RATE = 1.0  # sustained messages per second, per device
LOCAL_MQTT_BURST = 5  # burst size over LOCAL_MQTT_BURST seconds


class _BrokerAppClient(MQTTAppClient):
    """App client that resolves pending transactions from MQTT replies.

    meross_lan implements this dispatch in its Home Assistant profile layer,
    which is not part of the vendored subset; without it every request waits
    for its timeout.
    """

    def on_message(self, mqtt_msg, /):
        try:
            payload = mqtt_msg.payload
            text = payload.decode("utf-8") if isinstance(
                payload, (bytes, bytearray)) else payload
            message = MerossResponse(text)
        except Exception:  # noqa: BLE001 - malformed messages are ignored
            _LOGGER.debug("Unparseable MQTT message on %s",
                          getattr(mqtt_msg, "topic", None), exc_info=True)
            return
        try:
            namespace = message.namespace
            method = message.method
            messageid = message.messageid
        except Exception:  # noqa: BLE001 - header is missing or malformed
            _LOGGER.debug("MQTT RX with a malformed header on %s ignored",
                          getattr(mqtt_msg, "topic", None))
            return
        _LOGGER.debug("MQTT RX %s %s %s", getattr(mqtt_msg, "topic", None),
                      namespace, method)
        transaction = self._transactions.get(messageid)
        if transaction is not None:
            # Solicited replies are consumed by their requester (describe or
            # the central scheduler), so they must not be dispatched twice.
            transaction.set_result(message)
            return
        listener = getattr(self, "message_listener", None)
        if listener is not None:
            try:
                listener(message)
            except Exception:  # noqa: BLE001 - dispatch must not break MQTT
                _LOGGER.debug("MQTT payload listener failed",
                              exc_info=True)


class BrokerMqttTransport:
    """App-behavioured MQTT connection to the local broker."""

    def __init__(self, host: str, port: int, user_id: str, key: str,
                 ssl_context: ssl.SSLContext, loop, timeout: float = 15,
                 message_listener=None, state_listener=None):
        self._host = host
        self._port = port
        self._user_id = str(user_id)
        self._key = key
        self._ssl_context = ssl_context
        self._loop = loop
        self._message_listener = message_listener
        self._state_listener = state_listener
        self._timeout = timeout
        self._connection: MQTTAppClient | None = None
        self._priority_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return bool(self._connection and self._connection.is_connected)

    async def async_connect(self) -> None:
        connection = _BrokerAppClient(
            HostAddress(self._host, self._port),
            _LOGGER,
            user_id=self._user_id,
            key=self._key,
            sslcontext=self._ssl_context,
            loop=self._loop,
            timeout=self._timeout,
        )
        connection.message_listener = self._message_listener
        connection.rl_rate = LOCAL_MQTT_RATE
        connection.rl_window_size = LOCAL_MQTT_BURST
        connection.connect_broadcast.add(self._on_connect)
        connection.disconnect_broadcast.add(self._on_disconnect)
        await connection.async_connect(timeout=self._timeout)
        self._connection = connection
        _LOGGER.debug("Broker MQTT transport connected to %s:%s",
                      self._host, self._port)

    def _on_connect(self, connection) -> None:
        if self._state_listener is not None:
            self._state_listener(True)

    def _on_disconnect(self, connection) -> None:
        if self._state_listener is not None:
            self._state_listener(False)

    def _device_client(self, device_uuid: str) -> MQTTAppClient.Client:
        if self._connection is None:
            raise RuntimeError("MQTT transport is not connected")
        return MQTTAppClient.Client(
            f"broker_cloud:{device_uuid}",
            _LOGGER,
            uuid=device_uuid,
            connection=self._connection,
            key=self._key,
            loop=self._loop,
            timeout=self._timeout,
        )

    async def async_request(self, device_uuid: str, namespace: str,
                            method: str, payload) -> MerossResponse:
        client = self._device_client(device_uuid)
        try:
            return await client.async_request(
                namespace, method, payload, timeout=self._timeout)
        finally:
            client.shutdown()

    async def async_publish_priority(self, device_uuid: str, namespace: str,
                                     method: str, payload) -> None:
        """Publish immediately, without ACK wait or MQTT rate limiting.

        Used for safety commands such as roller-shutter stop: the ACK, when it
        arrives, is delivered to the message listener as an unsolicited push.
        """
        connection = self._connection
        if connection is None:
            raise RuntimeError("MQTT transport is not connected")
        client = self._device_client(device_uuid)
        try:
            request = MerossRequest(
                namespace, method, payload, client.key, client.from_)
            async with self._priority_lock:
                rate = connection.rl_rate
                connection.rl_rate = 0
                try:
                    await connection.async_publish_raw(
                        request, uuid=device_uuid)
                finally:
                    connection.rl_rate = rate
        finally:
            client.shutdown()

    async def async_request_multiple(self, device_uuid: str,
                                     requests) -> MerossResponse:
        client = self._device_client(device_uuid)
        try:
            return await client.async_request_multiple(
                requests, timeout=self._timeout)
        finally:
            client.shutdown()

    async def async_describe(self, device_uuid: str) -> DeviceDescriptor:
        client = self._device_client(device_uuid)
        _LOGGER.debug("Requesting System.All/Ability for %s", device_uuid)
        try:
            descriptor = await client.async_identify(timeout=self._timeout)
            _LOGGER.debug("Descriptor received for %s (%s)",
                          device_uuid, descriptor.type)
            return descriptor
        except Exception as err:  # noqa: BLE001 - logged by the adapter
            _LOGGER.debug("Describe failed for %s: %s: %s", device_uuid,
                          type(err).__name__, err)
            raise
        finally:
            client.shutdown()

    async def async_stop(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        connection.connect_broadcast.remove(self._on_connect)
        connection.disconnect_broadcast.remove(self._on_disconnect)
        try:
            await connection.async_shutdown()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            _LOGGER.debug("Error while shutting the broker MQTT transport",
                          exc_info=True)
