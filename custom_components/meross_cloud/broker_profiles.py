"""Fetch and verify the device profile catalog from the local broker."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from meross_iot.http_api import MerossHttpClient

_LOGGER = logging.getLogger(__name__)


async def _async_post(client: MerossHttpClient, endpoint: str,
                      path: str) -> Any:
    return await MerossHttpClient._async_authenticated_post(
        url=f"{endpoint.rstrip('/')}{path}",
        params_data={},
        cloud_creds=client.cloud_credentials,
    )


async def async_fetch_revision(client: MerossHttpClient,
                               endpoint: str) -> Dict[str, Any]:
    return await _async_post(client, endpoint, "/v1/Device/profiles/rev")


async def async_fetch_catalog(client: MerossHttpClient,
                              endpoint: str) -> Dict[str, Any]:
    return await _async_post(client, endpoint, "/v1/Device/profiles")


async def async_fetch_public_key(client: MerossHttpClient,
                                 endpoint: str) -> Dict[str, Any]:
    return await _async_post(client, endpoint, "/v1/Device/profiles/pubkey")


def catalog_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items()
            if key not in ("signature", "algorithm")}


def verify_catalog(payload: Dict[str, Any], public_key_pem: str) -> bool:
    """Verify the Ed25519 signature carried by a catalog payload."""
    signature = payload.get("signature")
    if not signature:
        return False
    try:
        key = load_pem_public_key(public_key_pem.encode("utf-8"))
        data = json.dumps(
            catalog_body(payload), sort_keys=True,
            separators=(",", ":")).encode("utf-8")
        key.verify(base64.b64decode(signature), data)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
