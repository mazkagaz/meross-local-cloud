"""D1 broker adapter: profiles, MQTT transport and device descriptors."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant

from .broker_profiles import async_fetch_catalog, async_fetch_revision
from .broker_transport import BrokerMqttTransport

_LOGGER = logging.getLogger(__name__)

_DESCRIBE_TIMEOUT = 5
_TOTAL_BUDGET = 20


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
        self.profile_count = 0
        self.descriptors: Dict[str, Dict[str, Any]] = {}
        self.last_error: Optional[str] = None

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
            }
        if self.descriptors:
            _LOGGER.info(
                "Broker profile backend: revision %s, %d profile(s), "
                "%d device(s) described",
                (self.revision or "unknown")[:16], self.profile_count,
                len(self.descriptors))

    async def _async_fetch_profiles(self) -> None:
        client = self._coordinator.client
        endpoint = self._coordinator.http_api_endpoint
        revision = await async_fetch_revision(client, endpoint)
        catalog = await async_fetch_catalog(client, endpoint)
        self.revision = revision.get("revision")
        self.profile_count = int(revision.get("count") or 0)
        self.catalog_version = catalog.get("revision")

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
        return {
            "state": self.state,
            "revision": self.revision,
            "profiles": self.profile_count,
            "devices": len(self.descriptors),
            "last_error": self.last_error,
        }
