"""D1 broker adapter: profiles, MQTT transport and device descriptors."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant

from .broker_profiles import async_fetch_catalog, async_fetch_revision
from .broker_transport import BrokerMqttTransport
from .profiles import (
    ENGINE_VERSION,
    MatchContext,
    ProfileCompiler,
    ProfileRegistry,
    match_profile,
)

_LOGGER = logging.getLogger(__name__)

_DESCRIBE_TIMEOUT = 5
_TOTAL_BUDGET = 20
_MAX_COMPILE_ERRORS = 20


class BrokerProfileAdapter:
    """Opt-in probe of the profile backend.

    It validates the profile catalog and builds descriptors over the broker
    MQTT transport. It never creates or changes business entities and it runs
    after the platforms are mounted, so a slow broker cannot delay setup.
    """

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._transport: Optional[BrokerMqttTransport] = None
        self._task: Optional[asyncio.Task] = None
        self.state = "idle"
        self.revision: Optional[str] = None
        self.catalog_version: Optional[str] = None
        self.registry: Optional[ProfileRegistry] = None
        self.profile_count = 0
        self.descriptors: Dict[str, Dict[str, Any]] = {}
        self.last_error: Optional[str] = None
        self.compiler = ProfileCompiler()
        self.devices_matched = 0
        self.devices_unmatched = 0
        self.match_ambiguities = 0
        self.compile_errors: list[str] = []

    def start_background(self, hass: HomeAssistant) -> None:
        if self._task is None or self._task.done():
            self._task = hass.async_create_task(self.async_start())

    async def async_start(self) -> None:
        self.state = "starting"
        self.last_error = None
        try:
            async with asyncio.timeout(_TOTAL_BUDGET):
                await self._async_probe()
        except asyncio.CancelledError:
            self.state = "stopped"
            raise
        except TimeoutError as err:
            self.last_error = f"timeout after {_TOTAL_BUDGET}s"
            self.state = "error"
            _LOGGER.warning("Broker profile backend: %s", self.last_error)
        except Exception as err:  # noqa: BLE001 - probe must not break setup
            self.last_error = str(err)
            self.state = "error"
            _LOGGER.warning("Broker profile backend unavailable: %s", err)
        else:
            self.state = "error" if self.last_error else "connected"

    async def _async_probe(self) -> None:
        mqtt_host, mqtt_port = self._coordinator.mqtt_address
        await self._async_fetch_profiles()
        self._transport = BrokerMqttTransport(
            mqtt_host,
            mqtt_port,
            self._coordinator.credentials.user_id,
            self._coordinator.credentials.key,
            self._coordinator.mqtt_ssl_context,
            self._hass.loop,
        )
        await self._transport.async_connect()
        devices = await self._coordinator.client.async_list_devices()
        for device in devices:
            try:
                async with asyncio.timeout(_DESCRIBE_TIMEOUT):
                    descriptor = await self._transport.async_describe(
                        device.uuid)
            except Exception as err:  # noqa: BLE001 - abort at first failure
                self.last_error = f"{type(err).__name__}: {err}"
                _LOGGER.warning(
                    "Unable to describe device %s over MQTT: %s",
                    device.uuid, err)
                break
            self.descriptors[device.uuid] = {
                "type": descriptor.type,
                "subType": descriptor.subType,
                "firmware": descriptor.fw_version,
                "abilities": sorted(descriptor.ability),
                "mac": descriptor.macAddress,
                "is_hub": descriptor.is_hub,
            }
        self._match_profiles()
        if self.descriptors:
            _LOGGER.info(
                "Broker profile backend: revision %s, %d profile(s), "
                "%d device(s) described, %d matched (%d compiled)",
                (self.revision or "unknown")[:16], self.profile_count,
                len(self.descriptors), self.devices_matched,
                self.compiler.cache_size)

    def _match_profiles(self) -> None:
        """Match descriptors and compile profiles lazily. No entities, no IO."""
        if self.registry is None:
            return
        for descriptor in self.descriptors.values():
            context = MatchContext(
                type=descriptor["type"],
                sub_type=descriptor["subType"],
                mac=descriptor["mac"],
                abilities=frozenset(descriptor["abilities"]),
                is_hub=bool(descriptor["is_hub"]),
            )
            result = match_profile(self.registry, context)
            if result.ambiguous:
                self.match_ambiguities += 1
            if result.profile is None:
                self.devices_unmatched += 1
                continue
            self.devices_matched += 1
            compiled = self.compiler.compile(result.profile)
            for warning in compiled.warnings:
                _LOGGER.debug("Profile warning: %s", warning)
            for error in compiled.errors:
                if len(self.compile_errors) < _MAX_COMPILE_ERRORS:
                    self.compile_errors.append(error)

    async def _async_fetch_profiles(self) -> None:
        client = self._coordinator.client
        endpoint = self._coordinator.http_api_endpoint
        revision = await async_fetch_revision(client, endpoint)
        catalog = await async_fetch_catalog(client, endpoint)
        self.revision = revision.get("revision")
        self.profile_count = int(revision.get("count") or 0)
        self.catalog_version = catalog.get("revision")
        self.registry = ProfileRegistry.from_catalog(catalog)
        _LOGGER.info(
            "Device profile engine %s: %d profile(s) loaded, %d skipped, "
            "%d catalog error(s)",
            ENGINE_VERSION, len(self.registry.profiles),
            len(self.registry.skipped), len(self.registry.errors))

    async def async_stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._transport is not None:
            await self._transport.async_stop()
            self._transport = None
        self.state = "stopped"

    def summary(self) -> Dict[str, Any]:
        summary = {
            "state": self.state,
            "revision": self.revision,
            "profiles": self.profile_count,
            "devices": len(self.descriptors),
            "last_error": self.last_error,
            "engine_version": ENGINE_VERSION,
            "profiles_compiled": self.compiler.cache_size,
            "devices_matched": self.devices_matched,
            "devices_unmatched": self.devices_unmatched,
            "match_ambiguities": self.match_ambiguities,
            "compile_errors": list(self.compile_errors),
        }
        if self.registry is not None:
            summary.update(self.registry.summary())
        return summary
