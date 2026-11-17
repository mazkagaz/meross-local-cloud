import ssl
from types import SimpleNamespace

import certifi
import paho.mqtt.client as mqtt
from meross_iot.manager import MerossManager

from custom_components.meross_cloud.patches import (
    create_mqtt_ssl_context,
    patch_mqtt_client_ssl_context,
)


def test_context_without_validation():
    context = create_mqtt_ssl_context(None, True)
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_context_verified_with_ca():
    context = create_mqtt_ssl_context(certifi.where(), False)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is False


def test_patched_client_uses_preloaded_context(monkeypatch):
    patch_mqtt_client_ssl_context()
    context = create_mqtt_ssl_context(None, True)
    fake_manager = SimpleNamespace(
        _client_id="app:test",
        _cloud_creds=SimpleNamespace(user_id="1"),
        _mqtt_password="secret",
        _mqtt_skip_validation=True,
        _ha_ssl_context=context,
        _on_connect=None,
        _on_message=None,
        _on_disconnect=None,
        _on_subscribe=None,
    )

    def _blocking_tls_set(*args, **kwargs):
        raise AssertionError("tls_set must not be used: it loads the CA bundle")

    monkeypatch.setattr(mqtt.Client, "tls_set", _blocking_tls_set)
    client = MerossManager._new_mqtt_client(fake_manager)
    assert client._ssl_context is context
