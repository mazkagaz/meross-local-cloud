"""Typed paths and token substitution for device profiles.

Paths are a tiny, non-evaluated grammar: dot-separated keys in
``[A-Za-z0-9_]+`` with at most one non-negative index per segment
(``togglex[0].onoff``). Nothing is ever evaluated or used to build a dynamic
expression.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple, Union

MISSING = object()

MAX_DEPTH = 16
MAX_KEY_LENGTH = 64
RESERVED_KEYS = frozenset({"__proto__", "constructor", "prototype"})
ALLOWED_TOKENS = ("$channel", "$value")

_SEGMENT_RE = re.compile(r"([A-Za-z0-9_]+)(?:\[([0-9]+)\])?")


class InvalidPath(ValueError):
    """Raised by parse_path for a path outside the accepted grammar."""


class UnknownToken(ValueError):
    """Raised when a payload string is not a supported ``$`` token."""


@dataclass(frozen=True)
class PathToken:
    key: str
    index: Optional[int] = None


PathLike = Union[str, Sequence[PathToken]]


def parse_path(path: str) -> Tuple[PathToken, ...]:
    """Parse a profile path, raising InvalidPath when it is not allowed."""
    if not isinstance(path, str) or not path:
        raise InvalidPath("path must be a non-empty string")
    segments = path.split(".")
    if len(segments) > MAX_DEPTH:
        raise InvalidPath(f"path is deeper than {MAX_DEPTH} segments")
    tokens = []
    for segment in segments:
        match = _SEGMENT_RE.fullmatch(segment)
        if match is None:
            raise InvalidPath(f"invalid path segment {segment!r}")
        key = match.group(1)
        if len(key) > MAX_KEY_LENGTH:
            raise InvalidPath(f"path key {key!r} is too long")
        if key in RESERVED_KEYS:
            raise InvalidPath(f"reserved path key {key!r}")
        index = int(match.group(2)) if match.group(2) is not None else None
        tokens.append(PathToken(key, index))
    return tuple(tokens)


def get_path(document: Any, path: PathLike) -> Any:
    """Return the value at path, or MISSING. Never raises."""
    try:
        tokens = parse_path(path) if isinstance(path, str) else tuple(path)
        current = document
        for token in tokens:
            if not isinstance(current, Mapping):
                return MISSING
            if token.key not in current:
                return MISSING
            current = current[token.key]
            if token.index is not None:
                if not isinstance(current, (list, tuple)):
                    return MISSING
                if token.index >= len(current):
                    return MISSING
                current = current[token.index]
        return current
    except (InvalidPath, TypeError, AttributeError, ValueError):
        return MISSING


def find_tokens(value: Any) -> Tuple[str, ...]:
    """Collect every whole string that starts with ``$``."""
    tokens = []
    if isinstance(value, str):
        if value.startswith("$"):
            tokens.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            tokens.extend(find_tokens(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            tokens.extend(find_tokens(item))
    return tuple(tokens)


def validate_tokens(value: Any, allowed: Iterable[str] = ALLOWED_TOKENS
                    ) -> Tuple[str, ...]:
    """Return the tokens in value that are not exactly ``allowed``."""
    allowed_set = frozenset(allowed)
    return tuple(token for token in find_tokens(value)
                 if token not in allowed_set)


def substitute(value: Any, values: Mapping[str, Any]) -> Any:
    """Replace ``$channel``/``$value`` whole strings, recursively.

    Only whole strings are replaced: ``$channel_x`` is rejected instead of
    being partially expanded. Unknown tokens raise UnknownToken.
    """
    if isinstance(value, str):
        if not value.startswith("$"):
            return value
        if value not in ALLOWED_TOKENS:
            raise UnknownToken(f"unsupported token {value!r}")
        name = value[1:]
        if name not in values:
            raise UnknownToken(f"no value for token {value!r}")
        return values[name]
    if isinstance(value, Mapping):
        return {key: substitute(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, values) for item in value]
    return value
