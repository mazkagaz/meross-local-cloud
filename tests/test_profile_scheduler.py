import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import yaml

from custom_components.meross_local_cloud.profiles import scheduler as scheduler_module
from custom_components.meross_local_cloud.profiles.compiler import compile_profile
from custom_components.meross_local_cloud.profiles.models import ProfileMeta
from custom_components.meross_local_cloud.profiles.runtime import DeviceRuntime
from custom_components.meross_local_cloud.profiles.scheduler import DeviceScheduler

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"
TOGGLE_NS = "Appliance.Control.ToggleX"
ELECTRICITY_NS = "Appliance.Control.Electricity"


def compiled_fixture(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return compile_profile(ProfileMeta(
        id=data["profile"]["id"], version=data["profile"].get("version"),
        source="test", digest=None, requires_engine=None, data=data,
    ))


def compiled_profile(namespaces, entities=None):
    data = {
        "schema_version": 2,
        "profile": {"id": "test.scheduler", "version": "1"},
        "match": {"type": ["test"]},
        "payloads": namespaces,
        "entities": entities or [],
    }
    return compile_profile(ProfileMeta(
        id="test.scheduler", version="1", source="test", digest=None,
        requires_engine=None, data=data,
    ))


class FakeSender:
    def __init__(self, multiple_payload=None, single_payload=None):
        self.requests = []
        self.multiples = []
        self.multiple_payload = multiple_payload or {}
        self.single_payload = single_payload or {}
        self.error = None

    async def async_request(self, uuid, namespace, method, payload):
        if self.error is not None:
            raise self.error
        self.requests.append((uuid, namespace, method, payload))
        return SimpleNamespace(
            namespace=namespace, method="GETACK",
            payload=self.single_payload.get(namespace, {}))

    async def async_request_multiple(self, uuid, requests):
        if self.error is not None:
            raise self.error
        requests = list(requests)
        self.multiples.append((uuid, requests))
        entries = [{
            "header": {"namespace": namespace, "method": "GETACK"},
            "payload": self.multiple_payload.get(namespace, {}),
        } for namespace, _, _ in requests]
        return SimpleNamespace(
            namespace="Appliance.Control.Multiple", method="SETACK",
            payload={"multiple": entries})


async def wait_for(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return False


async def test_push_namespaces_are_batched_and_polled_once():
    profile = compiled_fixture("mss310")
    runtime = DeviceRuntime("u1", profile)
    sender = FakeSender(multiple_payload={
        TOGGLE_NS: {"channel": 0, "togglex": [{"channel": 0, "onoff": 1}]},
        ELECTRICITY_NS: {"channel": 0, "electricity": {"power": 10}},
    })
    scheduler = DeviceScheduler(
        "u1", profile, runtime, sender, rate_limit=0)

    scheduler.start()
    try:
        assert await wait_for(lambda: sender.multiples)
        await asyncio.sleep(0.05)
        assert len(sender.multiples) == 1
        assert {request[0] for request in sender.multiples[0][1]} == {
            TOGGLE_NS, ELECTRICITY_NS}
        assert sender.requests == []
        assert runtime.entities["switch"].values == {"onoff": 1}
        assert scheduler.batches == 1
        assert scheduler.polls == 2
    finally:
        await scheduler.async_stop()


async def test_single_namespace_uses_an_individual_request():
    namespace = "Appliance.Test"
    profile = compiled_profile({
        namespace: {"methods": ["GET", "GETACK"], "polling": {"period_s": 3600}},
    })
    sender = FakeSender(single_payload={namespace: {"value": 1}})
    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), sender, rate_limit=0)

    scheduler.start()
    try:
        assert await wait_for(lambda: sender.requests)
        assert sender.multiples == []
    finally:
        await scheduler.async_stop()


async def test_periodic_namespace_is_polled_again():
    namespace = "Appliance.Test"
    profile = compiled_profile({
        namespace: {"methods": ["GET", "GETACK"], "polling": {"period_s": 0.02}},
    })
    sender = FakeSender()
    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), sender, rate_limit=0)

    scheduler.start()
    try:
        assert await wait_for(lambda: len(sender.requests) >= 2)
    finally:
        await scheduler.async_stop()


async def test_lazy_refresh_triggers_a_poll():
    namespace = "Appliance.Test"
    profile = compiled_profile({
        namespace: {"methods": ["GET", "GETACK"], "polling": {"period_s": 3600}},
    })
    sender = FakeSender()
    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), sender, rate_limit=0)

    scheduler.start()
    try:
        assert await wait_for(lambda: len(sender.requests) == 1)
        scheduler.request_refresh(namespace)
        assert await wait_for(lambda: len(sender.requests) == 2)
        assert scheduler.lazy == 1
    finally:
        await scheduler.async_stop()


async def test_failure_backs_off_then_recovers(monkeypatch):
    monkeypatch.setattr(scheduler_module, "FAILURE_BACKOFF", 0.02)
    namespace = "Appliance.Test"
    profile = compiled_profile({
        namespace: {"methods": ["GET", "GETACK"], "polling": {"period_s": 0.01}},
    })
    sender = FakeSender()
    sender.error = RuntimeError("timeout")
    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), sender, rate_limit=0)

    scheduler.start()
    try:
        assert await wait_for(lambda: scheduler.errors >= 1)
        sender.error = None
        assert await wait_for(lambda: sender.requests)
    finally:
        await scheduler.async_stop()


async def test_start_is_idempotent_and_stop_cancels():
    profile = compiled_fixture("mss310")
    sender = FakeSender()
    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), sender, rate_limit=0)

    first = scheduler.start()
    second = scheduler.start()

    assert first is second
    await scheduler.async_stop()
    assert first.cancelled() or first.done()


async def test_profile_without_pollable_namespaces_has_no_task():
    profile = compiled_profile({
        "Appliance.Test": {"methods": ["SET", "SETACK"]},
    })
    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), FakeSender())

    assert scheduler.start() is None


async def test_malformed_multiple_response_is_ignored():
    profile = compiled_profile({
        "Appliance.Test.One": {"methods": ["GET", "GETACK"]},
        "Appliance.Test.Two": {"methods": ["GET", "GETACK"]},
    })

    class BrokenSender(FakeSender):
        async def async_request_multiple(self, uuid, requests):
            return SimpleNamespace(
                namespace="Appliance.Control.Multiple", method="SETACK",
                payload=["nope"])

    scheduler = DeviceScheduler(
        "u1", profile, DeviceRuntime("u1", profile), BrokenSender(),
        rate_limit=0)
    scheduler.start()
    try:
        await asyncio.sleep(0.05)
        assert scheduler.errors == 0
    finally:
        await scheduler.async_stop()


def test_set_only_namespaces_are_not_polled():
    profile = compiled_fixture("mrs100")
    runtime = DeviceRuntime("u1", profile)
    scheduler = DeviceScheduler("u1", profile, runtime, FakeSender())

    assert "Appliance.RollerShutter.Adjust" not in scheduler._plan
    assert "Appliance.RollerShutter.Position" in scheduler._plan
