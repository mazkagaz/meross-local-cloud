"""Load and index the profile catalog served by the broker."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from packaging.version import InvalidVersion, Version

from .constants import ENGINE_VERSION
from .models import ProfileMeta

_LOGGER = logging.getLogger(__name__)
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
_REQUIREMENT_RE = re.compile(r"^\s*(>=|<=|==|>|<)?\s*([0-9][0-9A-Za-z.\-]*)\s*$")


@dataclass
class SkippedProfile:
    id: str
    reason: str


@dataclass
class ProfileRegistry:
    """Validated catalog entries indexed by profile id."""

    revision: Optional[str] = None
    schema_version: Optional[int] = None
    profiles: Dict[str, ProfileMeta] = field(default_factory=dict)
    skipped: List[SkippedProfile] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @classmethod
    def from_catalog(cls, payload: Optional[Dict[str, Any]]) -> "ProfileRegistry":
        payload = payload or {}
        registry = cls(
            revision=payload.get("revision"),
            schema_version=payload.get("schema_version"),
            errors=[str(error) for error in payload.get("errors") or []],
        )

        if registry.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            registry.errors.append(
                f"unsupported schema_version {registry.schema_version!r}")
            return registry

        for entry in payload.get("profiles") or []:
            profile_id = entry.get("id") if isinstance(entry, dict) else None
            data = entry.get("profile") if isinstance(entry, dict) else None
            if not isinstance(profile_id, str) or not isinstance(data, dict):
                registry.errors.append(f"malformed profile entry: {entry!r}")
                continue
            if profile_id in registry.profiles:
                registry.skipped.append(
                    SkippedProfile(profile_id, "duplicate profile id"))
                continue
            requires = ((data.get("profile") or {}).get("requires_engine")
                        or entry.get("requires_engine"))
            if requires and not engine_satisfies(str(requires)):
                registry.skipped.append(
                    SkippedProfile(
                        profile_id,
                        f"requires engine {requires} (running "
                        f"{ENGINE_VERSION})"))
                continue
            registry.profiles[profile_id] = ProfileMeta.from_entry(entry)

        return registry

    def summary(self) -> Dict[str, Any]:
        return {
            "engine_version": ENGINE_VERSION,
            "schema_version": self.schema_version,
            "revision": self.revision,
            "profiles_loaded": len(self.profiles),
            "profiles_skipped": len(self.skipped),
            "registry_errors": list(self.errors),
            "skipped_profiles": [
                {"id": item.id, "reason": item.reason}
                for item in self.skipped
            ],
        }


def engine_satisfies(requirement: str) -> bool:
    """Evaluate a simple version requirement against ENGINE_VERSION."""
    match = _REQUIREMENT_RE.fullmatch(requirement)
    if match is None:
        _LOGGER.warning("Invalid requires_engine %r", requirement)
        return False
    operator = match.group(1) or ">="
    try:
        required = Version(match.group(2))
        current = Version(ENGINE_VERSION)
    except InvalidVersion:
        _LOGGER.warning("Invalid requires_engine %r", requirement)
        return False
    if operator == ">=":
        return current >= required
    if operator == "<=":
        return current <= required
    if operator == ">":
        return current > required
    if operator == "<":
        return current < required
    return current == required
