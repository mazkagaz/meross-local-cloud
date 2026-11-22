"""D5-c: drop the unique_ids created by the pre-historical beta."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_local_cloud import (
    _is_stale_profile_uid,
    async_prune_stale_profile_entities,
)
from custom_components.meross_local_cloud.common import DOMAIN


def test_stale_profile_uid_detection():
    assert _is_stale_profile_uid("switch:u1:0") is True
    assert _is_stale_profile_uid("sensor:sub1:0:temperature:°C") is True
    assert _is_stale_profile_uid("switch:#BASE:u1:0") is False
    assert _is_stale_profile_uid("meross_local_cloud:u1:update:profile") is False
    assert _is_stale_profile_uid("broker_profile_backend") is False
    assert _is_stale_profile_uid("other:u1:0") is False


async def test_prune_removes_only_pre_d5c_entities(hass):
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry1")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    keep = {
        "switch:#BASE:u1:0": "switch",
        "meross_local_cloud:u1:update:profile": "update",
        "broker_profile_backend": "sensor",
    }
    for unique_id, platform in {
            **keep, "switch:u1:0": "switch"}.items():
        registry.async_get_or_create(
            domain=platform, platform=DOMAIN, unique_id=unique_id,
            config_entry=entry,
            suggested_object_id=unique_id.replace(":", "_"))

    async_prune_stale_profile_entities(hass, entry)

    remaining = {
        item.unique_id
        for item in er.async_entries_for_config_entry(
            registry, entry.entry_id)
    }
    assert remaining == set(keep)
