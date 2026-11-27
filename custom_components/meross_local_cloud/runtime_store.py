"""Persist raw profile entity values across reloads and HA restarts."""
from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, Mapping, Optional

from homeassistant.helpers.storage import Store

from .common import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_KEY = f"{DOMAIN}.runtime_state"
STORE_VERSION = 1
SAVE_DELAY = 5.0
MAX_VALUE_LENGTH = 256


def _scalar(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, int):
        return True
    return isinstance(value, str) and len(value) <= MAX_VALUE_LENGTH


def _clean_values(values: Any,
                  allowed: Optional[set] = None) -> Dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {
        key: value for key, value in values.items()
        if isinstance(key, str) and _scalar(value)
        and (allowed is None or key in allowed)
    }


def _state_fields(spec) -> set:
    fields = set()
    if spec.state is not None:
        fields.update(spec.state.fields)
    if spec.movement is not None:
        fields.update(spec.movement.fields)
    return fields


def _entity_payload(spec, state) -> Dict[str, Any]:
    return {
        "platform": spec.platform,
        "values": _clean_values(state.values, _state_fields(spec)),
    }


def snapshot_runtimes(runtimes: Mapping[str, Any]) -> Dict[str, Any]:
    """Serialize the current raw runtime values."""
    devices: Dict[str, Any] = {}
    for uuid, runtime in runtimes.items():
        profile = runtime.profile
        entities = {
            key: _entity_payload(profile.entities[key], state)
            for key, state in runtime.entities.items()
            if key in profile.entities
        }
        subdevices: Dict[str, Any] = {}
        for sid, subdevice in runtime.subdevices.items():
            template = subdevice.template
            subdevices[sid] = {
                "template": template.name or template.uid,
                "entities": {
                    key: _entity_payload(template.entities[key], state)
                    for key, state in subdevice.entities.items()
                    if key in template.entities
                },
            }
        devices[uuid] = {
            "profile": profile.profile_id,
            "profile_version": profile.version,
            "updated": time.time(),
            "entities": entities,
            "subdevices": subdevices,
        }
    return {"version": STORE_VERSION, "devices": devices}


def _apply_entity(stored: Any, spec, state) -> bool:
    if not isinstance(stored, Mapping):
        return False
    if stored.get("platform") != spec.platform:
        return False
    values = _clean_values(stored.get("values"), _state_fields(spec))
    if not values:
        return False
    state.values.update(values)
    return True


def restore_runtimes(data: Any, runtimes: Mapping[str, Any]) -> int:
    """Seed runtimes from a previous snapshot; return restored entities."""
    if not isinstance(data, Mapping) or data.get("version") != STORE_VERSION:
        return 0
    devices = data.get("devices")
    if not isinstance(devices, Mapping):
        return 0
    restored = 0
    for uuid, runtime in runtimes.items():
        stored = devices.get(uuid)
        if not isinstance(stored, Mapping):
            continue
        if stored.get("profile") != runtime.profile.profile_id:
            continue
        entities = stored.get("entities")
        if isinstance(entities, Mapping):
            for key, state in runtime.entities.items():
                spec = runtime.profile.entities.get(key)
                if spec is not None and _apply_entity(
                        entities.get(key), spec, state):
                    restored += 1
        subdevices = stored.get("subdevices")
        if not isinstance(subdevices, Mapping):
            continue
        for sid, subdevice in runtime.subdevices.items():
            sub_stored = subdevices.get(sid)
            if not isinstance(sub_stored, Mapping):
                continue
            template = subdevice.template
            if sub_stored.get("template") != (template.name or template.uid):
                continue
            sub_entities = sub_stored.get("entities")
            if not isinstance(sub_entities, Mapping):
                continue
            for key, state in subdevice.entities.items():
                spec = template.entities.get(key)
                if spec is not None and _apply_entity(
                        sub_entities.get(key), spec, state):
                    restored += 1
    return restored


class RuntimeStateStore:
    """HA Store wrapper with explicit snapshot/restore helpers."""

    def __init__(self, hass) -> None:
        self._store = Store(hass, STORE_VERSION, STORE_KEY)

    async def async_load(self) -> Optional[Dict[str, Any]]:
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - restore is best effort
            _LOGGER.debug("Runtime state load failed: %s", err)
            return None
        return data if isinstance(data, dict) else None

    async def async_save(self, runtimes: Mapping[str, Any]) -> None:
        try:
            await self._store.async_save(snapshot_runtimes(runtimes))
        except Exception as err:  # noqa: BLE001 - persistence is best effort
            _LOGGER.debug("Runtime state save failed: %s", err)
