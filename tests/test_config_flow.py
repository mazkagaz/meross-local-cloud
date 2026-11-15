import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.meross_cloud.common import DOMAIN
from custom_components.meross_cloud.config_flow import MerossFlowHandler


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_initial_flow_opens_local_configuration(hass, monkeypatch):
    async def fake_discover(self):
        return None, None

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", fake_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"


async def test_initial_flow_survives_discovery_failure(hass, monkeypatch):
    async def broken_discover(self):
        raise RuntimeError("mDNS unavailable")

    monkeypatch.setattr(MerossFlowHandler, "_discover_services", broken_discover)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure_manager"
    assert result["errors"]["base"] == "mdns_lookup_failed"
