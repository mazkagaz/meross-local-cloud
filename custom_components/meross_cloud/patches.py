"""Runtime fixes for bugs in the pinned meross_iot release."""

import aiohttp
import meross_iot.http_api as meross_http_api
from meross_iot.controller.mixins.light import LightMixin
from meross_iot.model.enums import Namespace

_PATCH_FLAG = "_meross_local_light_patch"


def set_http_cert_validation(skip_validation: bool) -> None:
    """Make meross_iot accept the self-signed local broker certificate.

    meross_iot creates a bare aiohttp.ClientSession for every API call and
    offers no way to supply an SSL context. Replacing the module-level symbol
    keeps the change local to that library: Home Assistant's own sessions and
    other integrations are untouched.
    """
    meross_http_api.ClientSession = (
        _unverified_client_session if skip_validation else aiohttp.ClientSession
    )


def _unverified_client_session(*args, **kwargs):
    """Build an aiohttp session that does not validate the server chain."""
    kwargs.setdefault("connector", aiohttp.TCPConnector(ssl=False))
    return aiohttp.ClientSession(*args, **kwargs)


def apply_patches() -> None:
    """Apply idempotent fixes before any device instance is built."""
    if getattr(LightMixin, _PATCH_FLAG, False):
        return

    original_async_handle_update = LightMixin.async_handle_update

    async def async_handle_update(self, namespace, data):
        if namespace == Namespace.SYSTEM_ALL:
            digest = (data.get("all") or {}).get("digest") or {}
            light = digest.get("light")
            if not isinstance(light, dict):
                # Devices such as the MRS100 expose the Light ability but
                # report no "light" digest. The upstream implementation uses
                # a list as default and then calls .get() on it, raising
                # AttributeError and failing every entity update.
                return await super(LightMixin, self).async_handle_update(
                    namespace=namespace, data=data
                )
        return await original_async_handle_update(self, namespace, data)

    LightMixin.async_handle_update = async_handle_update
    setattr(LightMixin, _PATCH_FLAG, True)
