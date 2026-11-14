"""Appliance.RollerShutter.Adjust helpers shared by buttons and sensors.

meross_iot 0.4.9.2 has no ROLLER_SHUTTER_ADJUST namespace member, but its
manager accepts raw namespace strings. Incoming Adjust push notifications are
dropped by that library version, so status is obtained with polling GETs.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .common import DOMAIN

_LOGGER = logging.getLogger(__name__)

ADJUST_NAMESPACE = "Appliance.RollerShutter.Adjust"

ADJUST_VALUE_STOP = 0
ADJUST_VALUE_START = 1
ADJUST_VALUE_MANUAL_ONE = 2
ADJUST_VALUE_MANUAL_TWO = 3
ADJUST_VALUE_MANUAL_STOP = 4

ADJUST_STATUS_NAMES = {
    0: "success",
    1: "timeout",
    2: "motor_blocked",
    3: "failed_3",
    4: "failed_4",
    5: "failed_5",
    6: "failed_6",
}

DATA_KEY = "roller_shutter_adjust"
TASKS_KEY = "roller_shutter_adjust_tasks"

# The official app polls GET Adjust every 30 s after an initial 90 s delay.
MONITOR_INITIAL_DELAY = 90
MONITOR_INTERVAL = 15
MONITOR_DURATION = 120


def adjust_signal(device_uuid: str, channel: int) -> str:
    return f"{DOMAIN}_adjust_{device_uuid}_{channel}"


def adjust_status_name(status: Optional[int]) -> Optional[str]:
    if status is None:
        return None
    return ADJUST_STATUS_NAMES.get(int(status), f"failed_{int(status)}")


def get_adjust_status(hass: HomeAssistant, device_uuid: str, channel: int) -> Optional[dict]:
    store = hass.data.get(DOMAIN, {}).get(DATA_KEY, {})
    return store.get((device_uuid, channel))


def set_adjust_status(hass: HomeAssistant,
                      device_uuid: str,
                      channel: int,
                      name: str,
                      status: Optional[int] = None,
                      raw: Any = None) -> None:
    store = hass.data.setdefault(DOMAIN, {}).setdefault(DATA_KEY, {})
    store[(device_uuid, channel)] = {
        "name": name,
        "status": status,
        "raw": raw,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    async_dispatcher_send(hass, adjust_signal(device_uuid, channel))


async def async_send_adjust(device, channel: int, value: int, timeout: float = 15) -> Any:
    return await device._execute_command(
        method="SET",
        namespace=ADJUST_NAMESPACE,
        payload={"adjust": {"channel": channel, "value": value}},
        timeout=timeout,
    )


def _parse_adjust_response(response: Any, channel: int) -> Tuple[Optional[int], Any]:
    adjust = response.get("adjust") if isinstance(response, dict) else response
    if isinstance(adjust, str):
        try:
            adjust = json.loads(adjust)
        except ValueError:
            return None, None
    if isinstance(adjust, dict):
        adjust = [adjust]
    if not isinstance(adjust, list):
        return None, None
    for entry in adjust:
        if not isinstance(entry, dict):
            continue
        try:
            entry_channel = int(entry.get("channel"))
        except (TypeError, ValueError):
            continue
        if entry_channel != channel:
            continue
        status = entry.get("status")
        if status is None:
            return None, entry
        return int(status), entry
    return None, None


async def async_fetch_adjust(device, channel: int, timeout: float = 15) -> Tuple[Optional[int], Any]:
    response = await device._execute_command(
        method="GET",
        namespace=ADJUST_NAMESPACE,
        payload={"adjust": [{"channel": channel}]},
        timeout=timeout,
    )
    status, raw = _parse_adjust_response(response, channel)
    return status, raw


def async_start_monitor(hass: HomeAssistant, device, channel: int) -> None:
    tasks = hass.data.setdefault(DOMAIN, {}).setdefault(TASKS_KEY, {})
    key = (device.uuid, channel)
    previous = tasks.pop(key, None)
    if previous is not None:
        previous.cancel()

    async def _monitor() -> None:
        loop = asyncio.get_running_loop()
        last_status = None
        try:
            await asyncio.sleep(MONITOR_INITIAL_DELAY)
            deadline = loop.time() + MONITOR_DURATION
            while loop.time() <= deadline:
                try:
                    status, raw = await async_fetch_adjust(device, channel)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    _LOGGER.debug("Adjust status poll failed for %s channel %d",
                                  device.uuid, channel, exc_info=True)
                else:
                    if status is not None and status != last_status:
                        last_status = status
                        set_adjust_status(hass, device.uuid, channel,
                                          adjust_status_name(status), status, raw)
                await asyncio.sleep(MONITOR_INTERVAL)
            if last_status is None:
                set_adjust_status(hass, device.uuid, channel, "no_result")
        except asyncio.CancelledError:
            raise
        finally:
            if tasks.get(key) is asyncio.current_task():
                tasks.pop(key, None)

    tasks[key] = hass.async_create_task(_monitor())


def async_stop_monitor(hass: HomeAssistant, device_uuid: str, channel: int) -> None:
    tasks = hass.data.get(DOMAIN, {}).get(TASKS_KEY, {})
    task = tasks.pop((device_uuid, channel), None)
    if task is not None:
        task.cancel()
