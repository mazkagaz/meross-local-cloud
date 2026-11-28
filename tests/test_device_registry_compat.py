from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.meross_local_cloud.common import (
    device_via_info,
    get_device_by_identifier,
)


def test_uses_the_current_entry_scoped_api():
    current = object()
    old = Mock()
    registry = SimpleNamespace(
        async_get_device_by_identifier=Mock(return_value=current),
        async_get_device=old,
    )

    assert get_device_by_identifier(
        registry, ("meross_local_cloud", "u1"), "entry-1") is current
    registry.async_get_device_by_identifier.assert_called_once_with(
        ("meross_local_cloud", "u1"), "entry-1")
    old.assert_not_called()


def test_falls_back_to_the_legacy_identifier_api():
    legacy = object()
    registry = SimpleNamespace(
        async_get_device=Mock(return_value=legacy),
    )

    assert get_device_by_identifier(
        registry, ("meross_local_cloud", "u1"), "entry-1") is legacy
    registry.async_get_device.assert_called_once_with(
        identifiers={("meross_local_cloud", "u1")})


def test_via_device_uses_the_current_api():
    registry = SimpleNamespace(
        async_get_device_by_identifier=Mock(),
    )

    assert device_via_info(registry, "parent-id") == {
        "via_device_id": "parent-id"}


def test_via_device_falls_back_to_identifiers():
    registry = SimpleNamespace(
        async_get=Mock(return_value=SimpleNamespace(
            identifiers={("meross_local_cloud", "#BASE:u1")})),
    )

    assert device_via_info(registry, "parent-id") == {
        "via_device": ("meross_local_cloud", "#BASE:u1")}


def test_via_device_fallback_without_a_parent_is_empty():
    registry = SimpleNamespace(async_get=Mock(return_value=None))

    assert device_via_info(registry, "parent-id") == {}
