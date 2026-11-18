"""Track broker devices that disappeared and offer to remove them."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .common import DOMAIN

_LOGGER = logging.getLogger(__name__)

MISSING_DEVICE_RETENTION = timedelta(hours=48)
_STORAGE_VERSION = 1
_ISSUE_TRANSLATION_KEY = "remove_missing_device"


def issue_id(device_uuid: str) -> str:
    return f"remove_missing_device_{device_uuid}"


class MissingDeviceTracker:
    """Persist the devices seen in the HTTP list and flag long absences.

    Only successful polls must call :meth:`async_update`; a broker outage says
    nothing about the devices and must not start the 48 h countdown.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._store = Store(
            hass, _STORAGE_VERSION, f"{DOMAIN}.missing_devices.{entry_id}")
        self._known: dict[str, dict] = {}
        self._missing: dict[str, str] = {}
        self._loaded = False

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._known = dict(stored.get("known") or {})
        self._missing = dict(stored.get("missing") or {})
        self._loaded = True

    async def async_update(self, devices: Iterable) -> None:
        if not self._loaded:
            await self.async_load()

        seen = {
            device.uuid: getattr(device, "dev_name", None) or device.uuid
            for device in devices
        }
        now = dt_util.utcnow()
        changed = False

        for uuid in list(self._missing):
            if uuid in seen:
                del self._missing[uuid]
                ir.async_delete_issue(self._hass, DOMAIN, issue_id(uuid))
                _LOGGER.info("Device %s is back in the broker list", uuid)
                changed = True

        for uuid, name in seen.items():
            if self._known.get(uuid, {}).get("name") != name:
                self._known[uuid] = {"name": name}
                changed = True

        for uuid, info in self._known.items():
            if uuid in seen:
                continue
            since = self._missing.get(uuid)
            if since is None:
                self._missing[uuid] = now.isoformat()
                _LOGGER.info(
                    "Device %s (%s) disappeared from the broker; its removal "
                    "will be proposed after 48 h", uuid, info.get("name", uuid))
                changed = True
                continue
            if now - datetime.fromisoformat(since) >= MISSING_DEVICE_RETENTION:
                self._raise_issue(uuid, info.get("name") or uuid)

        if changed:
            await self._save()

    async def async_forget(self, device_uuid: str) -> None:
        """Stop tracking a device the user removed."""
        self._known.pop(device_uuid, None)
        self._missing.pop(device_uuid, None)
        ir.async_delete_issue(self._hass, DOMAIN, issue_id(device_uuid))
        if self._loaded:
            await self._save()

    def _raise_issue(self, uuid: str, name: str) -> None:
        if ir.async_get(self._hass).async_get_issue(
                DOMAIN, issue_id(uuid)) is not None:
            return
        _LOGGER.warning(
            "Device %s (%s) has been absent for 48 h; a repair asks whether to "
            "remove it", uuid, name)
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id(uuid),
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=_ISSUE_TRANSLATION_KEY,
            translation_placeholders={"name": name, "uuid": uuid},
            data={"uuid": uuid, "name": name},
        )

    async def _save(self) -> None:
        await self._store.async_save(
            {"known": self._known, "missing": self._missing})
