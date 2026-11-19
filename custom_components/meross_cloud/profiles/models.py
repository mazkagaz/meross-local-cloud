"""Runtime models for compiled device profiles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


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
