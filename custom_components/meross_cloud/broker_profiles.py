"""Fetch the device profile catalog from the local broker."""
from __future__ import annotations

import logging
from typing import Any, Dict

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
