from types import SimpleNamespace

from meross_iot.model.enums import OnlineStatus

from custom_components.meross_cloud import MerossDevice

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
