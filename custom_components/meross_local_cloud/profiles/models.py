"""Runtime models for compiled device profiles."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class ProfileMeta:
    """A profile entry as served by the broker catalog."""

    id: str
    version: Optional[str]
    source: str
    digest: Optional[str]
    requires_engine: Optional[str]
    data: Dict[str, Any]

    @classmethod
    def from_entry(cls, entry: Dict[str, Any]) -> "ProfileMeta":
        data = entry.get("profile") or {}
        profile = data.get("profile") or {}
        return cls(
            id=entry["id"],
            version=profile.get("version") or entry.get("version"),
            source=entry.get("source") or "bundled",
            digest=entry.get("hash"),
            requires_engine=(
                profile.get("requires_engine")
                or entry.get("requires_engine")),
            data=data,
        )


@dataclass(frozen=True)
class PollingSpec:
    """How a namespace is polled by the (future) central scheduler."""

    strategy: str = "default"
    period_s: float = 60
    push: bool = False
    response_size: Optional[int] = None


@dataclass(frozen=True)
class NamespaceSpec:
    """A validated payload namespace declaration."""

    namespace: str
    methods: Tuple[str, ...]
    fields: Dict[str, Any] = field(default_factory=dict)
    digest: Optional[str] = None
    polling: PollingSpec = field(default_factory=PollingSpec)


@dataclass(frozen=True)
class FieldSpec:
    """A state field path with optional scaling or value mapping."""

    path: str
    scale: Optional[float] = None
    offset: Optional[float] = None
    on_values: Optional[Tuple[Any, ...]] = None


@dataclass(frozen=True)
class StateSpec:
    """Where an entity reads its state from."""

    namespace: str
    channel: Optional[int] = None
    fields: Dict[str, FieldSpec] = field(default_factory=dict)
    digest: Optional[str] = None
    scale: Optional[float] = None
    select_path: Optional[str] = None
    select_key: Optional[str] = None


@dataclass(frozen=True)
class CommandSpec:
    """One entity command, payload still carrying $channel/$value."""

    namespace: str
    payload: Dict[str, Any] = field(default_factory=dict)
    value_scale: Optional[float] = None


@dataclass(frozen=True)
class EntitySpec:
    """A compiled entity, ready for D3 without HA registration."""

    uid: str
    key: str
    platform: str
    channel: Optional[int] = None
    name: Optional[str] = None
    device_class: Optional[str] = None
    entity_category: Optional[str] = None
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    device: str = "hub"
    channel_template: bool = False
    mode: Optional[str] = None
    state: Optional[StateSpec] = None
    movement: Optional[StateSpec] = None
    commands: Dict[str, CommandSpec] = field(default_factory=dict)
    quirks: Tuple[Dict[str, Any], ...] = ()
    capabilities: Optional[Dict[str, Any]] = None
    legacy_classifiers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SubDeviceTemplate:
    """A compiled hub subdevice template."""

    uid: str
    name: Optional[str]
    match: Dict[str, Any] = field(default_factory=dict)
    namespaces: Dict[str, NamespaceSpec] = field(default_factory=dict)
    entities: Dict[str, EntitySpec] = field(default_factory=dict)


@dataclass
class CompiledProfile:
    """Compilation result; entity errors are isolated."""

    profile_id: str
    version: Optional[str]
    schema_version: Optional[int]
    description: Optional[str] = None
    namespaces: Dict[str, NamespaceSpec] = field(default_factory=dict)
    entities: Dict[str, EntitySpec] = field(default_factory=dict)
    subdevices: Tuple[SubDeviceTemplate, ...] = ()
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
