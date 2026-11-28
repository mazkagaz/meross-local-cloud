"""Repairs flow removing a device that left the broker long ago."""
from __future__ import annotations

import logging

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .common import (
    DOMAIN, MISSING_TRACKER, device_internal_id,
)
from .missing_devices import issue_id

_LOGGER = logging.getLogger(__name__)


async def async_remove_device(hass: HomeAssistant, device_uuid: str) -> None:
    """Drop the device from the manager, the registries and the tracker."""
    domain_data = hass.data.get(DOMAIN, {})
    registry = dr.async_get(hass)
    prefix = device_internal_id(device_uuid)
    devices = []
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        devices.extend(
            device
            for device in dr.async_entries_for_config_entry(
                registry, config_entry.entry_id)
            if any(
                domain == DOMAIN and (
                    identifier == prefix
                    or identifier.startswith(prefix + "#SUB:"))
                for domain, identifier in device.identifiers)
        )
    entities = er.async_get(hass)
    for device in devices:
        for entity in er.async_entries_for_device(
                entities, device.id, include_disabled_entities=True):
            entities.async_remove(entity.entity_id)
        registry.async_remove_device(device.id)

    tracker = domain_data.get(MISSING_TRACKER)
    if tracker is not None:
        await tracker.async_forget(device_uuid)
    ir.async_delete_issue(hass, DOMAIN, issue_id(device_uuid))


class RemoveMissingDeviceRepairFlow(RepairsFlow):
    """Ask the user before deleting the entities of an absent device."""

    def __init__(self, device_uuid: str, name: str) -> None:
        self._device_uuid = device_uuid
        self._name = name

    async def async_step_init(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        if user_input is not None:
            await async_remove_device(self.hass, self._device_uuid)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._name, "uuid": self._device_uuid},
        )


async def async_create_fix_flow(
        hass: HomeAssistant, issue_id_: str, data: dict | None
) -> RepairsFlow:
    data = data or {}
    return RemoveMissingDeviceRepairFlow(
        device_uuid=data.get("uuid", ""),
        name=data.get("name") or data.get("uuid", "device"),
    )
