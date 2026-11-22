"""Diagnostics support for Meross Local Cloud."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .common import (
    BROKER_ADAPTER,
    CONF_CA_FINGERPRINT,
    CONF_CA_PEM,
    CONF_HTTP_ENDPOINT,
    CONF_OPT_CUSTOM_USER_AGENT,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DEVICE_LIST_COORDINATOR,
    DOMAIN,
)
from .tls import fingerprint, is_ca, parse_certificate
from .version import MEROSS_INTEGRATION_VERSION

TO_REDACT = {
    "token",
    "key",
    "password",
    "issued_on",
}


def _ca_diagnostics(entry: ConfigEntry) -> dict[str, Any]:
    ca_pem = entry.data.get(CONF_CA_PEM)
    certificate = parse_certificate(ca_pem) if ca_pem else None
    if certificate is None:
        return {
            "available": False,
            "stored_fingerprint": entry.data.get(CONF_CA_FINGERPRINT),
            "valid_ca": False,
        }
    return {
        "available": True,
        "fingerprint": fingerprint(certificate),
        "stored_fingerprint": entry.data.get(CONF_CA_FINGERPRINT),
        "valid_ca": is_ca(certificate),
        "subject": certificate.subject.rfc4514_string(),
        "issuer": certificate.issuer.rfc4514_string(),
        "valid_until": certificate.not_valid_after_utc.isoformat(),
    }


def _device_diagnostics(coordinator) -> list[dict[str, Any]]:
    return [
        {
            "name": device.name,
            "uuid": device.uuid,
            "type": device.device_type,
            "firmware_version": device.firmware,
            "hardware_version": device.hardware,
            "online": "ONLINE" if device.online else "OFFLINE",
        }
        for device in (getattr(coordinator, "data", None) or {}).values()
    ]


async def async_get_config_entry_diagnostics(
        hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN) or {}
    coordinator = runtime.get(DEVICE_LIST_COORDINATOR)
    adapter = runtime.get(BROKER_ADAPTER)
    tls_info = runtime.get("TLS_INFO") or {}

    return {
        "version": {
            "integration": MEROSS_INTEGRATION_VERSION,
        },
        "entry": {
            "http_endpoint": entry.data.get(CONF_HTTP_ENDPOINT),
            "mqtt_endpoint": entry.data.get(CONF_OVERRIDE_MQTT_ENDPOINT),
            "options": {
                "custom_user_agent": entry.options.get(
                    CONF_OPT_CUSTOM_USER_AGENT),
            },
            "stored_credentials": async_redact_data(
                entry.data.get(CONF_STORED_CREDS) or {}, TO_REDACT),
        },
        "tls": {
            "ca": _ca_diagnostics(entry),
            "server": tls_info.get("server"),
            "http": {
                "verified": tls_info.get("http_verified", True),
                "check_hostname": tls_info.get("http_check_hostname"),
                "host": tls_info.get("http_host"),
            },
            "mqtt": {
                "verified": tls_info.get("mqtt_verified", True),
                "check_hostname": tls_info.get("mqtt_check_hostname"),
                "host": tls_info.get("mqtt_host"),
                "verified_context": bool(
                    getattr(coordinator, "_mqtt_ssl_context_verified", None)),
            },
        },
        "devices": _device_diagnostics(coordinator),
        "profile_backend": adapter.summary() if adapter else None,
    }
