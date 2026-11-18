import ipaddress
import ssl
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from custom_components.meross_cloud.tls import (
    build_client_ssl_context,
    certificate_hostnames,
    fingerprint,
    host_is_covered,
    is_ca,
    parse_certificate,
)


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _ca_pem():
    key = _key()
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


def _server_pem(ca_pem):
    ca = parse_certificate(ca_pem)
    # Only the SAN/extension handling is under test here; the server
    # certificate is self-signed by a throwaway key.
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Broker")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                       critical=True)
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("homeassistant.local"),
                x509.IPAddress(ipaddress.ip_address("192.168.1.10")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_ca_and_hostname_helpers():
    ca_pem = _ca_pem()
    ca = parse_certificate(ca_pem)
    assert ca is not None
    assert is_ca(ca)
    assert len(fingerprint(ca)) == 64

    server = parse_certificate(_server_pem(ca_pem))
    assert server is not None
    assert not is_ca(server)
    assert certificate_hostnames(server) == {
        "homeassistant.local", "192.168.1.10"}
    assert host_is_covered(server, "192.168.1.10")
    assert host_is_covered(server, "homeassistant.local")
    assert host_is_covered(server, "HOMEASSISTANT.LOCAL")
    assert not host_is_covered(server, "10.0.0.1")
    assert not host_is_covered(server, None)


def test_invalid_pem_is_rejected():
    assert parse_certificate("not a certificate") is None


def test_client_context_loads_the_ca():
    ca_pem = _ca_pem()
    context = build_client_ssl_context(ca_pem, check_hostname=False)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is False
