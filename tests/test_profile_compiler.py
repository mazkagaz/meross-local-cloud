from pathlib import Path

import pytest
import yaml

from custom_components.meross_cloud.profiles.compiler import (
    ProfileCompiler,
    compile_profile,
)
from custom_components.meross_cloud.profiles.models import ProfileMeta

FIXTURES = Path(__file__).parent / "fixtures" / "profiles"
BROKER_PROFILES = (
    Path(__file__).resolve().parents[2]
    / "meross-local-broker"
    / "meross_local_broker"
    / "rootfs"
    / "opt"
    / "custom_broker"
    / "device_profiles"
)
TOGGLE_NS = "Appliance.Control.ToggleX"


def fixture_data(name):
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text())


def meta(data, digest=None):
    profile_id = data["profile"]["id"]
    return ProfileMeta(
        id=profile_id,
        version=data["profile"].get("version"),
        source="test",
        digest=digest,
        requires_engine=None,
        data=data,
    )


def doc(entities=None, payloads=None, quirks=None):
    data = {
        "schema_version": 2,
        "profile": {"id": "test.profile", "version": "1"},
        "match": {"type": ["mss310"]},
        "payloads": payloads if payloads is not None else {
            TOGGLE_NS: {
                "methods": ["GETACK", "PUSH"],
                "fields": {"channel": {"type": "integer"},
                           "onoff": {"type": "integer"}},
            },
        },
        "entities": entities if entities is not None else [],
    }
    if quirks is not None:
        data["quirks"] = quirks
    return data


def entity(key="switch", platform="switch", **overrides):
    item = {
        "key": key,
        "platform": platform,
        "channel": 0,
        "state": {
            "namespace": TOGGLE_NS,
            "channel": "$channel",
            "fields": {"onoff": "onoff"},
        },
        "commands": {
            "turn_on": {
                "namespace": TOGGLE_NS,
                "payload": {"channel": "$channel", "onoff": 1},
            },
        },
    }
    item.update(overrides)
    return item


def test_unknown_platform_is_ignored_with_a_warning():
    compiled = compile_profile(meta(doc(
        entities=[entity(platform="toaster")])))

    assert compiled.entities == {}
    assert compiled.errors == []
    assert any("unknown platform" in warning for warning in compiled.warnings)


def test_complex_platform_is_deferred_not_failed():
    compiled = compile_profile(meta(doc(
        entities=[entity(platform="climate")])))

    assert compiled.entities == {}
    assert compiled.errors == []
    assert any("deferred to D2.2.3" in warning
               for warning in compiled.warnings)


def test_missing_state_namespace_is_an_entity_error():
    compiled = compile_profile(meta(doc(
        entities=[entity(state={
            "namespace": "Appliance.Unknown",
            "fields": {"onoff": "onoff"},
        })])))

    assert compiled.entities == {}
    assert any("unknown state namespace" in error
               for error in compiled.errors)


def test_missing_command_namespace_is_an_entity_error():
    bad = entity(commands={
        "turn_on": {"namespace": "Appliance.Unknown", "payload": {}}})

    compiled = compile_profile(meta(doc(entities=[bad])))

    assert compiled.entities == {}
    assert any("unknown namespace" in error for error in compiled.errors)


@pytest.mark.parametrize("fields", [None, [], "onoff", {}])
def test_invalid_state_fields_are_refused(fields):
    compiled = compile_profile(meta(doc(
        entities=[entity(state={"namespace": TOGGLE_NS, "fields": fields})])))

    assert compiled.entities == {}
    assert any("state.fields" in error for error in compiled.errors)


@pytest.mark.parametrize("path", ["", "a..b", "a[-1]", "$value"])
def test_invalid_state_path_is_refused(path):
    compiled = compile_profile(meta(doc(
        entities=[entity(state={
            "namespace": TOGGLE_NS,
            "fields": {"onoff": path},
        })])))

    assert compiled.entities == {}
    assert any("invalid state path" in error for error in compiled.errors)


@pytest.mark.parametrize("channel", [-1, 1.5, True, "one"])
def test_invalid_entity_channel_is_refused(channel):
    compiled = compile_profile(meta(doc(
        entities=[entity(channel=channel)])))

    assert compiled.entities == {}
    assert any("channel" in error for error in compiled.errors)


@pytest.mark.parametrize("token", ["$other", "$channel_x", "$"])
def test_unknown_or_partial_command_token_is_refused(token):
    bad = entity(commands={
        "turn_on": {"namespace": TOGGLE_NS, "payload": {"value": token}}})

    compiled = compile_profile(meta(doc(entities=[bad])))

    assert compiled.entities == {}
    assert any("unsupported token" in error for error in compiled.errors)


def test_value_is_required_for_number_commands():
    payloads = {
        "Appliance.Control.Number": {"methods": ["SET"], "fields": {}},
    }
    missing = entity(
        key="missing", platform="number",
        state={"namespace": "Appliance.Control.Number",
               "fields": {"value": "value"}},
        commands={"set_value": {"namespace": "Appliance.Control.Number",
                                "payload": {"value": 3}}})
    provided = entity(
        key="provided", platform="number",
        state={"namespace": "Appliance.Control.Number",
               "fields": {"value": "value"}},
        commands={"set_value": {"namespace": "Appliance.Control.Number",
                                "payload": {"value": "$value"}}})

    compiled = compile_profile(meta(doc(
        entities=[missing, provided], payloads=payloads)))

    assert "missing" not in compiled.entities
    assert "provided" in compiled.entities
    assert any("$value is required" in error for error in compiled.errors)


def test_duplicate_entity_key_is_an_error():
    compiled = compile_profile(meta(doc(
        entities=[entity(), entity(platform="sensor")])))

    assert len(compiled.entities) == 1
    assert any("duplicate entity key" in error for error in compiled.errors)


def test_unknown_and_duplicate_quirks_are_errors():
    unknown = entity(quirks=[{"name": "nope"}])
    duplicate = entity(
        key="other",
        quirks=[{"name": "config_persist"}, {"name": "config_persist"}])

    compiled = compile_profile(meta(doc(entities=[unknown, duplicate])))

    assert compiled.entities == {}
    assert any("unknown quirk" in error for error in compiled.errors)
    assert any("duplicate quirk" in error for error in compiled.errors)


def test_unknown_root_quirk_is_a_profile_error():
    compiled = compile_profile(meta(doc(quirks=[{"name": "nope"}])))

    assert any("unknown root quirk" in error for error in compiled.errors)


def test_subdevice_entity_without_hub_template_is_an_error():
    compiled = compile_profile(meta(doc(
        entities=[entity(device="subdevice")])))

    assert compiled.entities == {}
    assert any("require a hub template" in error
               for error in compiled.errors)


def test_entity_errors_are_isolated():
    good = entity()
    bad = entity(key="broken", state={"namespace": TOGGLE_NS, "fields": {}})

    compiled = compile_profile(meta(doc(entities=[bad, good])))

    assert list(compiled.entities) == ["switch"]
    assert any("broken" in error for error in compiled.errors)


def test_unknown_method_is_ignored_instead_of_failing():
    payloads = {
        TOGGLE_NS: {"methods": ["GETACK", "FUTUREMETHOD"], "fields": {}},
    }

    compiled = compile_profile(meta(doc(
        entities=[], payloads=payloads)))

    assert compiled.namespaces[TOGGLE_NS].methods == ("GETACK",)
    assert any("unknown method" in warning
               for warning in compiled.warnings)


def test_polling_defaults():
    payloads = {
        "Appliance.RollerShutter.State": {
            "methods": ["GETACK", "SETACK", "PUSH"], "fields": {}},
        "Appliance.RollerShutter.Config": {
            "methods": ["SET", "SETACK"], "fields": {}},
    }

    compiled = compile_profile(meta(doc(entities=[], payloads=payloads)))

    state = compiled.namespaces["Appliance.RollerShutter.State"].polling
    config = compiled.namespaces["Appliance.RollerShutter.Config"].polling
    assert state.strategy == "default"
    assert state.period_s == 60
    assert state.push is True
    assert config.strategy == "once"
    assert config.push is False


def test_explicit_polling_is_kept():
    payloads = {
        TOGGLE_NS: {
            "methods": ["GETACK"],
            "fields": {},
            "polling": {"strategy": "smart", "period_s": 30,
                        "push": False, "response_size": 512},
        },
    }

    compiled = compile_profile(meta(doc(entities=[], payloads=payloads)))
    polling = compiled.namespaces[TOGGLE_NS].polling

    assert polling.strategy == "smart"
    assert polling.period_s == 30
    assert polling.response_size == 512


def test_lazy_compilation_cache_uses_id_version_and_digest():
    data = doc(entities=[entity()])
    compiler = ProfileCompiler()

    first = compiler.compile(meta(data, digest="h1"))
    second = compiler.compile(meta(data, digest="h1"))
    compiler.compile(meta(data, digest="h2"))
    changed = dict(data, profile={"id": "test.profile", "version": "2"})
    compiler.compile(meta(changed, digest="h1"))

    assert first is second
    assert compiler.cache_size == 3


@pytest.mark.parametrize("name,expected", [
    ("mrs100", {"cover", "open_duration", "close_duration",
                "start_calibration", "stop_calibration",
                "calibration_status"}),
    ("mss310", {"switch", "power", "voltage", "current"}),
    ("msl120", {"light"}),
])
def test_canonical_profiles_compile(name, expected):
    data = fixture_data(name)

    compiled = compile_profile(meta(data, digest="hash"))

    assert compiled.errors == []
    assert set(compiled.entities) == expected
    assert compiled.schema_version == 1


def test_canonical_profile_entities_carry_stable_ids():
    compiled = compile_profile(meta(fixture_data("mss310"), digest="hash"))

    assert compiled.entities["switch"].uid == "meross.mss310:switch"
    assert compiled.entities["power"].state.namespace == \
        "Appliance.Control.Electricity"


@pytest.mark.parametrize("name", ["mrs100", "mss310", "msl120"])
def test_fixtures_match_the_canonical_broker_profiles(name):
    canonical = BROKER_PROFILES / f"{name}.yaml"
    if not canonical.exists():
        pytest.skip("broker profiles are not checked out next to the repo")
    assert (FIXTURES / f"{name}.yaml").read_bytes() == canonical.read_bytes()
