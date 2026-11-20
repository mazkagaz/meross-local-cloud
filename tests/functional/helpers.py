"""Shared helpers for the H2 functional harness."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import yaml
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.meross_cloud.common import BROKER_ADAPTER, DOMAIN
from custom_components.meross_cloud.profiles.compiler import compile_profile
from custom_components.meross_cloud.profiles.models import ProfileMeta
from custom_components.meross_cloud.profiles.runtime import DeviceRuntime

_LOGGER = logging.getLogger(__name__)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "profiles"


def compiled_fixture(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return compile_profile(ProfileMeta(
        id=data["profile"]["id"], version=data["profile"].get("version"),
        source="test", digest=None, requires_engine=None, data=data,
    ))


def runtime(name, uuid="u1"):
    return DeviceRuntime(uuid, compiled_fixture(name))


def catalog_entry(name):
    data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())
    return {
        "id": data["profile"]["id"],
        "version": data["profile"]["version"],
        "hash": "functional",
        "profile": data,
    }


class FakeAdapter:
    def __init__(self, runtime_obj, state="connected"):
        self.state = state
        self.runtimes = {runtime_obj.uuid: runtime_obj}
        self.schedulers = {}
        self.sent = []
        self.ready = []
        self.reloads = 0

    async def async_send(self, device_uuid, namespace, method, payload):
        self.sent.append((device_uuid, namespace, method, payload))
        return True

    async def async_reload_entry(self):
        self.reloads += 1
        return True

    def add_ready_listener(self, callback):
        if self.state == "connected":
            callback()
        else:
            self.ready.append(callback)


def entry(entities=True, only=False):
    options = {"profile_entities": entities}
    if only:
        options["profile_entities_only"] = True
    return SimpleNamespace(options=options)


async def setup_entities(hass, adapter, platform, config_entry):
    hass.data[DOMAIN] = {
        BROKER_ADAPTER: adapter,
        "ADDED_ENTITIES_IDS": set(),
    }
    component = EntityComponent(_LOGGER, platform, hass)

    def add(items, update_before_add=False):
        hass.async_create_task(component.async_add_entities(
            items, update_before_add=update_before_add))

    from custom_components.meross_cloud.profile_entities import (
        async_setup_profile_entities,
    )
    async_setup_profile_entities(hass, config_entry, platform, add)
    await hass.async_block_till_done()
    return component


async def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False
