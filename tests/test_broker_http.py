import hashlib

import pytest

from custom_components.meross_cloud.broker_http import (
    MEROSS_SECRET,
    BrokerAuthError,
    BrokerHttpClient,
    BrokerHttpError,
    BrokerTokenError,
    build_envelope,
)


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._body


class FakeSession:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.status, self.body)


def client(status=200, body=None):
    session = FakeSession(status, body or {})
    http = BrokerHttpClient(
        "https://broker:2004/", "token",
        session_factory=lambda: session)
    return http, session


def test_envelope_signature():
    envelope = build_envelope(
        {"a": 1}, timestamp=1788750000, nonce="nonce")

    expected = hashlib.md5(
        f"{MEROSS_SECRET}1788750000nonce{envelope['params']}".encode()
    ).hexdigest()
    assert envelope["sign"] == expected
    assert envelope["timestamp"] == 1788750000
    assert envelope["nonce"] == "nonce"


async def test_post_returns_data_and_signs():
    http, session = client(body={"apiStatus": 0, "data": {"revision": "r"}})

    result = await http.async_post("/v1/Device/profiles/rev")

    assert result == {"revision": "r"}
    url, kwargs = session.calls[0]
    assert url == "https://broker:2004/v1/Device/profiles/rev"
    assert kwargs["headers"]["Authorization"] == "Basic token"
    envelope = kwargs["json"]
    expected = hashlib.md5(
        f"{MEROSS_SECRET}{envelope['timestamp']}{envelope['nonce']}"
        f"{envelope['params']}".encode()).hexdigest()
    assert envelope["sign"] == expected


@pytest.mark.parametrize("status,error", [
    (1022, BrokerTokenError),
    (1002, BrokerAuthError),
    (5000, BrokerHttpError),
])
async def test_api_status_errors(status, error):
    http, _ = client(body={"apiStatus": status, "info": "nope"})

    with pytest.raises(error):
        await http.async_post("/path")


async def test_http_error():
    http, _ = client(status=502, body={})

    with pytest.raises(BrokerHttpError):
        await http.async_post("/path")
