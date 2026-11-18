import ipaddress
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud import _async_prepare_tls
from custom_components.meross_cloud.common import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _cert(ca: bool, sans=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test")])
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if sans:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(sans), critical=False)
    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def test_skip_option_still_enables_hostname_checks(hass, monkeypatch):
    ca_pem = _cert(ca=True)
    server_pem = _cert(
        ca=False,
        sans=[
            x509.DNSName("homeassistant.local"),
            x509.IPAddress(ipaddress.ip_address("192.168.1.10")),
        ],
    )

    async def fake_fetch(endpoint):
        return ca_pem

    def fake_server(host, port):
        return server_pem

    monkeypatch.setattr(
        "custom_components.meross_cloud.async_fetch_ca", fake_fetch)
    monkeypatch.setattr(
        "custom_components.meross_cloud.fetch_server_certificate",
        fake_server)

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    pem, fingerprint, context, check_hostname = await _async_prepare_tls(
        hass, entry, "https://192.168.1.10:2004", "192.168.1.10", True)

    assert pem == ca_pem
    assert fingerprint is not None
    assert context is not None
    assert check_hostname is True
