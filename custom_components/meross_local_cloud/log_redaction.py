"""Redact sensitive values from integration log records.

Pseudonyms are stable within an installation (derived from the config entry
id) but not reversible, so logs can be pasted into an issue without manual
masking.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re

_UUID_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_APP_TOPIC_RE = re.compile(r"(/app/\d+)-([A-Za-z0-9]+)(/subscribe)")
_JSON_SECRET_RE = re.compile(
    r'(?i)("(?:sign|key|token|mqttkey|password)"\s*:\s*)"[^"]*"')
_BASIC_RE = re.compile(r"(?i)(Basic\s+)[A-Za-z0-9_\-]+")
_SAFE_IPS = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}


class Redactor:
    def __init__(self, secret: bytes):
        self._secret = secret

    def _alias(self, prefix: str, value: str) -> str:
        digest = hmac.new(
            self._secret, value.encode("utf8"), hashlib.sha256).hexdigest()
        return f"{prefix}-{digest[:8]}"

    def _redact_ip(self, match: re.Match) -> str:
        value = match.group(0)
        return value if value in _SAFE_IPS else self._alias("ip", value)

    def redact(self, text: str) -> str:
        if not text:
            return text
        text = _JSON_SECRET_RE.sub(r'\1"***"', text)
        text = _BASIC_RE.sub(r"\1***", text)
        text = _APP_TOPIC_RE.sub(
            lambda m: f"{m.group(1)}-{self._alias('app', m.group(2))}"
                      f"{m.group(3)}", text)
        text = _MAC_RE.sub(lambda m: self._alias("mac", m.group(0)), text)
        text = _IPV4_RE.sub(self._redact_ip, text)
        text = _EMAIL_RE.sub(lambda m: self._alias("user", m.group(0)), text)
        text = _UUID_RE.sub(lambda m: self._alias("uuid", m.group(0)), text)
        return text


def _redact_args(redactor: Redactor, value):
    if isinstance(value, str):
        return redactor.redact(value)
    if isinstance(value, tuple):
        return tuple(_redact_args(redactor, item) for item in value)
    if isinstance(value, dict):
        return {key: _redact_args(redactor, item)
                for key, item in value.items()}
    return value


class RedactionFilter(logging.Filter):
    def __init__(self, redactor: Redactor,
                 only_prefix: str = "custom_components.meross_local_cloud"):
        super().__init__()
        self._redactor = redactor
        self._only_prefix = only_prefix

    def filter(self, record: logging.LogRecord) -> bool:
        if self._only_prefix and not record.name.startswith(self._only_prefix):
            return True
        if isinstance(record.msg, str):
            record.msg = self._redactor.redact(record.msg)
        if record.args:
            record.args = _redact_args(self._redactor, record.args)
        return True


def install(entry_id: str) -> None:
    logger = logging.getLogger("custom_components.meross_local_cloud")
    if any(isinstance(item, RedactionFilter) for item in logger.filters):
        return
    redactor = Redactor(entry_id.encode("utf8"))
    logger.addFilter(RedactionFilter(redactor, only_prefix=""))
    # Records propagate to the root handlers, where logger-level filters are
    # not applied; install there too, scoped to this integration.
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactionFilter(redactor))
