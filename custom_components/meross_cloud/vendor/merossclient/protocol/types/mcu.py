"""
A collection of typing definitions for payloads in Appliance.Mcu.*
"""
from __future__ import annotations

from . import TypedDict


class Firmware(TypedDict):
    """Appliance.Mcu.Firmware payload definition."""

    productId: str
    version: str
    type: str
