import asyncio
import logging
from types import SimpleNamespace

import pytest
from homeassistant.helpers.entity_component import EntityComponent
from meross_iot.controller.mixins.roller_shutter import RollerShutterTimerMixin
from meross_iot.model.enums import OnlineStatus

from custom_components.meross_cloud import calibration
from custom_components.meross_cloud.button import async_setup_entry as setup_buttons
from custom_components.meross_cloud.common import (
    DOMAIN, MANAGER, DEVICE_LIST_COORDINATOR,
)
from custom_components.meross_cloud.sensor import async_setup_entry as setup_sensors
from custom_components.meross_cloud.cover import async_setup_entry as setup_covers

_LOGGER = logging.getLogger(__name__)


class FakeShutter(RollerShutterTimerMixin):
    def __init__(self):
        self.uuid = "mrs100-test"
        self.internal_id = "mrs100-test"
        self.name = "Test Shutter"
        self.type = "mrs100"
        self.channels = [SimpleNamespace(index=0, name="Main", type=None, is_master_channel=True)]
        self.calls = []
        self.next_status = 0

    async def async_update(self):
        pass

    def check_full_update_done(self):
        return True

    def get_position(self, channel=0):
        return 100

    def get_status(self, channel=0):
        from meross_iot.model.enums import RollerShutterState
        return RollerShutterState.OPEN

    def register_push_notification_handler_coroutine(self, coro):
        pass

    def unregister_push_notification_handler_coroutine(self, coro):
        pass

    async def _execute_command(self, method, namespace, payload, timeout=None):
        self.calls.append({
            "method": method,
            "namespace": namespace,
            "payload": payload,
            "timeout": timeout,
        })
        if method == "GET":
            channel = payload["adjust"][0]["channel"]
            if self.next_status is None:
                return {"adjust": []}
            return {"adjust": [{"channel": channel, "status": self.next_status}]}
        return {"adjust": payload.get("adjust")}


class FakeCoordinator:
    def __init__(self, device_uuid):
        self.data = {device_uuid: SimpleNamespace(online_status=OnlineStatus.ONLINE)}
        self.last_update_success = True

    def async_add_listener(self, callback):
        return lambda: None


class FakeManager:
    def __init__(self, device):
        self.device = device

    def find_devices(self, device_class=None, **kwargs):
        if device_class:
            return [self.device] if any(isinstance(self.device, c) for c in device_class) else []
        return [self.device]


@pytest.fixture
async def runtime(hass):
    device = FakeShutter()
    hass.data[DOMAIN] = {
        MANAGER: FakeManager(device),
        DEVICE_LIST_COORDINATOR: FakeCoordinator(device.uuid),
        "ADDED_ENTITIES_IDS": set(),
    }

    sensor_component = EntityComponent(_LOGGER, "sensor", hass)

    def add_sensors(entities, update_before_add=False):
        hass.async_create_task(sensor_component.async_add_entities(entities, update_before_add=update_before_add))

    await setup_sensors(hass, None, add_sensors)

    button_component = EntityComponent(_LOGGER, "button", hass)

    def add_buttons(entities, update_before_add=False):
        hass.async_create_task(button_component.async_add_entities(entities, update_before_add=update_before_add))

    await setup_buttons(hass, None, add_buttons)
    await hass.async_block_till_done()
    await asyncio.sleep(0.02)
    await hass.async_block_till_done()

    return SimpleNamespace(
        hass=hass,
        device=device,
        sensor=list(sensor_component.entities)[0],
        start=next(b for b in button_component.entities if b._action == "calibrate"),
        stop=next(b for b in button_component.entities if b._action == "stop_calibration"),
    )


async def test_initial_status_is_success(runtime):
    assert runtime.sensor.state == "success"
    assert runtime.sensor.extra_state_attributes["status_code"] == 0
    assert runtime.sensor.extra_state_attributes["channel"] == 0


@pytest.mark.parametrize("code,name", [
    (0, "success"), (1, "timeout"), (2, "motor_blocked"),
    (3, "failed_3"), (4, "failed_4"), (5, "failed_5"), (6, "failed_6"),
])
async def test_status_mapping(hass, runtime, code, name):
    runtime.device.next_status = code
    await runtime.sensor._async_refresh_adjust()
    await hass.async_block_till_done()
    assert runtime.sensor.state == name
    assert runtime.sensor.extra_state_attributes["status_code"] == code


async def test_start_calibration_sets_in_progress(hass, runtime, monkeypatch):
    monkeypatch.setattr(calibration, "MONITOR_INITIAL_DELAY", 5)
    monkeypatch.setattr(calibration, "MONITOR_INTERVAL", 1)
    monkeypatch.setattr(calibration, "MONITOR_DURATION", 1)

    runtime.device.next_status = None
    await runtime.start.async_press()
    await asyncio.sleep(0)
    assert runtime.sensor.state == "in_progress"

    call = runtime.device.calls[-1]
    assert call["method"] == "SET"
    assert call["namespace"] == "Appliance.RollerShutter.Adjust"
    assert call["payload"] == {"adjust": {"channel": 0, "value": 1}}

    # Cancels the pending monitor task.
    await runtime.stop.async_press()
    await asyncio.sleep(0)


async def test_monitor_reports_success(hass, runtime, monkeypatch):
    monkeypatch.setattr(calibration, "MONITOR_INITIAL_DELAY", 0)
    monkeypatch.setattr(calibration, "MONITOR_INTERVAL", 0.01)
    monkeypatch.setattr(calibration, "MONITOR_DURATION", 0.1)

    runtime.device.next_status = 0
    await runtime.start.async_press()
    await hass.async_block_till_done()
    assert runtime.sensor.state == "success"


async def test_stop_calibration(hass, runtime):
    await runtime.stop.async_press()
    await hass.async_block_till_done()
    call = runtime.device.calls[-1]
    assert call["method"] == "SET"
    assert call["payload"] == {"adjust": {"channel": 0, "value": 0}}
    assert runtime.sensor.state == "stopped"


async def test_no_result_when_device_reports_nothing(hass, runtime, monkeypatch):
    monkeypatch.setattr(calibration, "MONITOR_INITIAL_DELAY", 0)
    monkeypatch.setattr(calibration, "MONITOR_INTERVAL", 0.01)
    monkeypatch.setattr(calibration, "MONITOR_DURATION", 0.05)

    runtime.device.next_status = None
    await runtime.start.async_press()
    await asyncio.sleep(0.15)
    await hass.async_block_till_done()
    assert runtime.sensor.state == "no_result"


async def test_cover_entity_is_created(hass):
    device = FakeShutter()
    hass.data[DOMAIN] = {
        MANAGER: FakeManager(device),
        DEVICE_LIST_COORDINATOR: FakeCoordinator(device.uuid),
        "ADDED_ENTITIES_IDS": set(),
    }

    from homeassistant.components.cover import CoverEntityFeature
    import logging
    from homeassistant.helpers.entity_component import EntityComponent

    component = EntityComponent(logging.getLogger(__name__), "cover", hass)

    def add_covers(entities, update_before_add=False):
        hass.async_create_task(component.async_add_entities(entities, update_before_add=update_before_add))

    await setup_covers(hass, None, add_covers)
    await hass.async_block_till_done()

    covers = list(component.entities)
    assert len(covers) == 1
    assert covers[0].supported_features & CoverEntityFeature.OPEN
    assert covers[0].supported_features & CoverEntityFeature.CLOSE


async def test_cover_and_sensor_support_missing_channel_list(hass):
    device = FakeShutter()
    device.channels = None
    hass.data[DOMAIN] = {
        MANAGER: FakeManager(device),
        DEVICE_LIST_COORDINATOR: FakeCoordinator(device.uuid),
        "ADDED_ENTITIES_IDS": set(),
    }

    import logging
    from homeassistant.helpers.entity_component import EntityComponent

    cover_component = EntityComponent(logging.getLogger(__name__), "cover", hass)
    sensor_component = EntityComponent(logging.getLogger(__name__), "sensor", hass)

    def add_covers(entities, update_before_add=False):
        hass.async_create_task(cover_component.async_add_entities(entities, update_before_add=update_before_add))

    def add_sensors(entities, update_before_add=False):
        hass.async_create_task(sensor_component.async_add_entities(entities, update_before_add=update_before_add))

    await setup_covers(hass, None, add_covers)
    await setup_sensors(hass, None, add_sensors)
    await hass.async_block_till_done()

    assert len(list(cover_component.entities)) == 1
    assert len(list(sensor_component.entities)) == 1
