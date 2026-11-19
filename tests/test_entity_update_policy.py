"""Entity update policy: P1 with a targeted bridge for shutters."""
import ast
from pathlib import Path

import pytest

PLATFORM_FILES = [
    "button.py",
    "climate.py",
    "humidifier.py",
    "light.py",
    "sensor.py",
    "switch.py",
]
# Cover and number keep update_before_add until D3's central scheduler
# replaces the per-entity updates and restores the initial shutter state.
BRIDGE_FILES = [
    "cover.py",
    "number.py",
]
COMPONENT = Path(__file__).parents[1] / "custom_components" / "meross_cloud"


def _platform_add_calls(filename):
    tree = ast.parse((COMPONENT / filename).read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        if name != "async_add_entities":
            continue
        if not node.args or not isinstance(node.args[0], (ast.Name, ast.Call)):
            continue
        calls.append(node)
    return calls


@pytest.mark.parametrize("filename", PLATFORM_FILES)
def test_platform_entities_do_not_update_on_add(filename):
    offenders = [
        node.lineno for node in _platform_add_calls(filename)
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
        and node.args[1].value is True
    ]
    assert not offenders, (
        f"{filename}: async_add_entities(..., True) at lines {offenders}")


@pytest.mark.parametrize("filename", BRIDGE_FILES)
def test_shutter_bridge_keeps_initial_update(filename):
    bridge_calls = [
        node for node in _platform_add_calls(filename)
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
        and node.args[1].value is True
    ]
    assert bridge_calls, (
        f"{filename}: expected the temporary update_before_add bridge")
