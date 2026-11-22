"""Runtime dispatch of MQTT payloads into compiled profile state (D2.2.4).

The dispatcher is deliberately pure: it only reads decoded payloads, applies
compiled state paths and stores scalar values. It never raises to the MQTT
layer and never creates Home Assistant entities or polls.
"""
from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import CompiledProfile, EntitySpec, StateSpec, SubDeviceTemplate
from .paths import MISSING, get_path

_LOGGER = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 256 * 1024
MAX_ERRORS = 20
STATE_METHODS = frozenset({"GETACK", "SETACK", "PUSH"})


@dataclass
class EntityState:
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubDeviceRuntime:
    subdevice_id: str
    template: SubDeviceTemplate
    entities: Dict[str, EntityState] = field(default_factory=dict)


@dataclass
class DeviceRuntime:
    """State for one matched device, its hub entities and subdevices."""

    uuid: str
    profile: CompiledProfile
    entities: Dict[str, EntityState] = field(default_factory=dict)
    subdevices: Dict[str, SubDeviceRuntime] = field(default_factory=dict)
    messages: int = 0
    updates: int = 0
    ignored: int = 0
    errors: List[str] = field(default_factory=list)
    listeners: List[Callable[[], None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for entity in self.profile.entities.values():
            self.entities[entity.key] = EntityState()

    def add_subdevice(self, subdevice_id: str,
                      template: SubDeviceTemplate) -> None:
        runtime = SubDeviceRuntime(subdevice_id, template)
        for entity in template.entities.values():
            runtime.entities[entity.key] = EntityState()
        self.subdevices[subdevice_id] = runtime

    def dispatch(self, namespace: Any, method: Any, payload: Any) -> int:
        """Apply one payload and return the number of updated properties."""
        self.messages += 1
        if not isinstance(namespace, str) or not namespace:
            return self._ignore("missing namespace")
        if method not in STATE_METHODS:
            return self._ignore(f"method {method!r} does not carry state")
        if not isinstance(payload, dict):
            return self._ignore("payload is not an object")
        if _payload_too_large(payload):
            self._error("payload exceeds size limit or is not serializable")
            return self._ignore("payload too large")

        applied = 0
        for entity in self.profile.entities.values():
            for state in (entity.state, entity.movement):
                if state is not None and state.namespace == namespace:
                    applied += self._apply(
                        self.entities[entity.key], entity, state, payload)

        for runtime in self.subdevices.values():
            document = _subdevice_document(payload, runtime.subdevice_id)
            if document is None:
                continue
            for entity in runtime.template.entities.values():
                for state in (entity.state, entity.movement):
                    if state is not None and state.namespace == namespace:
                        applied += self._apply(
                            runtime.entities[entity.key], entity, state,
                            document)

        if applied:
            self.updates += applied
            self._notify()
        else:
            self.ignored += 1
        return applied

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self.listeners.append(callback)

        def remove() -> None:
            with contextlib.suppress(ValueError):
                self.listeners.remove(callback)

        return remove

    def _notify(self) -> None:
        for callback in list(self.listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001 - a listener never breaks state
                _LOGGER.debug("Runtime listener failed", exc_info=True)

    def _ignore(self, reason: str) -> int:
        self.ignored += 1
        _LOGGER.debug("Runtime %s ignored payload: %s", self.uuid, reason)
        return 0

    def _error(self, message: str) -> None:
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(f"{self.uuid}: {message}")
        _LOGGER.debug("Runtime %s error: %s", self.uuid, message)

    def _apply(self, state: EntityState, entity: EntitySpec,
               spec: StateSpec, document: Dict[str, Any]) -> int:
        applied = 0
        if spec.select_path is not None:
            document = _select_by_channel(
                document, spec.select_path, spec.select_key, spec.channel)
            if document is None:
                return 0
        elif spec.channel is not None:
            payload_channel = document.get("channel")
            if payload_channel is not None and payload_channel != spec.channel:
                return 0
        for prop, field in spec.fields.items():
            try:
                value = get_path(document, field.path)
                if value is MISSING:
                    continue
                if isinstance(value, (dict, list)):
                    self._error(
                        f"{entity.key}: unexpected {type(value).__name__} "
                        f"for {prop}")
                    continue
                if field.on_values is not None:
                    state.values[prop] = value in field.on_values
                    applied += 1
                    continue
                if (field.scale is not None or field.offset is not None
                        or spec.scale is not None):
                    if isinstance(value, bool) or not isinstance(
                            value, (int, float)):
                        self._error(
                            f"{entity.key}: cannot scale "
                            f"{type(value).__name__} for {prop}")
                        continue
                    value = (value * (field.scale if field.scale is not None
                                      else 1)
                             + (field.offset or 0))
                    if spec.scale is not None:
                        value = value * spec.scale
                state.values[prop] = value
                applied += 1
            except Exception as err:  # noqa: BLE001 - never break dispatch
                self._error(f"{entity.key}: {type(err).__name__}")
        return applied


def _select_by_channel(document: Dict[str, Any], path: str, key: str,
                       channel: Optional[int]) -> Optional[Dict[str, Any]]:
    """Return the list item whose key equals channel, or None."""
    if channel is None:
        return None
    items = get_path(document, path)
    if isinstance(items, dict):
        if key in items:
            return items if items.get(key) == channel else None
        return items if channel == 0 else None
    if not isinstance(items, (list, tuple)):
        return None
    for item in items:
        if isinstance(item, dict) and item.get(key) == channel:
            return item
    return None


def _payload_too_large(payload: Dict[str, Any]) -> bool:
    try:
        return len(json.dumps(payload, separators=(",", ":"))) > \
            MAX_PAYLOAD_BYTES
    except (TypeError, ValueError):
        return True


def _subdevice_document(payload: Dict[str, Any],
                        subdevice_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not subdevice_id:
        return None
    for key in ("id", "subId"):
        if payload.get(key) == subdevice_id:
            return payload
    for key in ("id", "subId"):
        for value in payload.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and item.get(key) == subdevice_id:
                    return item
    return None
