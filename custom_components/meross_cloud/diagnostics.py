"""Diagnostics support for Meross Local Cloud."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .common import (
    CONF_CA_FINGERPRINT,
    CONF_CA_PEM,
    CONF_HTTP_ENDPOINT,
    CONF_HTTP_SKIP_CERT_VALIDATION,
    CONF_MQTT_SKIP_CERT_VALIDATION,
    CONF_OPT_CUSTOM_USER_AGENT,
    CONF_OPT_LAN,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DEVICE_LIST_COORDINATOR,
    DOMAIN,
    MANAGER,
)
from .tls import certificate_hostnames, fingerprint, is_ca, parse_certificate
from .version import MEROSS_INTEGRATION_VERSION, MEROSS_IOT_VERSION

TO_REDACT = {
    "token",
    "key",
    "password",
    "issued_on",
}


def _tls_diagnostics(entry: ConfigEntry) -> dict[str, Any]:
    ca_pem = entry.data.get(CONF_CA_PEM)
    certificate = parse_certificate(ca_pem) if ca_pem else None
    if certificate is None:
        return {
            "ca_available": False,
            "ca_fingerprint": entry.data.get(CONF_CA_FINGERPRINT),
            "valid_ca": False,
        }
    return {
        "ca_available": True,
        "ca_fingerprint": fingerprint(certificate),
        "stored_fingerprint": entry.data.get(CONF_CA_FINGERPRINT),
        "valid_ca": is_ca(certificate),
        "subject": certificate.subject.rfc4514_string(),
        "issuer": certificate.issuer.rfc4514_string(),
        "valid_until": certificate.not_valid_after_utc.isoformat(),
        "hostnames": sorted(certificate_hostnames(certificate)),
    }


def _device_diagnostics(manager) -> list[dict[str, Any]]:
    devices = []
    for device in manager.find_devices():
        devices.append({
            "name": device.name,
            "uuid": device.uuid,
            "type": device.type,
            "firmware_version": device.firmware_version,
            "hardware_version": device.hardware_version,
            "online": (
                device.online_status.name if device.online_status else None
            ),
        })
    return devices


async def async_get_config_entry_diagnostics(
        hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN) or {}
    manager = runtime.get(MANAGER)
    coordinator = runtime.get(DEVICE_LIST_COORDINATOR)

    return {
        "version": {
            "integration": MEROSS_INTEGRATION_VERSION,
            "meross_iot": MEROSS_IOT_VERSION,
        },
        "entry": {
            "http_endpoint": entry.data.get(CONF_HTTP_ENDPOINT),
            "mqtt_endpoint": entry.data.get(CONF_OVERRIDE_MQTT_ENDPOINT),
            "http_skip_cert_validation": entry.data.get(
                CONF_HTTP_SKIP_CERT_VALIDATION),
            "mqtt_skip_cert_validation": entry.data.get(
                CONF_MQTT_SKIP_CERT_VALIDATION),
            "options": {
                "custom_user_agent": entry.options.get(
                    CONF_OPT_CUSTOM_USER_AGENT),
                "lan_transport_mode": entry.options.get(CONF_OPT_LAN),
            },
            "stored_credentials": async_redact_data(
                entry.data.get(CONF_STORED_CREDS) or {}, TO_REDACT),
        },
        "tls": _tls_diagnostics(entry),
        "runtime": {
            "manager_started": manager is not None,
            "mqtt_verified_context": bool(
                getattr(coordinator, "_mqtt_ssl_context_verified", None)),
            "ca_check_hostname": bool(
                getattr(coordinator, "_ca_check_hostname", False)),
            "devices": _device_diagnostics(manager) if manager else [],
        },
    }
