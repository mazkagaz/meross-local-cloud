"""MQTT transport to the local broker using the vendored merossclient."""
from __future__ import annotations

import logging
import ssl

from .vendor.merossclient import DeviceDescriptor, HostAddress
from .vendor.merossclient.client.mqtt import MQTTAppClient

_LOGGER = logging.getLogger(__name__)


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
        connection = MQTTAppClient(
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
        try:
            return await client.async_identify(timeout=self._timeout)
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
