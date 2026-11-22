"""Binary sensors built from device profiles (D3, opt-in)."""
from homeassistant.core import HomeAssistant

from .common import HA_BINARY_SENSOR
from .profile_entities import async_setup_profile_entities


async def async_setup_entry(hass: HomeAssistant, config_entry,
                            async_add_entities):
    async_setup_profile_entities(
        hass, config_entry, HA_BINARY_SENSOR, async_add_entities)


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass
