"""Signed HTTP access to the local broker API (D5 vendored path)."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import aiohttp

MEROSS_SECRET = "23x17ahWarFH6w29"
DEFAULT_TIMEOUT = 10.0
APP_VERSION = "2.4.6"
USER_AGENT = "MerossHA/meross-local-cloud"


@dataclass(frozen=True)
class BrokerCredentials:
    token: str
    key: str
    user_id: str
    user_email: str
    domain: str
    mqtt_domain: str
    issued_on: datetime

    @classmethod
    def from_login(cls, data: dict, endpoint: str) -> "BrokerCredentials":
        return cls(
            token=data["token"],
            key=data["key"],
            user_id=str(data["userid"]),
            user_email=data["email"],
            domain=endpoint,
            mqtt_domain=data.get("mqttDomain") or "",
            issued_on=datetime.now(timezone.utc),
        )

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "mqtt_domain": self.mqtt_domain,
            "token": self.token,
            "key": self.key,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "issued_on": self.issued_on.isoformat(),
        }


class BrokerHttpError(Exception):
    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class BrokerAuthError(BrokerHttpError):
    pass


class BrokerTokenError(BrokerHttpError):
    pass


def build_envelope(payload: dict,
                   timestamp: Optional[int] = None,
                   nonce: Optional[str] = None) -> dict:
    timestamp = timestamp if timestamp is not None else int(time.time() * 1000)
    nonce = nonce or secrets.token_hex(8)
    encoded = base64.b64encode(
        json.dumps(payload).encode("utf-8")).decode("ascii")
    signature = hashlib.md5(
        f"{MEROSS_SECRET}{timestamp}{nonce}{encoded}".encode()).hexdigest()
    return {
        "params": encoded,
        "timestamp": timestamp,
        "nonce": nonce,
        "sign": signature,
    }


class BrokerHttpClient:
    """POST signed envelopes to the broker, using the pinned broker CA."""

    def __init__(self, endpoint: str, token,
                 ssl_context: Optional[ssl.SSLContext] = None,
                 timeout: float = DEFAULT_TIMEOUT,
                 session_factory: Optional[Callable[[], Any]] = None) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._ssl_context = ssl_context
        self._timeout = timeout
        self._session_factory = session_factory or aiohttp.ClientSession

    def _headers(self) -> dict:
        token = self._token() if callable(self._token) else self._token
        headers = {
            "Content-Type": "application/json",
            "AppVersion": APP_VERSION,
            "User-Agent": USER_AGENT,
        }
        if token:
            headers["Authorization"] = f"Basic {token}"
        return headers

    @classmethod
    async def async_login(cls, endpoint: str, email: str, password: str,
                          mfa_code: Optional[str] = None,
                          ssl_context: Optional[ssl.SSLContext] = None,
                          session_factory: Optional[Callable[[], Any]] = None
                          ) -> BrokerCredentials:
        client = cls(endpoint, None, ssl_context,
                     session_factory=session_factory)
        payload = {
            "email": email,
            "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
            "encryption": 1,
            "agree": 1,
        }
        if mfa_code:
            payload["mfaCode"] = mfa_code
        data = await client.async_post("/v1/Auth/signIn", payload)
        if not isinstance(data, dict):
            raise BrokerHttpError("malformed login response")
        return BrokerCredentials.from_login(data, endpoint)

    async def async_post(self, path: str, payload: Optional[dict] = None
                         ) -> Any:
        url = f"{self._endpoint}{path}"
        envelope = build_envelope(payload or {})
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with self._session_factory() as session:
            async with session.post(
                    url, json=envelope, headers=self._headers(),
                    ssl=self._ssl_context, timeout=timeout) as response:
                if response.status != 200:
                    raise BrokerHttpError(
                        f"HTTP {response.status} on {path}",
                        status=response.status)
                body = await response.json()
        status = body.get("apiStatus") if isinstance(body, dict) else None
        if status == 0:
            return body.get("data")
        info = body.get("info") if isinstance(body, dict) else None
        if status == 1022:
            raise BrokerTokenError(info or "token_error", status)
        if status in (1002, 1004):
            raise BrokerAuthError(info or "authentication_failed", status)
        raise BrokerHttpError(info or f"apiStatus {status}", status)
