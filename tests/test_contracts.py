"""N1 — broker API contracts consumed by the integration."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jsonschema
import pytest

from custom_components.meross_local_cloud.broker_config import (
    RollerShutterConfigCache,
)
from custom_components.meross_local_cloud.broker_devices import (
    DEVICE_LIST_PATH,
    async_list_devices,
    parse_devices,
)
from custom_components.meross_local_cloud.broker_http import BrokerCredentials
from custom_components.meross_local_cloud.broker_profiles import (
    async_fetch_catalog,
    async_fetch_public_key,
    async_fetch_revision,
)
from custom_components.meross_local_cloud.profiles import ProfileRegistry

CONTRACTS = Path(__file__).parent / "contracts"
FIXTURES = CONTRACTS / "fixtures"
BROKER_CONTRACTS = Path(
    os.environ.get("MEROSS_BROKER_REPO")
    or Path(__file__).resolve().parents[2] / "meross-local-broker"
) / "meross_local_broker/rootfs/opt/custom_broker/contracts"

FILES = [
    "README.md",
    "signin.json", "devlist.json", "profiles_rev.json", "profiles.json",
    "pubkey.json", "roller_shutter_config.json",
    "fixtures/signin.json", "fixtures/devlist.json",
    "fixtures/profiles_rev.json", "fixtures/profiles.json",
    "fixtures/pubkey.json", "fixtures/roller_shutter_config.json",
]


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative", FILES)
def test_contract_copies_match_the_broker(relative):
    broker_file = BROKER_CONTRACTS / relative
    if not broker_file.exists():
        pytest.skip("broker contracts are not checked out next to the repo")
    assert (CONTRACTS / relative).read_bytes() == broker_file.read_bytes()


@pytest.mark.parametrize("name", [
    "signin", "devlist", "profiles_rev", "profiles", "pubkey",
    "roller_shutter_config",
])
def test_fixtures_validate_against_the_schemas(name):
    schema = json.loads((CONTRACTS / f"{name}.json").read_text(
        encoding="utf-8"))
    jsonschema.validate(fixture(f"{name}.json"), schema)


def test_signin_fixture_builds_local_credentials():
    creds = BrokerCredentials.from_login(
        fixture("signin.json"), "https://broker:2004")

    assert creds.token == "token-1"
    assert creds.key == "mqtt-key"
    assert creds.user_id == "1"
    assert creds.user_email == "user@example.com"
    assert creds.domain == "https://broker:2004"


def test_devlist_fixture_is_parsed():
    devices = parse_devices(fixture("devlist.json"))

    assert len(devices) == 1
    assert devices[0].uuid == "u1"
    assert devices[0].device_type == "mrs100"
    assert devices[0].online is True
    assert devices[0].channels == (0,)


def test_profiles_fixture_is_registered():
    registry = ProfileRegistry.from_catalog(fixture("profiles.json"))

    assert list(registry.profiles) == ["test.sample"]
    assert registry.schema_version == 2
    assert registry.profiles["test.sample"].source == "bundled"


def test_profiles_rev_fixture_shape():
    revision = fixture("profiles_rev.json")

    assert revision["schema_version"] in (1, 2)
    assert len(revision["revision"]) == 64


async def test_roller_shutter_fixture_is_normalized():
    fetch = AsyncMock(return_value=fixture("roller_shutter_config.json"))
    cache = RollerShutterConfigCache(SimpleNamespace(), fetch=fetch)

    state = await cache.async_get_channel("u1", 0)

    assert state.signal_open_ms == 45000
    assert state.signal_close_ms == 50000
    assert state.position == 40
    assert state.adjust == 2


async def test_client_uses_the_contracted_paths():
    http = SimpleNamespace(async_post=AsyncMock(return_value={}))

    await async_fetch_revision(http)
    await async_fetch_catalog(http)
    await async_fetch_public_key(http)
    await async_list_devices(http)

    paths = [call.args[0] for call in http.async_post.await_args_list]
    assert paths == [
        "/v1/Device/profiles/rev",
        "/v1/Device/profiles",
        "/v1/Device/profiles/pubkey",
        DEVICE_LIST_PATH,
    ]
