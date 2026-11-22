"""Deterministic device-to-profile matching."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Optional, Tuple

from .models import ProfileMeta
from .registry import ProfileRegistry

_LOGGER = logging.getLogger(__name__)

_MAC_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")

# Highest tier first, as defined in docs/D2.2-PLAN.md.
_TIER_MAC_SUBTYPE = 5
_TIER_SUBTYPE = 4
_TIER_TYPE = 3
_TIER_PREFIX = 2
_TIER_GENERIC = 1


@dataclass(frozen=True)
class MatchContext:
    """Device facts used to resolve a profile."""

    type: str
    sub_type: Optional[str] = None
    mac: Optional[str] = None
    abilities: FrozenSet[str] = frozenset()
    is_hub: bool = False


@dataclass(frozen=True)
class MatchResult:
    profile: Optional[ProfileMeta]
    score: Tuple[int, int] = (0, 0)
    candidates: Tuple[str, ...] = ()
    ambiguous: bool = False


def normalize_type(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def normalize_mac(value: Any) -> Optional[str]:
    """Return upper-case hex without separators, or None when invalid."""
    if not isinstance(value, str):
        return None
    cleaned = _MAC_CLEAN_RE.sub("", value)
    if not cleaned or len(cleaned) % 2:
        return None
    return cleaned.upper()


def _declared_strings(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


def _abilities_match(match: Dict[str, Any],
                     abilities: FrozenSet[str]) -> bool:
    declared = match.get("abilities")
    if not isinstance(declared, dict):
        return True
    required = _declared_strings(declared.get("all"))
    if any(ability not in abilities for ability in required):
        return False
    optional = _declared_strings(declared.get("any"))
    if optional and not any(ability in abilities for ability in optional):
        return False
    return True


def _mac_matches(match: Dict[str, Any], mac: Optional[str]) -> bool:
    mac = normalize_mac(mac)
    prefixes = [
        prefix for prefix in (
            normalize_mac(item) for item in _declared_strings(
                match.get("mac_prefix")))
        if prefix
    ]
    if not prefixes:
        return False
    return bool(mac and any(mac.startswith(prefix) for prefix in prefixes))


def _score(profile: ProfileMeta, context: MatchContext) -> Optional[Tuple[int, int]]:
    data = profile.data
    match = data.get("match") if isinstance(data, dict) else None
    if not isinstance(match, dict):
        return None

    kind = match.get("kind", "device")
    if kind == "device" and context.is_hub:
        return None
    if kind == "hub" and not context.is_hub:
        return None
    if kind not in ("device", "hub", "any"):
        return None

    if not _abilities_match(match, context.abilities):
        return None

    context_mac = normalize_mac(context.mac)
    declared_macs = _declared_strings(match.get("mac_prefix"))
    if declared_macs:
        if not context_mac:
            return None
        if not _mac_matches(match, context_mac):
            return None

    context_type = normalize_type(context.type)
    types = [normalize_type(item)
             for item in _declared_strings(match.get("type"))]
    types = [item for item in types if item]

    declared_subs = [normalize_type(item)
                     for item in _declared_strings(match.get("sub_type"))]
    context_sub = normalize_type(context.sub_type)
    exact_sub_type = bool(context_sub and context_sub in declared_subs)
    if declared_subs and not exact_sub_type and "*" not in declared_subs:
        return None

    if context_type and context_type in types:
        if exact_sub_type:
            if _mac_matches(match, context.mac):
                return (_TIER_MAC_SUBTYPE, 0)
            return (_TIER_SUBTYPE, 0)
        return (_TIER_TYPE, 0)

    prefixes = [item for item in types
                if item != "*" and context_type.startswith(item)]
    if prefixes:
        return (_TIER_PREFIX, max(len(item) for item in prefixes))

    if "*" in types:
        return (_TIER_GENERIC, 0)

    return None


def match_profile(registry: ProfileRegistry,
                  context: MatchContext) -> MatchResult:
    return match_candidates(registry.profiles.values(), context)


def match_candidates(profiles: Iterable[ProfileMeta],
                     context: MatchContext) -> MatchResult:
    """Return the best candidate for context, deterministically.

    Equal scores are resolved by lexicographic profile id and reported as an
    ambiguity; the profile with the smallest id wins.
    """
    scored = []
    for profile in profiles:
        score = _score(profile, context)
        if score is not None:
            scored.append((score, profile))
    if not scored:
        return MatchResult(None)

    best_score = max(score for score, _ in scored)
    candidates = sorted(profile.id for score, profile in scored
                        if score == best_score)
    chosen_id = candidates[0]
    chosen = next(profile for score, profile in scored
                  if score == best_score and profile.id == chosen_id)
    ambiguous = len(candidates) > 1
    if ambiguous:
        _LOGGER.warning(
            "Ambiguous profile match for %s/%s (abilities %s): %s; "
            "using %s", context.type, context.sub_type or "*",
            sorted(context.abilities), ", ".join(candidates), chosen_id)
    return MatchResult(
        profile=chosen,
        score=best_score,
        candidates=tuple(candidates),
        ambiguous=ambiguous,
    )
