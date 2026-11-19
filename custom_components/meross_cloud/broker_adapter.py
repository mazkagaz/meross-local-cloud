"""D1 broker adapter: profiles, MQTT transport and device descriptors."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant

from .broker_profiles import async_fetch_catalog, async_fetch_revision
from .broker_transport import BrokerMqttTransport

_LOGGER = logging.getLogger(__name__)


class BrokerProfileAdapter:
    """Opt-in probe of the profile backend.

    It validates the profile catalog and builds descriptors over the broker
    MQTT transport. It never creates or changes business entities.
    """

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._transport: Optional[BrokerMqttTransport] = None
        self.revision: Optional[str] = None
        self.catalog_version: Optional[str] = None
        self.profile_count = 0
        self.descriptors: Dict[str, Dict[str, Any]] = {}
        self.last_error: Optional[str] = None
        self._started = False

    async def async_start(self) -> None:
        try:
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
                    descriptor = await self._transport.async_describe(
                        device.uuid)
                except Exception as err:  # noqa: BLE001 - per-device probe
                    _LOGGER.warning(
                        "Unable to describe device %s over MQTT: %s",
                        device.uuid, err)
                    continue
                self.descriptors[device.uuid] = {
                    "type": descriptor.type,
                    "subType": descriptor.subType,
                    "firmware": descriptor.fw_version,
                    "abilities": sorted(descriptor.ability),
                }
            self._started = True
            _LOGGER.info(
                "Broker profile backend ready: revision %s, %d profile(s), "
                "%d device(s) described",
                (self.revision or "unknown")[:16], self.profile_count,
                len(self.descriptors))
        except Exception as err:  # noqa: BLE001 - probe must not break setup
            self.last_error = str(err)
            _LOGGER.warning("Broker profile backend unavailable: %s", err)

    async def _async_fetch_profiles(self) -> None:
        client = self._coordinator.client
        endpoint = self._coordinator.http_api_endpoint
        revision = await async_fetch_revision(client, endpoint)
        catalog = await async_fetch_catalog(client, endpoint)
        self.revision = revision.get("revision")
        self.profile_count = int(revision.get("count") or 0)
        self.catalog_version = catalog.get("revision")

    async def async_stop(self) -> None:
        if self._transport is not None:
            await self._transport.async_stop()
            self._transport = None
        self._started = False

    def summary(self) -> Dict[str, Any]:
        connected = bool(self._transport and self._transport.connected)
        if self.last_error:
            state = "error"
        elif self._started and connected:
            state = "connected"
        else:
            state = "disconnected"
        return {
            "state": state,
            "revision": self.revision,
            "profiles": self.profile_count,
            "devices": len(self.descriptors),
            "last_error": self.last_error,
        }
