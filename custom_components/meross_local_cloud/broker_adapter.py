"""D1 broker adapter: profiles, MQTT transport and device descriptors."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .broker_devices import async_list_devices
from .broker_http import BrokerHttpClient
from .broker_profiles import (
    async_fetch_catalog,
    async_fetch_public_key,
    async_fetch_revision,
    verify_catalog,
)
from .broker_transport import BrokerMqttTransport
from .runtime_store import (
    SAVE_DELAY,
    RuntimeStateStore,
    restore_runtimes,
)
from .common import (
    DOMAIN,
    MISSING_TRACKER,
    PROFILE_CATALOG_SIGNAL,
    SHUTTER_CONFIG_CACHE,
    device_internal_id,
)
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
    expand_channel_entities,
    match_candidates,
    match_profile,
)

_LOGGER = logging.getLogger(__name__)

_DESCRIBE_TIMEOUT = 5
_TOTAL_BUDGET = 20
_MAX_COMPILE_ERRORS = 20
CATALOG_CHECK_INTERVAL = 60.0
RECONNECT_REFRESH_DELAYS = (0.0, 5.0, 15.0, 30.0)


def unsupported_device_issue(device_uuid: str) -> str:
    return f"unsupported_device_{device_uuid}"


def _descriptor_channels(descriptor) -> list[int]:
    channels = getattr(descriptor, "channels", ()) or ()
    return sorted({
        channel for channel in channels
        if isinstance(channel, int) and not isinstance(channel, bool)
        and channel >= 0})


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
        self.device_online: Dict[str, bool] = {}
        self._unmatched: Dict[str, Dict[str, Any]] = {}
        self._ready_listeners: list = []
        self._listeners: list = []
        self._ever_connected = False
        self._transport_lost = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._state_store = None
        self._save_task: Optional[asyncio.Task] = None
        self._restored_runtime_entities = 0
        self.entities_only = False

    def add_listener(self, callback):
        """Notify callback when the adapter or a device availability changes."""
        self._listeners.append(callback)

        def remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return remove

    def _notify_changed(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001 - entity refresh must not fail
                _LOGGER.debug("Adapter listener failed", exc_info=True)

    def async_update_devices(self, devices) -> None:
        """Refresh per-device availability from a successful devList poll."""
        changed = False
        for device in devices:
            online = bool(getattr(device, "online", False))
            if self.device_online.get(device.uuid) != online:
                self.device_online[device.uuid] = online
                changed = True
        if changed:
            self._notify_changed()

    def device_available(self, device_uuid: str) -> bool:
        if self.state != "connected":
            return False
        if (self._transport is not None
                and hasattr(self._transport, "connected")
                and not self._transport.connected):
            return False
        return self.device_online.get(device_uuid, True)

    def _on_transport_state(self, connected: bool) -> None:
        if not connected:
            if self._ever_connected:
                self._transport_lost = True
            self._notify_changed()
            return
        if not self._ever_connected:
            self._ever_connected = True
            self._notify_changed()
            return
        if self._transport_lost:
            self._transport_lost = False
            self._hass.loop.call_soon_threadsafe(
                self._start_reconnect_burst)
        self._notify_changed()

    def _start_reconnect_burst(self) -> None:
        if self.state != "connected":
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        create = getattr(
            self._hass, "async_create_background_task", None)
        if create is not None:
            task = create(
                self._async_reconnect_burst(),
                name="meross_local_cloud_reconnect_refresh")
        else:
            task = self._hass.async_create_task(
                self._async_reconnect_burst())
        self._reconnect_task = task
        if task.done():
            self._reconnect_task = None

    async def _async_reconnect_burst(self) -> None:
        """Re-sync devList, the P3 cache and schedulers after a reconnect."""
        _LOGGER.info(
            "Broker MQTT reconnected; refreshing devices and schedulers")
        try:
            for delay in RECONNECT_REFRESH_DELAYS:
                if delay:
                    await asyncio.sleep(delay)
                if self.state != "connected":
                    return
                try:
                    coordinator = self._coordinator
                    refresh = getattr(
                        coordinator, "async_request_refresh", None)
                    if refresh is not None:
                        await refresh()
                    cache = (self._hass.data.get(DOMAIN) or {}).get(
                        SHUTTER_CONFIG_CACHE)
                    if cache is not None:
                        cache.invalidate()
                    for scheduler in self.schedulers.values():
                        scheduler.request_refresh()
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - retry next delay
                    _LOGGER.debug(
                        "Reconnect refresh failed: %s", err)
        finally:
            self._reconnect_task = None

    def unknown_devices(self, devices) -> set[str]:
        """UUIDs reported by devList that this adapter has not described."""
        return {
            device.uuid for device in devices
            if device.uuid not in self.descriptors
        }

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
            self._notify_changed()
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
        self._notify_changed()

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
            state_listener=self._on_transport_state,
        )
        await self._transport.async_connect()
        if self._http is None:
            raise RuntimeError("Broker HTTP client is not ready")
        devices = await async_list_devices(self._http)
        self.async_update_devices(devices)
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
                "name": getattr(device, "dev_name", device.uuid),
                "type": descriptor.type,
                "subType": descriptor.subType,
                "firmware": descriptor.fw_version,
                "hardware": getattr(device, "hardware", None),
                "abilities": sorted(descriptor.ability),
                "mac": descriptor.macAddress,
                "is_hub": descriptor.is_hub,
                "channels": _descriptor_channels(descriptor),
                "subdevices": _subdevice_descriptors(descriptor),
            }
        self._match_profiles()
        await self._async_restore_state()
        self._sync_unsupported_issues()
        self._start_schedulers()
        self._async_sync_profile_updates()
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
                self._unmatched[device_uuid] = {
                    "name": descriptor.get("name") or device_uuid,
                    "type": descriptor.get("type") or "unknown",
                    "uuid": device_uuid,
                }
                continue
            self.devices_matched += 1
            compiled = expand_channel_entities(
                self.compiler.compile(result.profile),
                descriptor.get("channels") or ())
            for warning in compiled.warnings:
                _LOGGER.debug("Profile warning: %s", warning)
            for error in compiled.errors:
                if len(self.compile_errors) < _MAX_COMPILE_ERRORS:
                    self.compile_errors.append(error)
            runtime = DeviceRuntime(device_uuid, compiled)
            runtime.add_listener(self._schedule_state_save)
            if descriptor["subdevices"]:
                bindings = self._match_subdevices(
                    compiled, descriptor["subdevices"])
                for subdevice_id, template in bindings.items():
                    runtime.add_subdevice(subdevice_id, template)
            self.runtimes[device_uuid] = runtime

    def _get_state_store(self):
        if getattr(self, "_state_store", None) is None:
            hass = getattr(self, "_hass", None)
            if hass is None or not hasattr(hass, "data"):
                return None
            try:
                self._state_store = RuntimeStateStore(hass)
            except Exception as err:  # noqa: BLE001 - optional persistence
                _LOGGER.debug("Runtime state store unavailable: %s", err)
                return None
        return self._state_store

    async def _async_restore_state(self) -> None:
        store = self._get_state_store()
        if store is None:
            return
        data = await store.async_load()
        if data is None:
            return
        self._restored_runtime_entities = restore_runtimes(data, self.runtimes)
        if self._restored_runtime_entities:
            _LOGGER.info(
                "Restored %d profile entity state(s) from the previous run",
                self._restored_runtime_entities)

    def _schedule_state_save(self) -> None:
        hass = getattr(self, "_hass", None)
        if hass is None:
            return
        task = getattr(self, "_save_task", None)
        if task is not None and not task.done():
            return
        if self._get_state_store() is None:
            return
        if not hasattr(hass, "async_create_background_task"):
            self._save_task = hass.async_create_task(
                self._async_save_state())
            return
        self._save_task = hass.async_create_background_task(
            self._async_save_state(), name="meross_local_cloud_state_save")

    async def _async_save_state(self) -> None:
        try:
            await asyncio.sleep(SAVE_DELAY)
            store = self._get_state_store()
            if store is not None:
                await store.async_save(self.runtimes)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - persistence is best effort
            _LOGGER.debug("Runtime state save task failed: %s", err)

    def _sync_unsupported_issues(self) -> None:
        if getattr(self._hass, "data", None) is None:
            return
        for device_uuid in self.descriptors:
            if device_uuid not in self._unmatched:
                ir.async_delete_issue(
                    self._hass, DOMAIN,
                    unsupported_device_issue(device_uuid))
        for device_uuid, info in self._unmatched.items():
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                unsupported_device_issue(device_uuid),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="unsupported_device",
                translation_placeholders=info,
                data=info,
            )

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
            create = getattr(
                self._hass, "async_create_background_task", None)
            if create is not None:
                self._watch_task = create(
                    self._async_watch_catalog(),
                    name="meross_local_cloud_catalog_watch")
            else:
                self._watch_task = self._hass.async_create_task(
                    self._async_watch_catalog())

    async def _async_watch_catalog(self) -> None:
        """Advertise profile updates without applying them automatically."""
        try:
            while True:
                await asyncio.sleep(CATALOG_CHECK_INTERVAL)
                try:
                    http = BrokerHttpClient(
                        self._coordinator.http_api_endpoint,
                        lambda: self._coordinator.credentials.token,
                        self._coordinator.mqtt_ssl_context,
                        user_agent=getattr(
                            self._coordinator, "user_agent",
                            "MerossHA/unknown"))
                    revision = await async_fetch_revision(http)
                except Exception as err:  # noqa: BLE001 - retry next tick
                    _LOGGER.debug("Catalog revision check failed: %s", err)
                    continue
                observed = revision.get("revision")
                if not observed or not self.revision or observed == self.revision:
                    continue
                previous = self.revision
                try:
                    await self._async_fetch_profiles()
                except Exception as err:  # noqa: BLE001 - retry next tick
                    _LOGGER.debug("Catalog refresh failed: %s", err)
                    continue
                _LOGGER.info(
                    "Device profile catalog changed (%s -> %s); updates are "
                    "available for manual installation", previous[:16],
                    (self.revision or "?")[:16])
                self._async_sync_profile_updates()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - watch is best effort
            _LOGGER.debug("Catalog watcher stopped: %s", err)

    @staticmethod
    def _profile_notification_id(profile_id: str) -> str:
        return f"meross_local_cloud_profile_{profile_id}"

    def _async_sync_profile_updates(self) -> None:
        """Refresh update entities and persistent notifications."""
        if not hasattr(self._hass, "async_create_task"):
            return
        try:
            from homeassistant.components import persistent_notification
        except Exception:  # noqa: BLE001 - notifications are best effort
            persistent_notification = None
        if persistent_notification is not None:
            self._hass.async_create_task(
                self._async_sync_notifications(persistent_notification))
        try:
            async_dispatcher_send(self._hass, PROFILE_CATALOG_SIGNAL)
        except Exception:  # noqa: BLE001 - entity refresh is best effort
            _LOGGER.debug("Profile catalog signal failed", exc_info=True)

    async def _async_sync_notifications(self, notifications) -> None:
        registry = self.registry
        seen = set()
        for runtime in self.runtimes.values():
            profile_id = runtime.profile.profile_id
            if profile_id in seen:
                continue
            seen.add(profile_id)
            latest = None
            if registry is not None:
                meta = registry.profiles.get(profile_id)
                latest = meta.version if meta is not None else None
            installed = runtime.profile.version
            notification_id = self._profile_notification_id(profile_id)
            try:
                if latest and installed and latest != installed:
                    notifications.async_create(
                        self._hass,
                        "Une mise à jour du profil est disponible : "
                        f"`{profile_id}` {installed} → {latest}. "
                        "Utilisez l'entité `update` correspondante puis "
                        "**Installer**.",
                        title="Meross Local Cloud — profil à mettre à jour",
                        notification_id=notification_id)
                else:
                    notifications.async_dismiss(
                        self._hass, notification_id)
            except Exception:  # noqa: BLE001 - notifications are best effort
                _LOGGER.debug(
                    "Profile update notification failed", exc_info=True)

    def dismiss_profile_update(self, profile_id: str) -> None:
        try:
            from homeassistant.components import persistent_notification
        except Exception:  # noqa: BLE001 - notifications are best effort
            return
        try:
            persistent_notification.async_dismiss(
                self._hass, self._profile_notification_id(profile_id))
        except Exception:  # noqa: BLE001 - notifications are best effort
            _LOGGER.debug(
                "Dismissing profile notification failed", exc_info=True)

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

    async def async_send_priority(self, device_uuid: str, namespace: str,
                                  method: str, payload) -> bool:
        """Send a safety command immediately, without ACK wait or rate limit."""
        transport = self._transport
        if transport is None:
            return False
        if hasattr(transport, "async_publish_priority"):
            await transport.async_publish_priority(
                device_uuid, namespace, method, payload)
        else:
            await self.async_send(device_uuid, namespace, method, payload)
            return True
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
        if message.namespace == "Appliance.Control.Unbind":
            self._hass.loop.call_soon_threadsafe(
                self._hass.async_create_task,
                self._async_remove_unbound(device_uuid))
            return
        self._apply_online(device_uuid, message.namespace, message.payload)
        runtime = self.runtimes.get(device_uuid)
        if runtime is None:
            return
        try:
            runtime.dispatch(message.namespace, message.method,
                             message.payload)
        except Exception as err:  # noqa: BLE001 - dispatch is best effort
            _LOGGER.debug("Payload dispatch failed for %s: %s",
                          device_uuid, err)

    async def _async_remove_unbound(self, device_uuid: str) -> None:
        """Remove a device and its subdevices after an Unbind push."""
        _LOGGER.warning("Device %s was unbound; removing it", device_uuid)
        registry = dr.async_get(self._hass)
        entry_id = getattr(self._coordinator, "config_entry_id", None)
        prefix = device_internal_id(device_uuid)
        devices = [
            entry for entry in (
                dr.async_entries_for_config_entry(registry, entry_id)
                if entry_id else [])
            if any(
                domain == DOMAIN and (
                    identifier == prefix
                    or identifier.startswith(prefix + "#SUB:"))
                for domain, identifier in entry.identifiers)
        ]
        top = registry.async_get_device({(DOMAIN, prefix)})
        if top is not None and top not in devices:
            devices.append(top)

        entity_registry = er.async_get(self._hass)
        for device in devices:
            for entity in er.async_entries_for_device(
                    entity_registry, device.id,
                    include_disabled_entities=True):
                entity_registry.async_remove(entity.entity_id)
            registry.async_remove_device(device.id)

        scheduler = self.schedulers.pop(device_uuid, None)
        if scheduler is not None:
            await scheduler.async_stop()
        self.runtimes.pop(device_uuid, None)
        self.descriptors.pop(device_uuid, None)
        self._schedule_state_save()
        self.device_online.pop(device_uuid, None)
        self._unmatched.pop(device_uuid, None)
        ir.async_delete_issue(
            self._hass, DOMAIN, unsupported_device_issue(device_uuid))

        tracker = (self._hass.data.get(DOMAIN) or {}).get(MISSING_TRACKER)
        if tracker is not None:
            await tracker.async_forget(device_uuid)
        self._notify_changed()

    def _apply_online(self, device_uuid: str, namespace: str,
                      payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        status = None
        if namespace == "Appliance.System.Online":
            status = (payload.get("online") or {}).get("status")
        elif namespace == "Appliance.Hub.Online":
            status = payload.get("status")
        if status is None:
            return
        try:
            online = int(status) == 1
        except (TypeError, ValueError):
            return
        if self.device_online.get(device_uuid) == online:
            return
        self.device_online[device_uuid] = online
        self._notify_changed()

    async def _async_fetch_profiles(self) -> None:
        endpoint = self._coordinator.http_api_endpoint
        http = BrokerHttpClient(
            endpoint,
            lambda: self._coordinator.credentials.token,
            self._coordinator.mqtt_ssl_context,
            user_agent=getattr(
                self._coordinator, "user_agent", "MerossHA/unknown"))
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
        reconnect_task, self._reconnect_task = self._reconnect_task, None
        if reconnect_task is not None and not reconnect_task.done():
            reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reconnect_task
        for scheduler in self.schedulers.values():
            await scheduler.async_stop()
        self.schedulers.clear()
        save_task, self._save_task = self._save_task, None
        if save_task is not None and not save_task.done():
            save_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await save_task
        store = self._get_state_store()
        if store is not None:
            await store.async_save(self.runtimes)
        if self._transport is not None:
            await self._transport.async_stop()
            self._transport = None
        self.state = "stopped"
        self._notify_changed()

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
            "restored_runtime_entities": self._restored_runtime_entities,
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
        summary["entities_only"] = self.entities_only
        return summary
