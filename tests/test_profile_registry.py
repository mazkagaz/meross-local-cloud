from custom_components.meross_cloud.profiles import (
    ENGINE_VERSION,
    ProfileRegistry,
)
from custom_components.meross_cloud.profiles.registry import engine_satisfies


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


def test_engine_requirements():
    assert engine_satisfies(">=1.0")
    assert engine_satisfies(f">={ENGINE_VERSION}")
    assert engine_satisfies(f"=={ENGINE_VERSION}")
    assert not engine_satisfies(">99.0")
    assert not engine_satisfies("nonsense")
