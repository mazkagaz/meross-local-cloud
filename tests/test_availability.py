from types import SimpleNamespace
from unittest.mock import AsyncMock

from meross_iot.model.enums import Namespace, OnlineStatus

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meross_cloud import MerossDevice
from custom_components.meross_cloud.common import DOMAIN, MISSING_TRACKER

UUID = "mrs100-test"


def make_device(mqtt_status, http_status, http_present=True,
                last_update_success=True, last_http_status=None):
    device = SimpleNamespace(
        name="Test Shutter",
        type="mrs100",
        uuid=UUID,
        internal_id=UUID,
        channels=[SimpleNamespace(index=0, name="Main")],
        online_status=mqtt_status,
        register_push_notification_handler_coroutine=lambda cb: None,
        unregister_push_notification_handler_coroutine=lambda cb: None,
    )
    data = {}
    if http_present:
        data[UUID] = SimpleNamespace(online_status=http_status)
    coordinator = SimpleNamespace(
        data=data,
        last_update_success=last_update_success,
    )
    wrapper = MerossDevice(
        device=device,
        channel=0,
        device_list_coordinator=coordinator,
        platform="cover",
    )
    if last_http_status is not None:
        wrapper._last_http_state = SimpleNamespace(online_status=last_http_status)
    return wrapper


def test_stale_http_offline_does_not_hide_connected_device():
    wrapper = make_device(OnlineStatus.ONLINE, OnlineStatus.OFFLINE)
    assert wrapper.online is True
    assert wrapper.available is True


def test_stale_last_http_offline_does_not_hide_connected_device():
    wrapper = make_device(
        OnlineStatus.ONLINE, None, http_present=False,
        last_http_status=OnlineStatus.UNKNOWN,
    )
    assert wrapper.available is True


def test_http_poll_failure_does_not_hide_connected_device():
    wrapper = make_device(
        OnlineStatus.ONLINE, None,
        http_present=False, last_update_success=False,
    )
    assert wrapper.available is True


def test_http_online_keeps_entity_available_before_mqtt_connects():
    wrapper = make_device(OnlineStatus.UNKNOWN, OnlineStatus.ONLINE)
    assert wrapper.online is True


def test_entity_unavailable_when_every_source_is_offline():
    wrapper = make_device(
        OnlineStatus.OFFLINE, OnlineStatus.OFFLINE,
        last_http_status=OnlineStatus.OFFLINE,
    )
    assert wrapper.available is False


async def test_unbind_stops_tracking_and_removes_registries(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    wrapper = make_device(OnlineStatus.ONLINE, OnlineStatus.ONLINE)
    tracker = SimpleNamespace(async_forget=AsyncMock())
    hass.data[DOMAIN] = {
        MISSING_TRACKER: tracker,
        "ADDED_ENTITIES_IDS": {wrapper.unique_id},
    }
    wrapper.hass = hass
    wrapper.platform = SimpleNamespace(async_remove_entity=AsyncMock())
    wrapper.entity_id = "cover.test_shutter"
    wrapper.async_remove = AsyncMock()

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, UUID)},
        name="Test Shutter",
    )
    er.async_get(hass).async_get_or_create(
        domain="cover",
        platform=DOMAIN,
        unique_id=wrapper.unique_id,
        suggested_object_id="test_shutter",
        config_entry=entry,
        device_id=device.id,
    )

    await wrapper._async_push_notification_received(
        Namespace.CONTROL_UNBIND, {}, UUID)

    tracker.async_forget.assert_awaited_once_with(UUID)
    assert er.async_get(hass).async_get("cover.test_shutter") is None
    assert dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, UUID)}) is None
