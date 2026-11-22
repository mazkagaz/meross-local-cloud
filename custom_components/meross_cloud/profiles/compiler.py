"""Compile validated profile documents into runtime specs."""
from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import (
    CommandSpec,
    CompiledProfile,
    EntitySpec,
    FieldSpec,
    NamespaceSpec,
    PollingSpec,
    ProfileMeta,
    StateSpec,
    SubDeviceTemplate,
)
from .paths import InvalidPath, find_tokens, parse_path, validate_tokens

_LOGGER = logging.getLogger(__name__)

SIMPLE_PLATFORMS = frozenset({
    "cover", "switch", "light", "sensor", "binary_sensor", "number",
    "button", "select",
})
COMPLEX_PLATFORMS = frozenset({
    "climate", "fan", "humidifier", "calendar", "media_player", "siren",
    "update",
})
KNOWN_METHODS = frozenset({
    "GET", "SET", "GETACK", "SETACK", "PUSH", "ERROR",
})
POLLING_STRATEGIES = frozenset({"default", "smart", "once", "chunked"})
KNOWN_QUIRKS = frozenset({
    "roller_shutter_config_replay",
    "config_persist",
    "adjust_start",
    "adjust_stop",
    "adjust_status_names",
    "garage_door",
})
_REQUIRED_VALUE_COMMANDS = {
    "number": frozenset({"set_value"}),
    "select": frozenset({"set_option"}),
    "light": frozenset({"set_brightness", "set_rgb"}),
    "climate": frozenset({"set_temperature"}),
    "fan": frozenset({"set_speed"}),
}
_KEY_RE = re.compile(r"^[a-z0-9_]+$")
_DEFAULT_PERIOD_S = 60.0


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool))


def compile_profile(profile: ProfileMeta) -> CompiledProfile:
    """Compile one profile; entity errors stay isolated."""
    data = profile.data if isinstance(profile.data, dict) else {}
    profile_doc = data.get("profile")
    description = (profile_doc.get("description")
                   if isinstance(profile_doc, dict) else None)
    compiled = CompiledProfile(
        profile_id=profile.id,
        version=profile.version,
        schema_version=data.get("schema_version"),
        description=description if isinstance(description, str) else None,
    )
    compiled.namespaces = _compile_namespaces(profile.id, data, compiled)
    _check_root_quirks(profile.id, data, compiled)
    compiled.entities = _compile_entities(
        profile.id, data, compiled.namespaces, compiled,
        uid_prefix=profile.id,
        default_device="hub",
        allow_subdevice=False,
    )
    compiled.subdevices = _compile_subdevices(profile.id, data, compiled)
    return compiled


def expand_channel_entities(compiled: CompiledProfile,
                            channels: Iterable[int]) -> CompiledProfile:
    """Clone ``$channels`` entity templates for every device channel."""
    templated = [entity for entity in compiled.entities.values()
                 if entity.channel_template]
    if not templated:
        return compiled
    indexes = tuple(sorted({
        channel for channel in channels
        if _is_int(channel) and channel >= 0})) or (0,)
    entities = {key: entity for key, entity in compiled.entities.items()
                if not entity.channel_template}
    for entity in templated:
        for channel in indexes:
            state = entity.state
            if state is not None and state.channel is None:
                state = replace(state, channel=channel)
            clone = replace(
                entity,
                uid=f"{entity.uid}:{channel}",
                key=f"{entity.key}_{channel}",
                channel=channel,
                channel_template=False,
                name=_channel_name(entity.name, channel),
                state=state,
            )
            entities[clone.key] = clone
    return replace(compiled, entities=entities)


def _channel_name(name: Optional[str], channel: int) -> Optional[str]:
    if name is None:
        return None
    return (name.replace("$channel_number", str(channel + 1))
            .replace("$channel", str(channel)))


class ProfileCompiler:
    """Lazy compilation cache keyed by (id, version, hash)."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, Optional[str], Optional[str]],
                          CompiledProfile] = {}

    def compile(self, profile: ProfileMeta) -> CompiledProfile:
        key = (profile.id, profile.version, profile.digest)
        compiled = self._cache.get(key)
        if compiled is None:
            compiled = compile_profile(profile)
            self._cache[key] = compiled
        return compiled

    @property
    def cache_size(self) -> int:
        return len(self._cache)


def _compile_namespaces(profile_id: str, data: Dict[str, Any],
                        compiled: CompiledProfile
                        ) -> Dict[str, NamespaceSpec]:
    raw_namespaces = data.get("payloads")
    if raw_namespaces is None:
        return {}
    if not isinstance(raw_namespaces, dict):
        compiled.errors.append(
            f"{profile_id}: payloads must be an object")
        return {}

    namespaces = {}
    for name, raw in raw_namespaces.items():
        prefix = f"{profile_id}: namespace {name}"
        if not isinstance(name, str) or not isinstance(raw, dict):
            compiled.errors.append(f"{prefix}: malformed declaration")
            continue
        methods = _compile_methods(prefix, raw, compiled)
        if methods is None:
            continue
        fields = raw.get("fields")
        if fields is None:
            fields = {}
        elif not isinstance(fields, dict):
            compiled.errors.append(f"{prefix}: fields must be an object")
            fields = {}
        digest = raw.get("digest")
        if digest is not None:
            if not isinstance(digest, str):
                compiled.errors.append(f"{prefix}: digest must be a path")
                digest = None
            else:
                try:
                    parse_path(digest)
                except InvalidPath as err:
                    compiled.errors.append(f"{prefix}: invalid digest: {err}")
                    digest = None
        polling = _compile_polling(prefix, raw.get("polling"), methods,
                                   compiled)
        namespaces[name] = NamespaceSpec(
            namespace=name,
            methods=methods,
            fields=dict(fields),
            digest=digest,
            polling=polling,
        )
    return namespaces


def _compile_methods(prefix: str, raw: Dict[str, Any],
                     compiled: CompiledProfile) -> Optional[Tuple[str, ...]]:
    methods = raw.get("methods")
    if (not isinstance(methods, (list, tuple)) or not methods
            or not all(isinstance(item, str) for item in methods)):
        compiled.errors.append(
            f"{prefix}: methods must be a non-empty list of strings")
        return None
    known = []
    for method in methods:
        if method in KNOWN_METHODS:
            known.append(method)
        else:
            compiled.warnings.append(
                f"{prefix}: unknown method {method!r} ignored")
    return tuple(known)


def _compile_polling(prefix: str, raw: Any, methods: Tuple[str, ...],
                     compiled: CompiledProfile) -> PollingSpec:
    declared = raw if isinstance(raw, dict) else {}
    if raw is not None and not isinstance(raw, dict):
        compiled.errors.append(f"{prefix}: polling must be an object")

    strategy = declared.get("strategy")
    if strategy is None:
        strategy = ("once" if "SET" in methods
                    and not set(methods) & {"GET", "GETACK", "PUSH"}
                    else "default")
    elif strategy not in POLLING_STRATEGIES:
        compiled.warnings.append(f"{prefix}: unknown polling strategy "
                                 f"{strategy!r} ignored, using default")
        strategy = "default"

    period_s = declared.get("period_s", _DEFAULT_PERIOD_S)
    if not _is_number(period_s) or period_s < 0:
        compiled.errors.append(f"{prefix}: invalid polling period_s")
        period_s = _DEFAULT_PERIOD_S

    push = declared.get("push", "PUSH" in methods)
    if not isinstance(push, bool):
        compiled.errors.append(f"{prefix}: polling push must be a boolean")
        push = "PUSH" in methods

    response_size = declared.get("response_size")
    if response_size is not None and (
            not _is_int(response_size) or response_size < 0):
        compiled.errors.append(f"{prefix}: invalid polling response_size")
        response_size = None

    return PollingSpec(
        strategy=strategy,
        period_s=float(period_s),
        push=push,
        response_size=response_size,
    )


def _check_root_quirks(profile_id: str, data: Dict[str, Any],
                       compiled: CompiledProfile) -> None:
    raw = data.get("quirks")
    if raw is None:
        return
    if not isinstance(raw, (list, tuple)):
        compiled.errors.append(f"{profile_id}: quirks must be a list")
        return
    seen = set()
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or name not in KNOWN_QUIRKS:
            compiled.errors.append(
                f"{profile_id}: unknown root quirk {name!r}")
            continue
        if name in seen:
            compiled.errors.append(
                f"{profile_id}: duplicate root quirk {name!r}")
        seen.add(name)


def _compile_entities(context_id: str, data: Dict[str, Any],
                      namespaces: Dict[str, NamespaceSpec],
                      compiled: CompiledProfile, *, uid_prefix: str,
                      default_device: str,
                      allow_subdevice: bool) -> Dict[str, EntitySpec]:
    raw_entities = data.get("entities")
    if raw_entities is None:
        return {}
    if not isinstance(raw_entities, (list, tuple)):
        compiled.errors.append(f"{context_id}: entities must be a list")
        return {}

    entities = {}
    seen_keys = set()
    for raw in raw_entities:
        if not isinstance(raw, dict):
            compiled.errors.append(
                f"{context_id}: malformed entity {raw!r}")
            continue
        key = raw.get("key")
        label = key if isinstance(key, str) else "?"
        if isinstance(key, str) and key in seen_keys:
            compiled.errors.append(
                f"{context_id}: entity {label}: duplicate entity key")
            continue
        if isinstance(key, str):
            seen_keys.add(key)

        platform = raw.get("platform")
        if platform not in SIMPLE_PLATFORMS | COMPLEX_PLATFORMS:
            compiled.warnings.append(
                f"{context_id}: entity {label}: unknown platform "
                f"{platform!r} ignored")
            continue

        errors: List[str] = []
        entity = _compile_entity(
            context_id, raw, namespaces, errors,
            uid_prefix=uid_prefix,
            default_device=default_device,
            allow_subdevice=allow_subdevice,
        )
        if errors:
            compiled.errors.extend(errors)
            continue
        entities[entity.key] = entity
    return entities


def _compile_entity(context_id: str, raw: Dict[str, Any],
                    namespaces: Dict[str, NamespaceSpec],
                    errors: List[str], *, uid_prefix: str,
                    default_device: str,
                    allow_subdevice: bool) -> EntitySpec:
    key = raw.get("key")
    label = key if isinstance(key, str) else "?"
    prefix = f"{context_id}: entity {label}"

    if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
        errors.append(f"{prefix}: invalid entity key")

    platform = raw["platform"]
    channel = raw.get("channel")
    channel_template = channel == "$channels"
    if channel_template:
        channel = None
        if default_device == "subdevice":
            errors.append(
                f"{prefix}: $channels is not supported in subdevice "
                "templates")
            channel_template = False
    elif channel is not None:
        if not _is_int(channel) or channel < 0:
            errors.append(
                f"{prefix}: channel must be a non-negative integer or "
                "$channels")
            channel = None

    device = raw.get("device", default_device)
    if device not in ("hub", "subdevice"):
        errors.append(f"{prefix}: invalid device {device!r}")
    elif device == "subdevice" and not allow_subdevice:
        errors.append(
            f"{prefix}: subdevice entities require a hub template")
    elif device == "hub" and default_device == "subdevice":
        errors.append(
            f"{prefix}: template entities must use device: subdevice")

    name = _optional_string(prefix, raw, "name", errors)
    device_class = _optional_string(prefix, raw, "device_class", errors)
    entity_category = _optional_string(
        prefix, raw, "entity_category", errors)
    unit = _optional_string(prefix, raw, "unit", errors)
    min_value = _optional_number(prefix, raw, "min_value", errors)
    max_value = _optional_number(prefix, raw, "max_value", errors)
    step = _optional_number(prefix, raw, "step", errors)

    state = _compile_state(prefix, raw.get("state"), namespaces, channel,
                           errors, channel_template=channel_template)
    movement = _compile_state(
        f"{prefix}:movement", raw.get("movement"), namespaces, channel,
        errors, channel_template=channel_template)
    commands = _compile_commands(
        prefix, platform, raw.get("commands"), namespaces, channel, errors,
        allow_subdevice=allow_subdevice, channel_template=channel_template)
    quirks = _compile_entity_quirks(prefix, raw.get("quirks"), errors)
    legacy_classifiers = raw.get("legacy_classifiers", [])
    if not isinstance(legacy_classifiers, (list, tuple)) or not all(
            isinstance(item, str) for item in legacy_classifiers):
        errors.append(
            f"{prefix}: legacy_classifiers must be a list of strings")
        legacy_classifiers = ()
    capabilities = raw.get("capabilities")
    if capabilities is not None and not isinstance(capabilities, dict):
        errors.append(f"{prefix}: capabilities must be an object")
        capabilities = None
    elif capabilities is None and platform in ("climate", "fan"):
        errors.append(f"{prefix}: {platform} requires capabilities")

    return EntitySpec(
        uid=f"{uid_prefix}:{label}",
        key=label,
        platform=platform,
        channel=channel,
        name=name,
        device_class=device_class,
        entity_category=entity_category,
        unit=unit,
        min_value=min_value,
        max_value=max_value,
        step=step,
        device=device,
        channel_template=channel_template,
        state=state,
        movement=movement,
        commands=commands,
        quirks=quirks,
        capabilities=capabilities,
        legacy_classifiers=tuple(legacy_classifiers),
    )


def _compile_subdevices(profile_id: str, data: Dict[str, Any],
                        compiled: CompiledProfile
                        ) -> Tuple[SubDeviceTemplate, ...]:
    raw_subdevices = data.get("subdevices")
    if raw_subdevices is None:
        return ()
    if not isinstance(raw_subdevices, (list, tuple)):
        compiled.errors.append(f"{profile_id}: subdevices must be a list")
        return ()

    templates = []
    for index, raw in enumerate(raw_subdevices):
        uid = f"{profile_id}:subdevice:{index}"
        if not isinstance(raw, dict):
            compiled.errors.append(f"{uid}: malformed template")
            continue
        match = raw.get("match")
        types = match.get("type") if isinstance(match, dict) else None
        if (not isinstance(match, dict)
                or not isinstance(types, (list, tuple)) or not types
                or not all(isinstance(item, str) for item in types)):
            compiled.errors.append(
                f"{uid}: match.type must be a non-empty list of strings")
            continue
        name = raw.get("name")
        if name is not None and not isinstance(name, str):
            compiled.errors.append(f"{uid}: name must be a string")
            name = None
        namespaces = _compile_namespaces(uid, raw, compiled)
        _check_root_quirks(uid, raw, compiled)
        entities = _compile_entities(
            uid, raw, namespaces, compiled,
            uid_prefix=uid,
            default_device="subdevice",
            allow_subdevice=True,
        )
        templates.append(SubDeviceTemplate(
            uid=uid,
            name=name,
            match=dict(match),
            namespaces=namespaces,
            entities=entities,
        ))
    return tuple(templates)


def _optional_number(prefix: str, raw: Dict[str, Any], key: str,
                     errors: List[str]) -> Optional[float]:
    value = raw.get(key)
    if value is not None and not _is_number(value):
        errors.append(f"{prefix}: {key} must be a number")
        return None
    return float(value) if value is not None else None


def _optional_string(prefix: str, raw: Dict[str, Any], key: str,
                     errors: List[str]) -> Optional[str]:
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        errors.append(f"{prefix}: {key} must be a string")
        return None
    return value


def _compile_state(prefix: str, raw: Any,
                   namespaces: Dict[str, NamespaceSpec],
                   entity_channel: Optional[int],
                   errors: List[str], *,
                   channel_template: bool = False) -> Optional[StateSpec]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"{prefix}: state must be an object")
        return None

    namespace = raw.get("namespace")
    if not isinstance(namespace, str) or namespace not in namespaces:
        errors.append(f"{prefix}: unknown state namespace {namespace!r}")

    fields_raw = raw.get("fields")
    fields: Dict[str, FieldSpec] = {}
    if not isinstance(fields_raw, dict) or not fields_raw:
        errors.append(f"{prefix}: state.fields must be a non-empty object")
    else:
        for prop, raw_field in fields_raw.items():
            path = raw_field
            scale = offset = on_values = None
            if isinstance(raw_field, dict):
                path = raw_field.get("path")
                scale = raw_field.get("scale")
                offset = raw_field.get("offset")
                on_values = raw_field.get("on_values")
                if scale is not None and not _is_number(scale):
                    errors.append(
                        f"{prefix}: invalid scale for {prop!r}")
                    scale = None
                if offset is not None and not _is_number(offset):
                    errors.append(
                        f"{prefix}: invalid offset for {prop!r}")
                    offset = None
                if on_values is not None:
                    if (not isinstance(on_values, (list, tuple))
                            or not on_values
                            or not all(isinstance(item, (int, float, str))
                                       and not isinstance(item, bool)
                                       for item in on_values)):
                        errors.append(
                            f"{prefix}: invalid on_values for {prop!r}")
                        on_values = None
            if not isinstance(prop, str) or not isinstance(path, str) \
                    or not path:
                errors.append(
                    f"{prefix}: invalid state path for {prop!r}")
                continue
            try:
                parse_path(path)
            except InvalidPath as err:
                errors.append(f"{prefix}: invalid state path {path!r}: {err}")
                continue
            fields[prop] = FieldSpec(
                path=path,
                scale=float(scale) if scale is not None else None,
                offset=float(offset) if offset is not None else None,
                on_values=(tuple(on_values)
                           if on_values is not None else None))

    state_channel = raw.get("channel")
    channel: Optional[int] = None
    if state_channel is not None:
        if state_channel == "$channel":
            if entity_channel is None and not channel_template:
                errors.append(
                    f"{prefix}: $channel used without an entity channel")
            channel = entity_channel
        elif _is_int(state_channel) and state_channel >= 0:
            channel = state_channel
            if channel_template:
                errors.append(
                    f"{prefix}: a $channels entity must read state from "
                    "$channel")
        else:
            errors.append(
                f"{prefix}: state channel must be a non-negative integer "
                "or $channel")

    digest = raw.get("digest")
    if digest is not None:
        if not isinstance(digest, str):
            errors.append(f"{prefix}: state.digest must be a path")
            digest = None
        else:
            try:
                parse_path(digest)
            except InvalidPath as err:
                errors.append(f"{prefix}: invalid state digest: {err}")
                digest = None

    scale = raw.get("scale")
    if scale is not None and not _is_number(scale):
        errors.append(f"{prefix}: state.scale must be a number")
        scale = None

    select_path = select_key = None
    select = raw.get("select")
    if select is not None:
        if not isinstance(select, dict):
            errors.append(f"{prefix}: state.select must be an object")
        else:
            path = select.get("path")
            key = select.get("key")
            if not isinstance(path, str) or not path:
                errors.append(f"{prefix}: state.select.path must be a path")
            else:
                try:
                    parse_path(path)
                    select_path = path
                except InvalidPath as err:
                    errors.append(
                        f"{prefix}: invalid state.select.path {path!r}: {err}")
            if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
                errors.append(
                    f"{prefix}: state.select.key must be a lowercase key")
            else:
                select_key = key
        if entity_channel is None and not channel_template:
            errors.append(
                f"{prefix}: state.select requires an entity channel")

    return StateSpec(
        namespace=namespace,
        channel=channel,
        fields=fields,
        digest=digest,
        scale=float(scale) if scale is not None else None,
        select_path=select_path,
        select_key=select_key,
    )


def _compile_commands(prefix: str, platform: str, raw: Any,
                      namespaces: Dict[str, NamespaceSpec],
                      entity_channel: Optional[int],
                      errors: List[str], *,
                      allow_subdevice: bool,
                      channel_template: bool = False
                      ) -> Dict[str, CommandSpec]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{prefix}: commands must be an object")
        return {}

    commands = {}
    for name, command in raw.items():
        if not isinstance(name, str) or not isinstance(command, dict):
            errors.append(f"{prefix}: malformed command {name!r}")
            continue
        namespace = command.get("namespace")
        if not isinstance(namespace, str) or namespace not in namespaces:
            errors.append(
                f"{prefix}: command {name}: unknown namespace {namespace!r}")
            continue
        payload = command.get("payload")
        if not isinstance(payload, dict):
            errors.append(
                f"{prefix}: command {name}: payload must be an object")
            continue
        invalid_tokens = validate_tokens(payload)
        if invalid_tokens:
            errors.append(
                f"{prefix}: command {name}: unsupported token(s) "
                f"{', '.join(sorted(set(invalid_tokens)))}")
            continue
        tokens = set(find_tokens(payload))
        if ("$channel" in tokens and entity_channel is None
                and not channel_template):
            errors.append(
                f"{prefix}: command {name}: $channel used without an "
                "entity channel")
        if "$id" in tokens and not allow_subdevice:
            errors.append(
                f"{prefix}: command {name}: $id is only valid in a "
                "subdevice template")
        if (name in _REQUIRED_VALUE_COMMANDS.get(platform, ())
                and "$value" not in tokens):
            errors.append(
                f"{prefix}: command {name}: $value is required")
        value_scale = command.get("value_scale")
        if value_scale is not None and not _is_number(value_scale):
            errors.append(
                f"{prefix}: command {name}: value_scale must be a number")
            value_scale = None
        commands[name] = CommandSpec(
            namespace=namespace,
            payload=dict(payload),
            value_scale=float(value_scale)
            if value_scale is not None else None,
        )
    return commands


def _compile_entity_quirks(prefix: str, raw: Any,
                           errors: List[str]) -> Tuple[Dict[str, Any], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        errors.append(f"{prefix}: quirks must be a list")
        return ()
    quirks = []
    seen = set()
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or name not in KNOWN_QUIRKS:
            errors.append(f"{prefix}: unknown quirk {name!r}")
            continue
        if name in seen:
            errors.append(f"{prefix}: duplicate quirk {name!r}")
            continue
        seen.add(name)
        params = item.get("params")
        if params is not None and not isinstance(params, dict):
            errors.append(f"{prefix}: quirk {name}: params must be an object")
            continue
        quirks.append(dict(item))
    return tuple(quirks)
