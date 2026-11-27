import ast
from pathlib import Path

import pytest

from custom_components.meross_local_cloud.profiles import paths as paths_module
from custom_components.meross_local_cloud.profiles.paths import (
    MISSING,
    UnknownToken,
    find_tokens,
    get_path,
    parse_path,
    substitute,
    validate_tokens,
)


def test_parse_path_returns_key_and_index_tokens():
    tokens = parse_path("togglex[0].onoff")

    assert tokens[0].key == "togglex"
    assert tokens[0].index == 0
    assert tokens[1].key == "onoff"
    assert tokens[1].index is None


def test_get_path_walks_dicts_and_lists():
    document = {
        "togglex": [{"onoff": 1}],
        "electricity": {"power": 42},
    }

    assert get_path(document, "togglex[0].onoff") == 1
    assert get_path(document, "electricity.power") == 42
    assert parse_path("togglex[0].onoff")


def test_get_path_returns_missing_instead_of_raising():
    document = {
        "togglex": [{"onoff": 1}],
        "scalar": 5,
        "items": [1, 2],
    }

    assert get_path(document, "absent") is MISSING
    assert get_path(document, "togglex[1].onoff") is MISSING
    assert get_path(document, "togglex[0].absent") is MISSING
    assert get_path(document, "scalar[0]") is MISSING
    assert get_path(document, "items.key") is MISSING
    assert get_path(document, "a..b") is MISSING
    assert get_path(document, None) is MISSING


@pytest.mark.parametrize("path", [
    "a..b",
    ".a",
    "a.",
    "a[",
    "a[]",
    "a[-1]",
    "a[x]",
    "a[0][1]",
    "$channel",
    "a.$value",
    "a b",
    "a/b",
])
def test_invalid_paths_are_refused(path):
    with pytest.raises(ValueError):
        parse_path(path)


def test_excessive_depth_is_refused():
    with pytest.raises(ValueError):
        parse_path(".".join(["a"] * 17))


def test_overlong_key_is_refused():
    with pytest.raises(ValueError):
        parse_path("a" * 65)


@pytest.mark.parametrize("key", ["__proto__", "constructor", "prototype"])
def test_reserved_keys_are_refused(key):
    with pytest.raises(ValueError):
        parse_path(f"parent.{key}")


def test_substitute_replaces_only_whole_strings():
    payload = {
        "channel": "$channel",
        "light": {"luminance": "$value", "name": "keep",
                  "label": "prefix-$value"},
        "list": ["$channel", 3],
    }

    assert substitute(payload, {"channel": 2, "value": 80}) == {
        "channel": 2,
        "light": {"luminance": 80, "name": "keep", "label": "prefix-$value"},
        "list": [2, 3],
    }


def test_id_token_is_supported_for_subdevices():
    assert substitute(
        {"mode": [{"id": "$id", "state": 1}]}, {"id": "sub1"}) == {
        "mode": [{"id": "sub1", "state": 1}]}
    assert validate_tokens({"id": "$id"}) == ()


def test_substitute_rejects_partial_and_unknown_tokens():
    with pytest.raises(UnknownToken):
        substitute("$channel_x", {"channel": 0})
    with pytest.raises(UnknownToken):
        substitute({"value": "$other"}, {})


def test_substitute_requires_a_value_for_each_token():
    with pytest.raises(UnknownToken):
        substitute("$value", {"channel": 0})


def test_get_path_accepts_parsed_tokens_and_scalar_documents():
    document = {"a": {"b": 3}}

    assert get_path(document, parse_path("a.b")) == 3
    assert get_path(5, "a.b") is MISSING
    assert get_path(None, "a.b") is MISSING


def test_paths_module_never_uses_dynamic_execution():
    source = Path(paths_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"eval", "exec", "compile", "__import__", "getattr",
                 "setattr", "globals", "locals"}

    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls & forbidden == set()


def test_token_discovery():
    payload = {"a": "$channel", "b": ["$value", "plain"]}

    assert set(find_tokens(payload)) == {"$channel", "$value"}
    assert validate_tokens(payload) == ()
    assert set(validate_tokens({"a": "$partial", "b": "$value"})) == {
        "$partial"}


def test_brightness_token_is_substituted():
    assert substitute({"luminance": "$brightness"}, {"brightness": 20}) == {
        "luminance": 20}


def test_unknown_substitution_still_raises():
    with pytest.raises(UnknownToken):
        substitute({"luminance": "$brightness"}, {})
