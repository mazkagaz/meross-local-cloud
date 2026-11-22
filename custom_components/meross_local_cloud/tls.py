"""TLS helpers for the local broker CA and server certificate."""

import hashlib
import socket
import ssl
from typing import Optional, Set

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID


def parse_certificate(pem: str) -> Optional[x509.Certificate]:
    try:
        return x509.load_pem_x509_certificate(pem.encode())
    except ValueError:
        return None


def is_ca(certificate: x509.Certificate) -> bool:
    try:
        constraints = certificate.extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS
        ).value
    except x509.ExtensionNotFound:
        return False
    return bool(constraints.ca)


def fingerprint(certificate: x509.Certificate) -> str:
    return hashlib.sha256(certificate.public_bytes(Encoding.DER)).hexdigest()


def certificate_hostnames(certificate: x509.Certificate) -> Set[str]:
    hostnames: Set[str] = set()
    try:
        san = certificate.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        ).value
    except x509.ExtensionNotFound:
        return hostnames
    for name in san:
        if isinstance(name, x509.DNSName):
            hostnames.add(name.value.lower().rstrip("."))
        elif isinstance(name, x509.IPAddress):
            hostnames.add(str(name.value))
    return hostnames


def host_is_covered(certificate: x509.Certificate,
                    host: Optional[str]) -> bool:
    if not host:
        return False
    return host.lower().strip("[]").rstrip(".") in certificate_hostnames(
        certificate)


def build_client_ssl_context(ca_pem: str,
                             check_hostname: bool) -> ssl.SSLContext:
    """Build a client context that trusts only the broker CA."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = check_hostname
    context.load_verify_locations(cadata=ca_pem)
    return context


async def async_fetch_ca(endpoint: str) -> Optional[str]:
    """Download /ca.crt from the broker without validating its TLS yet."""
    url = endpoint.rstrip("/") + "/ca.crt"
    connector = aiohttp.TCPConnector(ssl=False)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return None
                text = await response.text()
    except Exception:  # noqa: BLE001 - discovery is best effort
        return None
    if "BEGIN CERTIFICATE" not in text:
        return None
    return text.strip() + "\n"


def fetch_server_certificate(host: str, port: int) -> Optional[str]:
    """Return the broker server certificate in PEM format."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
    except OSError:
        return None
    if not der:
        return None
    return ssl.DER_cert_to_PEM_cert(der)
