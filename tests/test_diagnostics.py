from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud.common import (
    CONF_CA_PEM,
    CONF_HTTP_ENDPOINT,
    CONF_MQTT_SKIP_CERT_VALIDATION,
    CONF_OVERRIDE_MQTT_ENDPOINT,
    CONF_STORED_CREDS,
    DEVICE_LIST_COORDINATOR,
    DOMAIN,
    MANAGER,
)
from custom_components.meross_cloud.diagnostics import (
    async_get_config_entry_diagnostics,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _ca_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                       critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def test_diagnostics_redacts_secrets(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HTTP_ENDPOINT: "https://10.0.0.5:2004",
            CONF_OVERRIDE_MQTT_ENDPOINT: "10.0.0.5:2001",
            CONF_MQTT_SKIP_CERT_VALIDATION: True,
            CONF_CA_PEM: _ca_pem(),
            CONF_STORED_CREDS: {
                "token": "secret-token",
                "key": "secret-key",
                "password": "secret-password",
                "user_email": "local-user",
                "user_id": "1",
            },
        },
    )
    entry.add_to_hass(hass)

    device = SimpleNamespace(
        name="volet",
        uuid="uuid-1",
        type="mrs100",
        firmware_version="7.6.20",
        hardware_version="7.0.0",
        online_status=SimpleNamespace(name="ONLINE"),
    )
    manager = SimpleNamespace(find_devices=lambda: [device])
    coordinator = SimpleNamespace(
        _mqtt_ssl_context_verified=object(), _ca_check_hostname=True)
    hass.data[DOMAIN] = {
        MANAGER: manager,
        DEVICE_LIST_COORDINATOR: coordinator,
    }

    result = await async_get_config_entry_diagnostics(hass, entry)

    creds = result["entry"]["stored_credentials"]
    assert creds["token"] == "**REDACTED**"
    assert creds["key"] == "**REDACTED**"
    assert creds["password"] == "**REDACTED**"
    assert creds["user_email"] == "local-user"

    assert result["tls"]["valid_ca"] is True
    assert len(result["tls"]["ca_fingerprint"]) == 64
    assert result["runtime"]["manager_started"] is True
    assert result["runtime"]["devices"][0]["uuid"] == "uuid-1"
