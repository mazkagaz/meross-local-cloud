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


def doc(entities=None, payloads=None, quirks=None, subdevices=None,
        match=None):
    data = {
        "schema_version": 2,
        "profile": {"id": "test.profile", "version": "1"},
        "match": match or {"type": ["mss310"]},
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
    if subdevices is not None:
        data["subdevices"] = subdevices
    return data


SUBDEVICE_NS = "Appliance.Hub.Sensor.TempHum"


def subdevice(types=("ms100",), entities=None, payloads=None, name=None):
    template = {
        "match": {"type": list(types)},
        "entities": entities if entities is not None else [],
    }
    if payloads is not None:
        template["payloads"] = payloads
    if name is not None:
        template["name"] = name
    return template


def sub_entity(key="temperature", **overrides):
    item = {
        "key": key,
        "platform": "sensor",
        "state": {
            "namespace": SUBDEVICE_NS,
            "fields": {"value": "temperature"},
        },
    }
    item.update(overrides)
    return item


def subdevice_payloads():
    return {
        SUBDEVICE_NS: {"methods": ["GETACK", "PUSH"], "fields": {}},
    }


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


@pytest.mark.parametrize("platform", ["climate", "fan"])
def test_climate_and_fan_require_capabilities(platform):
    compiled = compile_profile(meta(doc(
        entities=[entity(platform=platform)])))

    assert compiled.entities == {}
    assert any("requires capabilities" in error
               for error in compiled.errors)


@pytest.mark.parametrize("platform", ["climate", "fan"])
def test_climate_and_fan_compile_with_capabilities(platform):
    capabilities = {"features": ["target_temperature"]}
    compiled = compile_profile(meta(doc(
        entities=[entity(platform=platform, capabilities=capabilities)])))

    assert compiled.errors == []
    assert compiled.entities["switch"].platform == platform
    assert compiled.entities["switch"].capabilities == capabilities


@pytest.mark.parametrize("platform", [
    "humidifier", "calendar", "media_player", "siren", "update",
])
def test_other_complex_platforms_compile(platform):
    compiled = compile_profile(meta(doc(
        entities=[entity(platform=platform)])))

    assert compiled.errors == []
    assert compiled.entities["switch"].platform == platform


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


@pytest.mark.parametrize("channel", [-1, 1.5, True, "one", "$channel"])
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


@pytest.mark.parametrize("platform,command", [
    ("select", "set_option"),
    ("light", "set_brightness"),
    ("light", "set_rgb"),
    ("climate", "set_temperature"),
    ("fan", "set_speed"),
])
def test_value_is_required_for_value_commands(platform, command):
    capabilities = None
    if platform == "climate":
        capabilities = {"hvac_modes": ["off"]}
    elif platform == "fan":
        capabilities = {"fan_modes": ["auto"]}
    extra = {"capabilities": capabilities} if capabilities else {}

    compiled = compile_profile(meta(doc(entities=[entity(
        platform=platform,
        commands={command: {"namespace": TOGGLE_NS,
                            "payload": {"value": 3}}},
        **extra,
    )])))

    assert compiled.entities == {}
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


def hub_doc(subdevices):
    return doc(
        match={"kind": "hub", "type": ["msh300"]},
        payloads={},
        subdevices=subdevices,
    )


def test_hub_profile_compiles_subdevice_template():
    compiled = compile_profile(meta(hub_doc([subdevice(
        entities=[sub_entity()], payloads=subdevice_payloads())])))

    assert compiled.errors == []
    assert len(compiled.subdevices) == 1
    template = compiled.subdevices[0]
    assert template.uid == "test.profile:subdevice:0"
    assert template.match == {"type": ["ms100"]}
    assert set(template.entities) == {"temperature"}


def test_subdevice_entities_default_to_subdevice():
    compiled = compile_profile(meta(hub_doc([subdevice(
        entities=[sub_entity()], payloads=subdevice_payloads())])))

    entity = compiled.subdevices[0].entities["temperature"]
    assert entity.device == "subdevice"
    assert entity.uid == "test.profile:subdevice:0:temperature"


def test_template_entities_cannot_target_the_hub():
    compiled = compile_profile(meta(hub_doc([subdevice(
        entities=[sub_entity(device="hub")],
        payloads=subdevice_payloads())])))

    assert compiled.subdevices[0].entities == {}
    assert any("must use device: subdevice" in error
               for error in compiled.errors)


def test_subdevice_template_requires_a_match_type():
    compiled = compile_profile(meta(hub_doc([{"entities": []}])))

    assert compiled.subdevices == ()
    assert any("match.type" in error for error in compiled.errors)


def test_subdevice_entity_keys_may_repeat_across_templates():
    entity_one = sub_entity()
    entity_two = sub_entity(key="temperature", name="Second")
    compiled = compile_profile(meta(hub_doc([
        subdevice(types=("ms100",), entities=[entity_one],
                  payloads=subdevice_payloads()),
        subdevice(types=("ms101",), entities=[entity_two],
                  payloads=subdevice_payloads()),
    ])))

    assert compiled.errors == []
    assert len(compiled.subdevices) == 2
    assert compiled.subdevices[1].entities["temperature"].name == "Second"


def test_subdevice_namespace_must_be_declared_in_the_template():
    compiled = compile_profile(meta(hub_doc([subdevice(
        entities=[sub_entity()])])))

    assert compiled.subdevices[0].entities == {}
    assert any("unknown state namespace" in error
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


@pytest.mark.parametrize("key", ["BadKey", "with-dash", "", 5])
def test_invalid_entity_key_is_refused(key):
    compiled = compile_profile(meta(doc(entities=[entity(key=key)])))

    assert compiled.entities == {}
    assert any("invalid entity key" in error for error in compiled.errors)


def test_non_string_state_property_is_refused():
    compiled = compile_profile(meta(doc(entities=[entity(state={
        "namespace": TOGGLE_NS,
        "fields": {1: "onoff"},
    })])))

    assert compiled.entities == {}
    assert any("invalid state path" in error for error in compiled.errors)


def test_non_string_namespace_name_is_refused():
    compiled = compile_profile(meta(doc(
        payloads={5: {"methods": ["GETACK"]}})))

    assert compiled.namespaces == {}
    assert any("malformed declaration" in error
               for error in compiled.errors)


def test_non_object_payloads_is_an_error():
    compiled = compile_profile(meta(doc(payloads=[])))

    assert compiled.namespaces == {}
    assert any("payloads must be an object" in error
               for error in compiled.errors)


@pytest.mark.parametrize("methods", [None, [], "GET", [1], [None]])
def test_invalid_methods_are_errors(methods):
    compiled = compile_profile(meta(doc(
        payloads={TOGGLE_NS: {"methods": methods}})))

    assert TOGGLE_NS not in compiled.namespaces
    assert any("methods must be" in error for error in compiled.errors)


@pytest.mark.parametrize("polling,expected", [
    ("bad", "polling must be an object"),
    ({"period_s": -1}, "invalid polling period_s"),
    ({"period_s": "60"}, "invalid polling period_s"),
    ({"push": "yes"}, "push must be a boolean"),
    ({"response_size": -1}, "invalid polling response_size"),
    ({"response_size": 1.5}, "invalid polling response_size"),
])
def test_invalid_polling_is_reported_and_defaulted(polling, expected):
    compiled = compile_profile(meta(doc(
        payloads={TOGGLE_NS: {"methods": ["GETACK"], "polling": polling}})))

    assert any(expected in error for error in compiled.errors)
    assert compiled.namespaces[TOGGLE_NS].polling.period_s == 60


def test_unknown_polling_strategy_falls_back_with_a_warning():
    compiled = compile_profile(meta(doc(
        payloads={TOGGLE_NS: {
            "methods": ["GETACK"],
            "polling": {"strategy": "future_strategy"},
        }})))

    assert compiled.errors == []
    assert any("unknown polling strategy" in warning
               for warning in compiled.warnings)
    assert compiled.namespaces[TOGGLE_NS].polling.strategy == "default"


def test_namespace_fields_must_be_an_object():
    compiled = compile_profile(meta(doc(
        payloads={TOGGLE_NS: {"methods": ["GETACK"], "fields": []}})))

    assert any("fields must be an object" in error
               for error in compiled.errors)


@pytest.mark.parametrize("digest,expected", [
    (5, "digest must be a path"),
    ("a..b", "invalid digest"),
])
def test_invalid_namespace_digest_is_an_error(digest, expected):
    compiled = compile_profile(meta(doc(
        payloads={TOGGLE_NS: {"methods": ["GETACK"], "digest": digest}})))

    assert any(expected in error for error in compiled.errors)


def test_entities_must_be_a_list():
    data = doc()
    data["entities"] = "nope"

    compiled = compile_profile(meta(data))

    assert any("entities must be a list" in error
               for error in compiled.errors)


def test_malformed_entity_is_reported():
    compiled = compile_profile(meta(doc(entities=["nope"])))

    assert compiled.entities == {}
    assert any("malformed entity" in error for error in compiled.errors)


@pytest.mark.parametrize("channel", [-1, 1.5, True, "$other", "1"])
def test_invalid_state_channel_is_refused(channel):
    compiled = compile_profile(meta(doc(entities=[entity(state={
        "namespace": TOGGLE_NS,
        "channel": channel,
        "fields": {"onoff": "onoff"},
    })])))

    assert compiled.entities == {}
    assert any("state channel" in error for error in compiled.errors)


def test_state_channel_token_requires_an_entity_channel():
    compiled = compile_profile(meta(doc(entities=[entity(
        channel=None,
        state={"namespace": TOGGLE_NS, "channel": "$channel",
               "fields": {"onoff": "onoff"}},
    )])))

    assert compiled.entities == {}
    assert any("$channel used without an entity channel" in error
               for error in compiled.errors)


@pytest.mark.parametrize("digest,expected", [
    (5, "state.digest must be a path"),
    ("a..b", "invalid state digest"),
])
def test_invalid_state_digest_is_an_error(digest, expected):
    compiled = compile_profile(meta(doc(entities=[entity(state={
        "namespace": TOGGLE_NS,
        "fields": {"onoff": "onoff"},
        "digest": digest,
    })])))

    assert compiled.entities == {}
    assert any(expected in error for error in compiled.errors)


def test_per_field_scale_and_offset_are_compiled():
    compiled = compile_profile(meta(doc(entities=[entity(state={
        "namespace": TOGGLE_NS,
        "fields": {"onoff": {"path": "togglex[0].onoff",
                             "scale": 0.1, "offset": 2}},
    })])))

    field = compiled.entities["switch"].state.fields["onoff"]
    assert field.path == "togglex[0].onoff"
    assert field.scale == 0.1
    assert field.offset == 2


@pytest.mark.parametrize("key", ["scale", "offset"])
def test_invalid_per_field_scale_is_an_error(key):
    compiled = compile_profile(meta(doc(entities=[entity(state={
        "namespace": TOGGLE_NS,
        "fields": {"onoff": {"path": "togglex[0].onoff", key: "x"}},
    })])))

    assert compiled.entities == {}
    assert any(key in error for error in compiled.errors)


def test_invalid_state_scale_is_an_error():
    compiled = compile_profile(meta(doc(entities=[entity(state={
        "namespace": TOGGLE_NS,
        "fields": {"onoff": "onoff"},
        "scale": "x",
    })])))

    assert compiled.entities == {}
    assert any("state.scale must be a number" in error
               for error in compiled.errors)


@pytest.mark.parametrize("commands,expected", [
    ([], "commands must be an object"),
    ({"turn_on": "x"}, "malformed command"),
    ({"turn_on": {"namespace": TOGGLE_NS, "payload": []}},
     "payload must be an object"),
    ({"turn_on": {"namespace": TOGGLE_NS, "payload": {"onoff": 1},
                  "value_scale": "x"}}, "value_scale must be a number"),
])
def test_invalid_commands_are_errors(commands, expected):
    compiled = compile_profile(meta(doc(
        entities=[entity(commands=commands)])))

    assert compiled.entities == {}
    assert any(expected in error for error in compiled.errors)


def test_command_channel_token_requires_an_entity_channel():
    compiled = compile_profile(meta(doc(entities=[entity(
        channel=None,
        commands={"turn_on": {"namespace": TOGGLE_NS,
                              "payload": {"channel": "$channel"}}},
    )])))

    assert compiled.entities == {}
    assert any("$channel used without an entity channel" in error
               for error in compiled.errors)


@pytest.mark.parametrize("field", [
    "name", "unit", "device_class", "entity_category",
])
def test_invalid_string_attributes_are_errors(field):
    compiled = compile_profile(meta(doc(
        entities=[entity(**{field: 5})])))

    assert compiled.entities == {}
    assert any(f"{field} must be a string" in error
               for error in compiled.errors)


def test_number_range_is_compiled():
    compiled = compile_profile(meta(doc(entities=[entity(
        key="level", platform="number",
        min_value=10, max_value=120, step=1,
        commands={"set_value": {"namespace": TOGGLE_NS,
                                "payload": {"value": "$value"}}})])))

    spec = compiled.entities["level"]
    assert spec.min_value == 10
    assert spec.max_value == 120
    assert spec.step == 1


@pytest.mark.parametrize("field", ["min_value", "max_value", "step"])
def test_invalid_numeric_attributes_are_errors(field):
    compiled = compile_profile(meta(doc(entities=[entity(
        **{field: "x"})])))

    assert compiled.entities == {}
    assert any(f"{field} must be a number" in error
               for error in compiled.errors)


def test_legacy_classifiers_are_compiled():
    compiled = compile_profile(meta(doc(entities=[entity(
        legacy_classifiers=["power", "W"])])))

    assert compiled.entities["switch"].legacy_classifiers == ("power", "W")


def test_invalid_legacy_classifiers_are_errors():
    compiled = compile_profile(meta(doc(entities=[entity(
        legacy_classifiers=[1])])))

    assert compiled.entities == {}
    assert any("legacy_classifiers" in error for error in compiled.errors)


def test_capabilities_must_be_an_object():
    compiled = compile_profile(meta(doc(
        entities=[entity(capabilities=[])])))

    assert compiled.entities == {}
    assert any("capabilities must be an object" in error
               for error in compiled.errors)


def test_quirks_must_be_a_list():
    compiled = compile_profile(meta(doc(entities=[entity(quirks="bad")])))

    assert compiled.entities == {}
    assert any("quirks must be a list" in error for error in compiled.errors)


def test_quirk_params_must_be_an_object():
    compiled = compile_profile(meta(doc(entities=[entity(
        quirks=[{"name": "config_persist", "params": []}])])))

    assert compiled.entities == {}
    assert any("params must be an object" in error
               for error in compiled.errors)


def test_malformed_subdevice_template_is_reported():
    compiled = compile_profile(meta(hub_doc(["nope"])))

    assert compiled.subdevices == ()
    assert any("malformed template" in error for error in compiled.errors)


def test_subdevice_template_name_must_be_a_string():
    template = subdevice()
    template["name"] = 5

    compiled = compile_profile(meta(hub_doc([template])))

    assert compiled.subdevices[0].name is None
    assert any("name must be a string" in error
               for error in compiled.errors)


def test_subdevice_template_entities_must_be_a_list():
    template = subdevice()
    template["entities"] = "nope"

    compiled = compile_profile(meta(hub_doc([template])))

    assert any("entities must be a list" in error
               for error in compiled.errors)


def test_subdevice_template_quirks_are_validated():
    template = subdevice()
    template["quirks"] = [{"name": "nope"}]

    compiled = compile_profile(meta(hub_doc([template])))

    assert any("unknown root quirk" in error for error in compiled.errors)


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
    ("msh300", {"online"}),
    ("mts200", {"climate"}),
    ("mfc", {"fan"}),
    ("mss", {"switch"}),
    ("msl", {"light"}),
    ("mrs", {"cover"}),
    ("mss5", {"light"}),
    ("mod", {"spray", "light"}),
])
def test_canonical_profiles_compile(name, expected):
    data = fixture_data(name)

    compiled = compile_profile(meta(data, digest="hash"))

    assert compiled.errors == []
    assert set(compiled.entities) == expected
    assert compiled.schema_version == data["schema_version"]
    assert compiled.description == data["profile"].get("description")


def test_hub_pilot_templates_compile_with_id_commands():
    data = fixture_data("msh300")

    compiled = compile_profile(meta(data, digest="hash"))

    assert compiled.errors == []
    templates = {template.name: template for template in compiled.subdevices}
    assert set(templates) == {"ms100", "ms130", "mts100"}
    assert set(templates["ms100"].entities) == {
        "temperature", "humidity", "voltage"}
    assert set(templates["ms130"].entities) == {"temperature", "humidity"}
    climate = templates["mts100"].entities["climate"]
    assert climate.platform == "climate"
    assert climate.commands["set_temperature"].payload == {
        "temperature": [{"id": "$id", "currentSet": "$value"}]}


def test_id_token_is_refused_outside_a_subdevice_template():
    compiled = compile_profile(meta(doc(entities=[entity(commands={
        "turn_on": {"namespace": TOGGLE_NS,
                    "payload": {"id": "$id", "onoff": 1}}})])))

    assert compiled.entities == {}
    assert any("$id is only valid in a subdevice template" in error
               for error in compiled.errors)


def test_canonical_profile_entities_carry_stable_ids():
    compiled = compile_profile(meta(fixture_data("mss310"), digest="hash"))

    assert compiled.entities["switch"].uid == "meross.mss310:switch"
    assert compiled.entities["power"].state.namespace == \
        "Appliance.Control.Electricity"


@pytest.mark.parametrize("name", [
    "mrs100", "mss310", "msl120", "msh300", "mts200", "mfc",
    "mss", "msl", "mrs", "mss5", "mod",
])
def test_fixtures_match_the_canonical_broker_profiles(name):
    canonical = BROKER_PROFILES / f"{name}.yaml"
    if not canonical.exists():
        pytest.skip("broker profiles are not checked out next to the repo")
    assert (FIXTURES / f"{name}.yaml").read_bytes() == canonical.read_bytes()
