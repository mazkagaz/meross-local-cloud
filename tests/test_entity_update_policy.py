"""Entities must not trigger a device update when they are added."""
import ast
from pathlib import Path

import pytest

PLATFORM_FILES = [
    "button.py",
    "climate.py",
    "cover.py",
    "humidifier.py",
    "light.py",
    "number.py",
    "sensor.py",
    "switch.py",
]
COMPONENT = Path(__file__).parents[1] / "custom_components" / "meross_cloud"


@pytest.mark.parametrize("filename", PLATFORM_FILES)
def test_platform_entities_do_not_update_on_add(filename):
    tree = ast.parse((COMPONENT / filename).read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or \
                func.attr != "async_add_entities":
            continue
        # Only the platform entity lists are checked; the diagnostic probe
        # sensor is added separately and performs no device update.
        if not node.args or not isinstance(node.args[0], (ast.Name, ast.Call)):
            continue
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) \
                and node.args[1].value is True:
            offenders.append(node.lineno)

    assert not offenders, (
        f"{filename}: async_add_entities(..., True) at lines {offenders}")
