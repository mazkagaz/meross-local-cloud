"""Local broker CA bootstrap helpers."""
import logging
import ssl

import aiohttp

_LOGGER = logging.getLogger(__name__)


def build_ca_url(endpoint: str) -> str:
    return endpoint.rstrip("/") + "/ca.crt"


async def async_fetch_broker_ca(endpoint: str, timeout: int = 10):
    """Fetch the broker CA over the user-selected local endpoint.

    The HTTPS certificate cannot be validated before its CA is known, so the
    bootstrap fetch accepts the connection as-is. The CA is then used to verify
    the broker's HTTP and MQTT certificates.
    """
    url = build_ca_url(endpoint)
    connector = (
        aiohttp.TCPConnector(ssl=False) if url.startswith("https://") else None
    )
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    return None
                pem = await response.text()
    except Exception as err:  # noqa: BLE001 - best-effort bootstrap
        _LOGGER.debug("Could not fetch the broker CA from %s: %s", url, err)
        return None

    if "BEGIN CERTIFICATE" not in pem:
        _LOGGER.warning("The broker CA endpoint %s did not return a PEM certificate", url)
        return None
    return pem


def write_ca_bundle(pem: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(pem)


def build_http_ssl_context(ca_path: str) -> ssl.SSLContext:
    """Verify the broker certificate chain, but not the configured hostname.

    The local certificate does not necessarily include the LAN IP used by the
    integration; the chain still has to be signed by the stored broker CA.
    """
    context = ssl.create_default_context(cafile=ca_path)
    context.check_hostname = False
    return context
