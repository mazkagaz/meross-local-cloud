"""MQTT transport to the local broker using the vendored merossclient."""
from __future__ import annotations

import logging
import ssl

from .vendor.merossclient import DeviceDescriptor, HostAddress
from .vendor.merossclient.client.mqtt import MQTTAppClient
from .vendor.merossclient.protocol.message import MerossResponse

_LOGGER = logging.getLogger(__name__)


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
        _LOGGER.debug("MQTT RX %s %s %s", getattr(mqtt_msg, "topic", None),
                      message.namespace, message.method)
        transaction = self._transactions.get(message.messageid)
        if transaction is None:
            _LOGGER.debug("MQTT RX without pending transaction: %s",
                          message.messageid)
            return
        transaction.set_result(message)


class BrokerMqttTransport:
    """App-behavioured MQTT connection to the local broker."""

    def __init__(self, host: str, port: int, user_id: str, key: str,
                 ssl_context: ssl.SSLContext, loop, timeout: float = 15):
        self._host = host
        self._port = port
        self._user_id = str(user_id)
        self._key = key
        self._ssl_context = ssl_context
        self._loop = loop
        self._timeout = timeout
        self._connection: MQTTAppClient | None = None

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
        await connection.async_connect(timeout=self._timeout)
        self._connection = connection
        _LOGGER.debug("Broker MQTT transport connected to %s:%s",
                      self._host, self._port)

    async def async_describe(self, device_uuid: str) -> DeviceDescriptor:
        if self._connection is None:
            raise RuntimeError("MQTT transport is not connected")
        client = MQTTAppClient.Client(
            f"broker_cloud:{device_uuid}",
            _LOGGER,
            uuid=device_uuid,
            connection=self._connection,
            key=self._key,
            loop=self._loop,
            timeout=self._timeout,
        )
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
        try:
            await connection.async_shutdown()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            _LOGGER.debug("Error while shutting the broker MQTT transport",
                          exc_info=True)
