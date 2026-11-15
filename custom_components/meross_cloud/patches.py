"""Runtime fixes for bugs in the pinned meross_iot release."""

from meross_iot.controller.mixins.light import LightMixin
from meross_iot.model.enums import Namespace

_PATCH_FLAG = "_meross_local_light_patch"


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
