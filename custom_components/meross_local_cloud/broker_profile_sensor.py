"""Diagnostic sensor for the opt-in broker profile backend."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .broker_adapter import BrokerProfileAdapter


class BrokerProfileSensor(SensorEntity):
    """Expose the state of the D1 profile-backend probe."""

    _attr_name = "Broker profile backend"
    _attr_unique_id = "broker_profile_backend"
    _attr_icon = "mdi:file-code-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True

    def __init__(self, adapter: BrokerProfileAdapter) -> None:
        self._adapter = adapter

    @property
    def native_value(self) -> str:
        return self._adapter.summary()["state"]

    @property
    def extra_state_attributes(self) -> dict:
        return self._adapter.summary()
