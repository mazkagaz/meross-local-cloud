"""Sensors built from device profiles."""
from homeassistant.core import HomeAssistant

from .broker_profile_sensor import BrokerProfileSensor
from .common import BROKER_ADAPTER, DOMAIN, HA_SENSOR
from .profile_entities import async_setup_profile_entities


async def async_setup_entry(hass: HomeAssistant, config_entry,
                            async_add_entities):
    async_setup_profile_entities(
        hass, config_entry, HA_SENSOR, async_add_entities)

    adapter = hass.data.get(DOMAIN, {}).get(BROKER_ADAPTER)
    if adapter is not None:
        async_add_entities([BrokerProfileSensor(adapter)], True)


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass
