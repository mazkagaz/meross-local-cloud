"""Per-device profile update entities (D4, opt-in)."""
from homeassistant.core import HomeAssistant

from .profile_entities import async_setup_profile_updates


async def async_setup_entry(hass: HomeAssistant, config_entry,
                            async_add_entities):
    async_setup_profile_updates(hass, config_entry, async_add_entities)


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    pass
