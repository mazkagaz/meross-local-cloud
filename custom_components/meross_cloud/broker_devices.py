"""Device discovery through the local broker API (D5 vendored path)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .broker_http import BrokerHttpClient

DEVICE_LIST_PATH = "/v1/Device/devList"


@dataclass(frozen=True)
class BrokerDeviceInfo:
    uuid: str
    name: str
    device_type: str
    sub_type: Optional[str] = None
    online: bool = False
    firmware: Optional[str] = None
    hardware: Optional[str] = None
    channels: Tuple[int, ...] = ()

    @property
    def dev_name(self) -> str:
        return self.name


def _channel_indexes(channels: Any) -> Tuple[int, ...]:
    if not isinstance(channels, list):
        return ()
    indexes = []
    for channel in channels:
        index = channel.get("channel") if isinstance(channel, dict) else None
        if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
            indexes.append(index)
    return tuple(indexes)


def parse_devices(payload: Any) -> List[BrokerDeviceInfo]:
    if not isinstance(payload, list):
        return []
    devices = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        uuid = item.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            continue
        devices.append(BrokerDeviceInfo(
            uuid=uuid,
            name=str(item.get("devName") or uuid),
            device_type=str(item.get("deviceType") or ""),
            sub_type=item.get("subType"),
            online=item.get("onlineStatus") == 1,
            firmware=item.get("fmwareVersion"),
            hardware=item.get("hdwareVersion"),
            channels=_channel_indexes(item.get("channels")),
        ))
    return devices


async def async_list_devices(http: BrokerHttpClient) -> List[BrokerDeviceInfo]:
    return parse_devices(await http.async_post(DEVICE_LIST_PATH))
