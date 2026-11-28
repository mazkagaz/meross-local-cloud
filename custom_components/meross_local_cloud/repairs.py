"""Repairs flows for missing devices and broker CA changes."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import (
    ConfigEntryDisabler,
    OperationNotAllowed,
    UnknownEntry,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .common import (
    DOMAIN, MISSING_TRACKER, device_internal_id,
)
from .missing_devices import issue_id

_LOGGER = logging.getLogger(__name__)

CA_CHANGE_ISSUE_PREFIX = "ca_changed_"


def ca_change_issue_id(entry_id: str, new_fingerprint: str) -> str:
    """Return a stable issue id for one entry and one new CA."""
    token = "".join(
        char for char in new_fingerprint if char.isalnum())[:16].lower()
    return f"{CA_CHANGE_ISSUE_PREFIX}{entry_id}_{token}"


def async_create_ca_change_issue(
        hass: HomeAssistant, config_entry, change: dict[str, Any]) -> str:
    """Publish a non-blocking notice for a changed broker CA."""
    issue = ca_change_issue_id(
        config_entry.entry_id, change["new_fingerprint"])
    registry = ir.async_get(hass)
    if registry.async_get_issue(DOMAIN, issue) is not None:
        return issue
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="ca_change_detected",
        translation_placeholders={
            key: str(value) for key, value in change.items()
        },
        data={**change, "entry_id": config_entry.entry_id},
    )
    return issue


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


class CAChangeRepairFlow(RepairsFlow):
    """Explain a CA change and let the user acknowledge or disable safely."""

    def __init__(self, entry_id: str, placeholders: dict[str, str]) -> None:
        self._entry_id = entry_id
        self._placeholders = placeholders

    async def async_step_init(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["verified", "not_recognized", "later"],
            description_placeholders=self._placeholders,
        )

    async def async_step_verified(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        return self.async_create_entry(data={})

    async def async_step_later(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        return self.async_abort(reason="remind_later")

    async def async_step_not_recognized(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        return self.async_show_menu(
            step_id="not_recognized",
            menu_options=["disable", "back"],
            description_placeholders=self._placeholders,
        )

    async def async_step_back(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_init()

    async def async_step_disable(
            self, user_input: dict | None = None
    ) -> data_entry_flow.FlowResult:
        try:
            await self.hass.config_entries.async_set_disabled_by(
                self._entry_id, ConfigEntryDisabler.USER)
        except (OperationNotAllowed, UnknownEntry):
            return self.async_abort(reason="cannot_disable")
        return self.async_create_entry(data={})


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
    if issue_id_.startswith(CA_CHANGE_ISSUE_PREFIX):
        return CAChangeRepairFlow(
            entry_id=str(data.get("entry_id") or ""),
            placeholders={
                key: str(value)
                for key, value in data.items()
                if key != "entry_id"
            },
        )
    return RemoveMissingDeviceRepairFlow(
        device_uuid=data.get("uuid", ""),
        name=data.get("name") or data.get("uuid", "device"),
    )
