"""D5 invariants: dependency inventory and registry identity formats."""
import json
import re
from pathlib import Path

from custom_components.meross_cloud.common import (
    HA_UPDATE,
    MEROSS_PLATFORMS,
    calculate_id,
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

_IMPORT = re.compile(r"^\s*(?:from|import)\s+meross_iot\b", re.MULTILINE)


def test_meross_iot_is_gone():
    offenders = set()
    for path in COMPONENT.rglob("*.py"):
        if "vendor" in path.parts:
            continue
        if _IMPORT.search(path.read_text()):
            offenders.add(str(path.relative_to(COMPONENT)))
    assert offenders == set()


def test_profile_layer_covers_every_entity_platform():
    covered = set(PLATFORM_CLASSES) | {HA_UPDATE}
    assert covered == set(MEROSS_PLATFORMS)


def test_manifest_and_changelog_versions_agree():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    changelog = (
        Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text()
    assert changelog.startswith(f"## {manifest['version']} ")


def test_dependency_is_paho_only_and_pinned():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["requirements"] == ["paho-mqtt==2.1.0"]


def test_historical_unique_ids_include_the_registry_base():
    top = calculate_id(
        "switch", device_internal_id("uuid"), 0)
    sub = calculate_id(
        "sensor", device_internal_id("hub", "sub"), 0,
        ["temperature", "°C"])
    assert top == "switch:#BASE:uuid:0"
    assert sub == "sensor:#BASE:hub#SUB:sub:0:temperature:°C"


def test_device_registry_identifiers_match_historical_format():
    assert device_internal_id("uuid") == "#BASE:uuid"
    assert device_internal_id("hub", "sub") == "#BASE:hub#SUB:sub"

    top = _device_info("uuid")
    sub = _device_info("hub", "sub")
    assert top["identifiers"] == {("meross_cloud", "#BASE:uuid")}
    assert sub["identifiers"] == {
        ("meross_cloud", "#BASE:hub#SUB:sub")}
    assert sub["via_device"] == ("meross_cloud", "#BASE:hub")
