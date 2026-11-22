import logging

from custom_components.meross_local_cloud.profiles import (
    ENGINE_VERSION,
    ProfileRegistry,
)
from custom_components.meross_local_cloud.profiles.registry import engine_satisfies


def entry(profile_id, requires=None):
    data = {
        "schema_version": 2,
        "profile": {"id": profile_id, "version": "1"},
        "match": {"type": ["x"]},
        "payloads": {},
        "entities": [{"key": "sw", "platform": "switch"}],
    }
    if requires:
        data["profile"]["requires_engine"] = requires
    return {
        "id": profile_id,
        "version": "1",
        "requires_engine": requires,
        "source": "bundled",
        "hash": "h",
        "profile": data,
    }


def catalog(*entries, schema=2, errors=None):
    return {
        "schema_version": schema,
        "revision": "rev1",
        "profiles": list(entries),
        "errors": errors or [],
    }


def test_loads_profiles_and_metadata():
    registry = ProfileRegistry.from_catalog(
        catalog(entry("a"), entry("b"), entry("c")))

    assert registry.revision == "rev1"
    assert registry.schema_version == 2
    assert sorted(registry.profiles) == ["a", "b", "c"]
    assert registry.profiles["a"].version == "1"
    assert registry.profiles["a"].source == "bundled"
    summary = registry.summary()
    assert summary["profiles_loaded"] == 3
    assert summary["profiles_skipped"] == 0
    assert summary["engine_version"] == ENGINE_VERSION


def test_unsupported_schema_is_reported_and_not_loaded():
    registry = ProfileRegistry.from_catalog(catalog(entry("a"), schema=3))

    assert registry.profiles == {}
    assert any("unsupported schema_version" in error for error in registry.errors)


def test_requires_engine_too_recent_is_skipped():
    registry = ProfileRegistry.from_catalog(
        catalog(entry("old", ">=1.0"), entry("future", ">=99.0")))

    assert sorted(registry.profiles) == ["old"]
    assert len(registry.skipped) == 1
    assert registry.skipped[0].id == "future"
    assert "requires engine" in registry.skipped[0].reason


def test_duplicate_profile_is_skipped():
    registry = ProfileRegistry.from_catalog(catalog(entry("a"), entry("a")))

    assert list(registry.profiles) == ["a"]
    assert registry.skipped[0].reason == "duplicate profile id"


def test_malformed_entry_is_reported():
    registry = ProfileRegistry.from_catalog(catalog({"id": "a"}))

    assert registry.profiles == {}
    assert any("malformed profile" in error for error in registry.errors)


def test_catalog_errors_are_surfaced():
    registry = ProfileRegistry.from_catalog(
        catalog(entry("a"), errors=["broken.yaml: invalid"]))

    assert any("broken.yaml" in error for error in registry.errors)


def test_non_object_catalog_is_rejected():
    registry = ProfileRegistry.from_catalog(["not", "a", "catalog"])

    assert registry.profiles == {}
    assert any("not an object" in error for error in registry.errors)


def test_non_list_profiles_is_reported():
    registry = ProfileRegistry.from_catalog({
        "schema_version": 2,
        "revision": "rev1",
        "profiles": "nope",
    })

    assert registry.profiles == {}
    assert any("profiles is not a list" in error
               for error in registry.errors)


def test_non_list_catalog_errors_are_normalized():
    registry = ProfileRegistry.from_catalog({
        "schema_version": 2,
        "revision": "rev1",
        "profiles": [],
        "errors": "boom",
    })

    assert any("malformed catalog errors" in error
               for error in registry.errors)


def test_null_and_string_entries_are_rejected():
    registry = ProfileRegistry.from_catalog(
        catalog(None, "nope", {"id": "a", "profile": "nope"}))

    assert registry.profiles == {}
    assert len([error for error in registry.errors
                if "malformed profile" in error]) == 3


def test_entry_without_id_is_rejected():
    registry = ProfileRegistry.from_catalog(catalog({
        "version": "1",
        "profile": {"schema_version": 2, "profile": {"version": "1"}},
    }))

    assert registry.profiles == {}
    assert any("malformed profile" in error for error in registry.errors)


def test_entry_without_version_is_skipped():
    data = {
        "schema_version": 2,
        "profile": {"id": "a"},
        "match": {"type": ["x"]},
        "payloads": {},
        "entities": [],
    }
    registry = ProfileRegistry.from_catalog(catalog({
        "id": "a",
        "profile": data,
    }))

    assert registry.profiles == {}
    assert registry.skipped[0].reason == "missing profile version"


def test_non_string_requires_engine_is_skipped():
    registry = ProfileRegistry.from_catalog(
        catalog(entry("a", 5)))

    assert registry.profiles == {}
    assert registry.skipped[0].id == "a"


def test_invalid_requires_engine_is_skipped():
    registry = ProfileRegistry.from_catalog(
        catalog(entry("a", "nonsense")))

    assert registry.profiles == {}
    assert registry.skipped[0].id == "a"
    assert "requires engine" in registry.skipped[0].reason


def test_missing_revision_warns(caplog):
    caplog.set_level(logging.WARNING)
    registry = ProfileRegistry.from_catalog(
        catalog(entry("a")) | {"revision": None})

    assert registry.revision is None
    assert "no revision" in caplog.text


def test_boolean_schema_version_is_rejected():
    registry = ProfileRegistry.from_catalog(
        catalog(entry("a"), schema=True))

    assert registry.profiles == {}
    assert any("unsupported schema_version" in error
               for error in registry.errors)


def test_missing_hash_is_tolerated():
    item = entry("a")
    item.pop("hash")

    registry = ProfileRegistry.from_catalog(catalog(item))

    assert registry.profiles["a"].digest is None


def test_profile_level_requires_engine_is_evaluated():
    item = entry("a")
    item.pop("requires_engine")
    item["profile"]["profile"]["requires_engine"] = ">=99.0"

    registry = ProfileRegistry.from_catalog(catalog(item))

    assert registry.profiles == {}
    assert registry.skipped[0].id == "a"


def test_extension_keys_are_preserved():
    item = entry("a")
    item["profile"]["x-vendor"] = {"nested": True}

    registry = ProfileRegistry.from_catalog(catalog(item))

    assert registry.profiles["a"].data["x-vendor"] == {"nested": True}


def test_engine_requirements():
    assert engine_satisfies(">=1.0")
    assert engine_satisfies(f">={ENGINE_VERSION}")
    assert engine_satisfies(f"=={ENGINE_VERSION}")
    assert not engine_satisfies(">99.0")
    assert not engine_satisfies("nonsense")
