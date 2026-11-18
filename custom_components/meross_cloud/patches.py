"""Runtime fixes for bugs in the pinned meross_iot release."""

import json
import ssl

import aiohttp
import meross_iot.http_api as meross_http_api
import paho.mqtt.client as mqtt
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.model.enums import Namespace

_PATCH_FLAG = "_meross_local_light_patch"
_MQTT_SSL_PATCH_FLAG = "_meross_local_mqtt_ssl_patch"
_MQTT_ACK_PATCH_FLAG = "_meross_local_mqtt_ack_patch"


def patch_mqtt_acks_on_user_topic() -> None:
    """Resolve command ACKs delivered on the user topic.

    The local broker agent forwards every device publish to
    ``/app/<userId>/subscribe``, including GETACK/SETACK replies. meross_iot
    only matches ACKs on the app-specific response topic, so those replies were
    ignored and every command ended in CommandTimeoutError.
    """
    from meross_iot.manager import MerossManager, _handle_future
    from meross_iot.model.exception import CommandError
    from meross_iot.utilities.mqtt import (
        build_client_user_topic,
        verify_message_signature,
    )

    if getattr(MerossManager, _MQTT_ACK_PATCH_FLAG, False):
        return

    original_on_message = MerossManager._on_message

    def _on_message(self, client, userdata, msg):
        try:
            if msg.topic == build_client_user_topic(self._cloud_creds.user_id):
                raw = msg.payload
                text = raw.decode("utf8") if isinstance(raw, (bytes, bytearray)) else raw
                message = json.loads(text)
                header = message.get("header") or {}
                method = header.get("method")
                if method in ("SETACK", "GETACK", "ERROR") and \
                        verify_message_signature(header, self._cloud_creds.key):
                    message_id = header.get("messageId")
                    future = self._pending_messages_futures.get(message_id)
                    if future is not None:
                        if method == "ERROR":
                            error = CommandError(
                                error_payload=message.get("payload"))
                            self._loop.call_soon_threadsafe(
                                _handle_future, future, None, error)
                        else:
                            self._loop.call_soon_threadsafe(
                                _handle_future, future, message, None)
                        del self._pending_messages_futures[message_id]
                        return
        except Exception:  # noqa: BLE001 - fall back to the library handler
            pass
        return original_on_message(self, client, userdata, msg)

    MerossManager._on_message = _on_message
    setattr(MerossManager, _MQTT_ACK_PATCH_FLAG, True)


def create_mqtt_ssl_context(
        ca_pem: str | None, skip_validation: bool,
        check_hostname: bool = False) -> ssl.SSLContext:
    """Build the MQTT TLS context outside the event loop.

    paho's ``tls_set`` loads the CA bundle synchronously; Home Assistant flags
    that as a blocking call when the manager connects from the event loop.
    Loading the PEM here lets the caller run this in an executor.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if skip_validation:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = check_hostname
    if ca_pem:
        context.load_verify_locations(cadata=ca_pem)
    return context


def patch_mqtt_client_ssl_context() -> None:
    """Use a preloaded SSL context instead of paho's blocking ``tls_set``."""
    from meross_iot.manager import MerossManager

    if getattr(MerossManager, _MQTT_SSL_PATCH_FLAG, False):
        return

    original_new_mqtt_client = MerossManager._new_mqtt_client

    def _new_mqtt_client(self):
        context = getattr(self, "_ha_ssl_context", None)
        if context is None:
            return original_new_mqtt_client(self)
        client = mqtt.Client(
            client_id=self._client_id,
            protocol=mqtt.MQTTv311,
            clean_session=False,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        )
        client.username_pw_set(
            username=self._cloud_creds.user_id, password=self._mqtt_password
        )
        client.tls_set_context(context)
        client.tls_insecure_set(self._mqtt_skip_validation)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.on_subscribe = self._on_subscribe
        return client

    MerossManager._new_mqtt_client = _new_mqtt_client
    setattr(MerossManager, _MQTT_SSL_PATCH_FLAG, True)


def set_http_cert_validation(
        skip_validation: bool,
        ssl_context: ssl.SSLContext | None = None) -> None:
    """Make meross_iot trust the local broker certificate.

    meross_iot creates a bare aiohttp.ClientSession for every API call and
    offers no way to supply an SSL context. Replacing the module-level symbol
    keeps the change local to that library: Home Assistant's own sessions and
    other integrations are untouched.
    """
    if skip_validation:
        meross_http_api.ClientSession = _unverified_client_session
    elif ssl_context is not None:
        meross_http_api.ClientSession = _verified_client_session_factory(
            ssl_context)
    else:
        meross_http_api.ClientSession = aiohttp.ClientSession


def _unverified_client_session(*args, **kwargs):
    """Build an aiohttp session that does not validate the server chain."""
    kwargs.setdefault("connector", aiohttp.TCPConnector(ssl=False))
    return aiohttp.ClientSession(*args, **kwargs)


def _verified_client_session_factory(ssl_context: ssl.SSLContext):
    """Build aiohttp sessions that validate the chain against the broker CA."""
    def _session(*args, **kwargs):
        kwargs.setdefault(
            "connector", aiohttp.TCPConnector(ssl=ssl_context))
        return aiohttp.ClientSession(*args, **kwargs)
    return _session


def apply_patches() -> None:
    """Apply idempotent fixes before any device instance is built."""
    if getattr(LightMixin, _PATCH_FLAG, False):
        return

    original_async_handle_update = LightMixin.async_handle_update

    async def async_handle_update(self, namespace, data):
        if namespace == Namespace.SYSTEM_ALL:
            digest = (data.get("all") or {}).get("digest") or {}
            light = digest.get("light")
            if not isinstance(light, dict):
                # Devices such as the MRS100 expose the Light ability but
                # report no "light" digest. The upstream implementation uses
                # a list as default and then calls .get() on it, raising
                # AttributeError and failing every entity update.
                return await super(LightMixin, self).async_handle_update(
                    namespace=namespace, data=data
                )
        return await original_async_handle_update(self, namespace, data)

    LightMixin.async_handle_update = async_handle_update
    setattr(LightMixin, _PATCH_FLAG, True)
