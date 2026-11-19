import logging

from custom_components.meross_cloud.profiles.match import (
    MatchContext,
    match_candidates,
    match_profile,
    normalize_mac,
)
from custom_components.meross_cloud.profiles.models import ProfileMeta
from custom_components.meross_cloud.profiles.registry import ProfileRegistry


def profile(profile_id, types=("mss310",), *, sub_type=None, abilities=None,
            mac_prefix=None, kind=None):
    match = {"type": list(types)}
    if sub_type is not None:
        match["sub_type"] = list(sub_type)
    if abilities is not None:
        match["abilities"] = abilities
    if mac_prefix is not None:
        match["mac_prefix"] = list(mac_prefix)
    if kind is not None:
        match["kind"] = kind
    return {
        "id": profile_id,
        "version": "1",
        "profile": {
            "schema_version": 2,
            "profile": {"id": profile_id, "version": "1"},
            "match": match,
            "payloads": {},
            "entities": [],
        },
    }


def registry(*entries):
    return ProfileRegistry.from_catalog({
        "schema_version": 2,
        "revision": "rev1",
        "profiles": list(entries),
    })


def context(**kwargs):
    kwargs.setdefault("abilities", frozenset())
    return MatchContext(**kwargs)


def test_no_profile_means_unmatched():
    result = match_profile(registry(profile("a")), context(type="abc"))

    assert result.profile is None
    assert result.candidates == ()


def test_exact_type_with_subtype_and_mac_wins():
    result = match_profile(
        registry(
            profile("plain", sub_type=["un"]),
            profile("mac", sub_type=["un"], mac_prefix=["AABBCC"]),
        ),
        context(type="mss310", sub_type="un",
                mac="aa:bb:cc:dd:ee:ff"),
    )

    assert result.profile.id == "mac"
    assert result.score[0] == 5
    assert result.ambiguous is False


def test_exact_subtype_wins_over_abilities():
    result = match_profile(
        registry(
            profile("ability", abilities={
                "all": ["Appliance.Control.ToggleX"]}),
            profile("subtype", sub_type=["un"]),
        ),
        context(type="mss310", sub_type="un",
                abilities=frozenset({"Appliance.Control.ToggleX"})),
    )

    assert result.profile.id == "subtype"


def test_exact_type_wins_over_prefix():
    result = match_profile(
        registry(profile("prefix", types=("mss31",)), profile("exact")),
        context(type="mss310"),
    )

    assert result.profile.id == "exact"


def test_longest_prefix_wins_between_prefixes():
    result = match_profile(
        registry(
            profile("short", types=("mss3",)),
            profile("long", types=("mss31",)),
        ),
        context(type="mss310"),
    )

    assert result.profile.id == "long"


def test_prefix_does_not_match_unrelated_model():
    result = match_profile(
        registry(profile("mss310")), context(type="mss311"))

    assert result.profile is None


def test_generic_type_is_the_last_resort():
    result = match_profile(
        registry(profile("generic", types=("*",)),
                 profile("prefix", types=("mss",))),
        context(type="mss310"),
    )

    assert result.profile.id == "prefix"


def test_equal_scores_are_resolved_by_id_and_reported(caplog):
    caplog.set_level(logging.WARNING)
    result = match_profile(
        registry(profile("b"), profile("a")), context(type="mss310"))

    assert result.profile.id == "a"
    assert result.candidates == ("a", "b")
    assert result.ambiguous is True
    assert "Ambiguous profile match" in caplog.text


def test_mac_comparison_is_case_and_separator_insensitive():
    assert normalize_mac("aa:bb:cc:dd:ee:ff") == "AABBCCDDEEFF"
    assert normalize_mac("AA-BB-CC-DD-EE-FF") == "AABBCCDDEEFF"
    assert normalize_mac("not a mac") is None
    assert normalize_mac("ABC") is None

    result = match_profile(
        registry(profile("mac", mac_prefix=["AABBCC"])),
        context(type="mss310", mac="aa:bb:cc:dd:ee:ff"),
    )
    assert result.profile.id == "mac"


def test_invalid_or_missing_mac_cannot_satisfy_mac_prefix():
    macs = context(type="mss310", mac="zz:zz")
    missing = context(type="mss310")

    assert match_profile(
        registry(profile("mac", mac_prefix=["AABBCC"])), macs
    ).profile is None
    assert match_profile(
        registry(profile("mac", mac_prefix=["AABBCC"])), missing
    ).profile is None


def test_empty_abilities_only_match_profiles_without_requirements():
    required = profile("required", abilities={
        "all": ["Appliance.Control.ToggleX"]})
    unrestricted = profile("free", types=("mss311",))

    assert match_profile(registry(required), context(
        type="mss310", abilities=frozenset())).profile is None
    assert match_profile(registry(unrestricted), context(
        type="mss311", abilities=frozenset())).profile.id == "free"


def test_abilities_all_and_any():
    abilities = {"any": ["A", "B"], "all": ["C"]}
    entries = registry(profile("p", abilities=abilities))

    assert match_profile(entries, context(
        type="mss310", abilities=frozenset({"B", "C"}))).profile.id == "p"
    assert match_profile(entries, context(
        type="mss310", abilities=frozenset({"A"}))).profile is None
    assert match_profile(entries, context(
        type="mss310", abilities=frozenset({"C"}))).profile is None


def test_kind_filters_hubs_and_devices():
    hub = profile("hub", kind="hub")
    device = profile("device", kind="device")
    any_kind = profile("any", kind="any")

    assert match_profile(registry(hub), context(
        type="mss310", is_hub=False)).profile is None
    assert match_profile(registry(device), context(
        type="mss310", is_hub=True)).profile is None
    assert match_profile(registry(hub), context(
        type="mss310", is_hub=True)).profile.id == "hub"
    assert match_profile(registry(any_kind), context(
        type="mss310", is_hub=True)).profile.id == "any"


def test_subtype_wildcard_matches_any_subtype():
    result = match_profile(
        registry(profile("wild", sub_type=["*"])),
        context(type="mss310", sub_type="un"),
    )

    assert result.profile.id == "wild"


def test_declared_subtype_must_match():
    result = match_profile(
        registry(profile("sub", sub_type=["un"])),
        context(type="mss310", sub_type="other"),
    )

    assert result.profile is None


def test_type_and_subtype_comparison_is_case_insensitive():
    item = profile("a", types=("MSS310",), sub_type=["UN"])

    result = match_profile(
        registry(item), context(type="mss310", sub_type="un"))

    assert result.profile.id == "a"


def test_missing_match_never_matches():
    item = profile("a")
    item["profile"].pop("match")

    assert match_profile(registry(item), context(
        type="mss310")).profile is None


def test_malformed_match_never_matches():
    item = profile("a")
    item["profile"]["match"] = {"type": "mss310"}

    assert match_profile(registry(item), context(
        type="mss310")).profile is None


def test_unknown_kind_never_matches():
    item = profile("a", kind="sensor")

    assert match_profile(registry(item), context(
        type="mss310")).profile is None


def test_generic_profile_matches_unknown_devices():
    result = match_profile(
        registry(profile("generic", types=("*",))),
        context(type="mystery"),
    )

    assert result.profile.id == "generic"


def test_invalid_declared_mac_prefix_cannot_match():
    result = match_profile(
        registry(profile("mac", mac_prefix=["ABC"])),
        context(type="mss310", mac="AABBCCDDEEFF"),
    )

    assert result.profile is None


def test_empty_registry_matches_nothing():
    assert match_profile(
        registry(), context(type="mss310")).profile is None


def template(uid, types):
    return ProfileMeta(
        id=uid,
        version="1",
        source="template",
        digest=None,
        requires_engine=None,
        data={"match": {"type": list(types)}},
    )


def test_subdevice_templates_are_matched_deterministically():
    result = match_candidates(
        [template("hub:subdevice:1", ("ms100",)),
         template("hub:subdevice:0", ("ms100",))],
        context(type="ms100"),
    )

    assert result.profile.id == "hub:subdevice:0"
    assert result.candidates == ("hub:subdevice:0", "hub:subdevice:1")
    assert result.ambiguous is True


def test_unmatched_subdevice_returns_no_template():
    result = match_candidates(
        [template("hub:subdevice:0", ("ms100",))],
        context(type="ms200"),
    )

    assert result.profile is None
