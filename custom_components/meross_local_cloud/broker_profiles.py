"""Fetch and verify the device profile catalog from the local broker."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .broker_http import BrokerHttpClient


async def async_fetch_revision(http: BrokerHttpClient) -> Dict[str, Any]:
    return await http.async_post("/v1/Device/profiles/rev")


async def async_fetch_catalog(http: BrokerHttpClient) -> Dict[str, Any]:
    return await http.async_post("/v1/Device/profiles")


async def async_fetch_public_key(http: BrokerHttpClient
                                 ) -> Dict[str, Any]:
    return await http.async_post("/v1/Device/profiles/pubkey")


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
