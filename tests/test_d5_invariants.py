"""D5 invariants: dependency inventory and registry identity formats."""
import json
import re
from pathlib import Path

from custom_components.meross_cloud.common import (
    HA_UPDATE,
    MEROSS_PLATFORMS,
    device_internal_id,
)
from custom_components.meross_cloud.profile_entities import (
    PLATFORM_CLASSES,
    _device_info,
)

COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "meross_cloud"
)

# Files that still contain the legacy meross_iot path during D5-b. D5-d
# must empty this set when the dependency is removed.
LEGACY_MEROSS_IOT_FILES = {
    "__init__.py",
    "button.py",
    "calibration.py",
    "climate.py",
    "common.py",
    "cover.py",
    "humidifier.py",
    "light.py",
    "number.py",
    "patches.py",
    "sensor.py",
    "switch.py",
    "version.py",
    "diagnostics.py",
}

_IMPORT = re.compile(r"^\s*(?:from|import)\s+meross_iot\b", re.MULTILINE)


def test_meross_iot_imports_stay_in_the_legacy_allowlist():
    offenders = set()
    for path in COMPONENT.rglob("*.py"):
        if "vendor" in path.parts:
            continue
        text = path.read_text()
        if _IMPORT.search(text) and path.name not in LEGACY_MEROSS_IOT_FILES:
            offenders.add(str(path.relative_to(COMPONENT)))
    assert offenders == set()


def test_profile_layer_covers_every_entity_platform():
    covered = set(PLATFORM_CLASSES) | {HA_UPDATE}
    assert covered == set(MEROSS_PLATFORMS)


def test_legacy_dependency_remains_pinned():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    requirements = manifest.get("requirements", [])
    legacy = [item for item in requirements if item.startswith("meross_iot")]
    assert legacy in ([], ["meross_iot==0.4.9.2"])


def test_device_registry_identifiers_match_historical_format():
    assert device_internal_id("uuid") == "#BASE:uuid"
    assert device_internal_id("hub", "sub") == "#BASE:hub#SUB:sub"

    top = _device_info("uuid")
    sub = _device_info("hub", "sub")
    assert top["identifiers"] == {("meross_cloud", "#BASE:uuid")}
    assert sub["identifiers"] == {
        ("meross_cloud", "#BASE:hub#SUB:sub")}
    assert sub["via_device"] == ("meross_cloud", "#BASE:hub")
