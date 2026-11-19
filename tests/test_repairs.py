from types import SimpleNamespace

import pytest
from homeassistant.components import repairs as repairs_component
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud import repairs
from custom_components.meross_cloud.common import DOMAIN, MANAGER
from custom_components.meross_cloud.missing_devices import issue_id


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_confirm_removes_device_and_issue(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, repairs_component.DOMAIN, {})
    hass.data[repairs_component.DOMAIN]["platforms"] = {DOMAIN: repairs}

    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "u1")},
        name="Volet",
    )

    class FakeManager:
        def __init__(self):
            self.relinquished = []

        def find_devices(self, device_uuids=None):
            return [SimpleNamespace(internal_id="u1")]

        def relinquish_device(self, internal_id):
            self.relinquished.append(internal_id)

    manager = FakeManager()
    hass.data[DOMAIN] = {MANAGER: manager}

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id("u1"),
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="remove_missing_device",
        translation_placeholders={"name": "Volet", "uuid": "u1"},
        data={"uuid": "u1", "name": "Volet"},
    )

    flow_manager = hass.data[repairs_component.DOMAIN]["flow_manager"]
    result = await flow_manager.async_init(
        DOMAIN, context={"source": "user"},
        data={"issue_id": issue_id("u1")})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await flow_manager.async_configure(result["flow_id"], user_input={})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert manager.relinquished == ["u1"]
    assert registry.async_get_device(identifiers={(DOMAIN, "u1")}) is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id("u1")) is None


async def test_confirm_removes_device_absent_from_the_manager(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, repairs_component.DOMAIN, {})
    hass.data[repairs_component.DOMAIN]["platforms"] = {DOMAIN: repairs}

    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "#BASE:u1")},
        name="Volet",
    )

    class EmptyManager:
        def find_devices(self, device_uuids=None):
            return []

        def relinquish_device(self, internal_id):
            raise AssertionError("no device should be relinquished")

    hass.data[DOMAIN] = {MANAGER: EmptyManager()}

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id("u1"),
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="remove_missing_device",
        translation_placeholders={"name": "Volet", "uuid": "u1"},
        data={"uuid": "u1", "name": "Volet"},
    )

    flow_manager = hass.data[repairs_component.DOMAIN]["flow_manager"]
    result = await flow_manager.async_init(
        DOMAIN, context={"source": "user"},
        data={"issue_id": issue_id("u1")})
    result = await flow_manager.async_configure(result["flow_id"], user_input={})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert registry.async_get_device(
        identifiers={(DOMAIN, "#BASE:u1")}) is None
