"""D1 broker adapter: profiles, MQTT transport and device descriptors."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant

from .broker_devices import async_list_devices
from .broker_http import BrokerHttpClient
from .broker_profiles import (
    async_fetch_catalog,
    async_fetch_public_key,
    async_fetch_revision,
    verify_catalog,
)
from .broker_transport import BrokerMqttTransport
from .profiles import (
    ENGINE_VERSION,
    CompiledProfile,
    DeviceRuntime,
    DeviceScheduler,
    MatchContext,
    ProfileCompiler,
    ProfileMeta,
    ProfileRegistry,
    SubDeviceTemplate,
    match_candidates,
    match_profile,
)

_LOGGER = logging.getLogger(__name__)

_DESCRIBE_TIMEOUT = 5
_TOTAL_BUDGET = 20
_MAX_COMPILE_ERRORS = 20
CATALOG_CHECK_INTERVAL = 60.0


def _subdevice_descriptors(descriptor) -> list[Dict[str, Any]]:
    if not descriptor.is_hub:
        return []
    try:
        return [
            {"id": subdevice.id, "type": subdevice.type,
             "subType": subdevice.subType}
            for subdevice in descriptor.subdevices
        ]
    except Exception as err:  # noqa: BLE001 - a bad digest must not abort
        _LOGGER.debug("Unable to read hub subdevices: %s", err)
        return []


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
        self._http: Optional[BrokerHttpClient] = None
        self._task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._entry_id = getattr(coordinator, "config_entry_id", None)
        self.state = "idle"
        self.revision: Optional[str] = None
        self.catalog_version: Optional[str] = None
        self.signature_status = "unknown"
        self.public_key_fingerprint: Optional[str] = None
        self.registry: Optional[ProfileRegistry] = None
        self.profile_count = 0
        self.descriptors: Dict[str, Dict[str, Any]] = {}
        self.last_error: Optional[str] = None
        self.compiler = ProfileCompiler()
        self.devices_matched = 0
        self.devices_unmatched = 0
        self.subdevices_matched = 0
        self.subdevices_unmatched = 0
        self.match_ambiguities = 0
        self.compile_errors: list[str] = []
        self.runtimes: Dict[str, DeviceRuntime] = {}
        self.schedulers: Dict[str, DeviceScheduler] = {}
        self._ready_listeners: list = []

    def add_ready_listener(self, callback) -> None:
        """Call callback once matching is done (or immediately if already)."""
        if self.state == "connected":
            callback()
            return
        self._ready_listeners.append(callback)

    def _notify_ready(self) -> None:
        listeners, self._ready_listeners = self._ready_listeners, []
        for callback in listeners:
            try:
                callback()
            except Exception:  # noqa: BLE001 - entity platforms must not fail
                _LOGGER.exception("Profile entity listener failed")

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
            if self.state == "connected":
                self._notify_ready()
                self._start_catalog_watch()

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
            message_listener=self._dispatch_message,
        )
        await self._transport.async_connect()
        if self._http is None:
            raise RuntimeError("Broker HTTP client is not ready")
        devices = await async_list_devices(self._http)
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
                "subdevices": _subdevice_descriptors(descriptor),
            }
        self._match_profiles()
        self._start_schedulers()
        if self.descriptors:
            _LOGGER.info(
                "Broker profile backend: revision %s, %d profile(s), "
                "%d device(s) described, %d matched (%d compiled), "
                "%d subdevice(s) matched",
                (self.revision or "unknown")[:16], self.profile_count,
                len(self.descriptors), self.devices_matched,
                self.compiler.cache_size, self.subdevices_matched)

    def _match_profiles(self) -> None:
        """Match descriptors and compile profiles lazily. No entities, no IO."""
        if self.registry is None:
            return
        for device_uuid, descriptor in self.descriptors.items():
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
            runtime = DeviceRuntime(device_uuid, compiled)
            if descriptor["subdevices"]:
                bindings = self._match_subdevices(
                    compiled, descriptor["subdevices"])
                for subdevice_id, template in bindings.items():
                    runtime.add_subdevice(subdevice_id, template)
            self.runtimes[device_uuid] = runtime

    def _match_subdevices(self, compiled: CompiledProfile,
                          subdevices: list[Dict[str, Any]]
                          ) -> Dict[str, SubDeviceTemplate]:
        templates = {template.uid: template
                     for template in compiled.subdevices}
        options = [
            ProfileMeta(
                id=template.uid,
                version=compiled.version,
                source="template",
                digest=None,
                requires_engine=None,
                data={"match": template.match},
            )
            for template in compiled.subdevices
        ]
        bindings = {}
        for subdevice in subdevices:
            result = match_candidates(
                options,
                MatchContext(
                    type=subdevice["type"],
                    sub_type=subdevice["subType"],
                ),
            )
            if result.ambiguous:
                self.match_ambiguities += 1
            if result.profile is None:
                self.subdevices_unmatched += 1
            else:
                self.subdevices_matched += 1
                bindings[subdevice["id"]] = templates[result.profile.id]
        return bindings

    def _start_schedulers(self) -> None:
        """Start one central polling task per device (opt-in backend only)."""
        transport = self._transport
        if transport is None or not (
                hasattr(transport, "async_request")
                and hasattr(transport, "async_request_multiple")):
            return
        for device_uuid, runtime in self.runtimes.items():
            scheduler = DeviceScheduler(
                device_uuid, runtime.profile, runtime, transport)
            self.schedulers[device_uuid] = scheduler
            scheduler.start()

    def _start_catalog_watch(self) -> None:
        if not self._entry_id or not hasattr(
                self._hass, "async_create_task"):
            return
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = self._hass.async_create_task(
                self._async_watch_catalog())

    async def _async_watch_catalog(self) -> None:
        """Reload the config entry when the broker catalog revision changes."""
        try:
            while True:
                await asyncio.sleep(CATALOG_CHECK_INTERVAL)
                try:
                    http = BrokerHttpClient(
                        self._coordinator.http_api_endpoint,
                        lambda: self._coordinator.credentials.token,
                        self._coordinator.mqtt_ssl_context)
                    revision = await async_fetch_revision(http)
                except Exception as err:  # noqa: BLE001 - retry next tick
                    _LOGGER.debug("Catalog revision check failed: %s", err)
                    continue
                observed = revision.get("revision")
                if not observed or not self.revision or observed == self.revision:
                    continue
                _LOGGER.info(
                    "Device profile catalog changed (%s -> %s), reloading "
                    "the integration entry", self.revision[:16],
                    observed[:16])
                if self._entry_id is None:
                    return
                await self._hass.config_entries.async_reload(self._entry_id)
                return
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - watch is best effort
            _LOGGER.debug("Catalog watcher stopped: %s", err)

    async def async_reload_entry(self) -> bool:
        if not self._entry_id or not hasattr(self._hass, "config_entries"):
            return False
        await self._hass.config_entries.async_reload(self._entry_id)
        return True

    async def async_send(self, device_uuid: str, namespace: str, method: str,
                         payload) -> bool:
        """Send a command for a profile entity and refresh its namespace."""
        transport = self._transport
        if transport is None or not hasattr(transport, "async_request"):
            return False
        response = await transport.async_request(
            device_uuid, namespace, method, payload)
        self._dispatch_message(response)
        scheduler = self.schedulers.get(device_uuid)
        if scheduler is not None:
            scheduler.request_refresh(namespace)
        return True

    def _dispatch_message(self, message) -> None:
        """Route one decoded MQTT message to the matching device runtime."""
        try:
            device_uuid = message.uuid
        except Exception:  # noqa: BLE001 - malformed header or topic
            _LOGGER.debug("Payload without a device uuid ignored",
                          exc_info=True)
            return
        runtime = self.runtimes.get(device_uuid)
        if runtime is None:
            return
        try:
            runtime.dispatch(message.namespace, message.method,
                             message.payload)
        except Exception as err:  # noqa: BLE001 - dispatch is best effort
            _LOGGER.debug("Payload dispatch failed for %s: %s",
                          device_uuid, err)

    async def _async_fetch_profiles(self) -> None:
        endpoint = self._coordinator.http_api_endpoint
        http = BrokerHttpClient(
            endpoint,
            lambda: self._coordinator.credentials.token,
            self._coordinator.mqtt_ssl_context)
        self._http = http
        revision = await async_fetch_revision(http)
        catalog = await async_fetch_catalog(http)
        self.signature_status = "absent"
        if isinstance(catalog, dict) and catalog.get("signature"):
            public = await async_fetch_public_key(http)
            pem = public.get("public_key") if isinstance(public, dict) else None
            if not pem or not verify_catalog(catalog, pem):
                self.signature_status = "invalid"
                raise ValueError("invalid profile catalog signature")
            self.signature_status = "valid"
            self.public_key_fingerprint = public.get("fingerprint")
        self.revision = revision.get("revision")
        self.profile_count = int(revision.get("count") or 0)
        self.catalog_version = catalog.get("revision")
        if (self.revision and self.catalog_version
                and self.revision != self.catalog_version):
            _LOGGER.warning(
                "Profile catalog revision %s does not match the revision "
                "endpoint %s", self.catalog_version, self.revision)
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
        watch_task, self._watch_task = self._watch_task, None
        if watch_task is not None and not watch_task.done():
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task
        for scheduler in self.schedulers.values():
            await scheduler.async_stop()
        self.schedulers.clear()
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
            "subdevices_matched": self.subdevices_matched,
            "subdevices_unmatched": self.subdevices_unmatched,
            "match_ambiguities": self.match_ambiguities,
            "compile_errors": list(self.compile_errors),
            "runtime_messages": sum(
                runtime.messages for runtime in self.runtimes.values()),
            "runtime_updates": sum(
                runtime.updates for runtime in self.runtimes.values()),
            "runtime_ignored": sum(
                runtime.ignored for runtime in self.runtimes.values()),
            "runtime_errors": [
                error
                for runtime in self.runtimes.values()
                for error in runtime.errors
            ][:_MAX_COMPILE_ERRORS],
            "scheduler_polls": sum(
                scheduler.polls for scheduler in self.schedulers.values()),
            "scheduler_batches": sum(
                scheduler.batches for scheduler in self.schedulers.values()),
            "scheduler_errors": sum(
                scheduler.errors for scheduler in self.schedulers.values()),
        }
        if self.registry is not None:
            summary.update(self.registry.summary())
            summary["profiles_overridden"] = sum(
                1 for profile in self.registry.profiles.values()
                if profile.source == "override")
        summary["catalog_revision"] = self.catalog_version
        summary["catalog_signature"] = self.signature_status
        summary["catalog_key_fingerprint"] = self.public_key_fingerprint
        return summary
