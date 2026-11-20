"""D5-b: per-device availability fed by HTTP polls and MQTT pushes."""
from types import SimpleNamespace

from custom_components.meross_cloud.broker_adapter import BrokerProfileAdapter


def adapter(state="connected"):
    instance = BrokerProfileAdapter.__new__(BrokerProfileAdapter)
    instance.state = state
    instance.device_online = {}
    instance._listeners = []
    return instance


def test_devlist_poll_updates_availability_and_notifies():
    instance = adapter()
    calls = []
    instance.add_listener(lambda: calls.append("changed"))

    instance.async_update_devices([
        SimpleNamespace(uuid="u1", online=True),
        SimpleNamespace(uuid="u2", online=False),
    ])
    instance.async_update_devices([
        SimpleNamespace(uuid="u1", online=True),
        SimpleNamespace(uuid="u2", online=False),
    ])

    assert instance.device_online == {"u1": True, "u2": False}
    assert len(calls) == 1


def test_system_and_hub_online_pushes_update_availability():
    instance = adapter()

    instance._apply_online(
        "u1", "Appliance.System.Online", {"online": {"status": 2}})
    assert instance.device_online["u1"] is False

    instance._apply_online(
        "hub", "Appliance.Hub.Online", {"status": 1})
    assert instance.device_online["hub"] is True

    instance._apply_online("ignored", "Appliance.Control.Light", {})
    assert "ignored" not in instance.device_online


def test_unknown_devices_are_reported_for_reload():
    instance = adapter()
    instance.descriptors = {"u1": {}}

    assert instance.unknown_devices([
        SimpleNamespace(uuid="u1"), SimpleNamespace(uuid="u2")]) == {"u2"}


def test_availability_requires_a_connected_adapter():
    instance = adapter(state="starting")
    instance.device_online["u1"] = True

    assert instance.device_available("u1") is False
    instance.state = "connected"
    assert instance.device_available("u1") is True
    assert instance.device_available("unknown") is True
