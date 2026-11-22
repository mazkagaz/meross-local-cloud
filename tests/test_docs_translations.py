import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "check_docs_translations.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "check_docs_translations", SCRIPT)
MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MODULE)


def setup_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.fr.md").write_text("bonjour\n", encoding="utf-8")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    manifest = root / "docs" / "translations.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({
        "source_language": "fr",
        "pairs": [{
            "source": "README.fr.md",
            "translation": "README.md",
        }],
    }), encoding="utf-8")
    return root, manifest


def test_update_then_check_passes(tmp_path):
    root, manifest = setup_repo(tmp_path)

    MODULE.update(root, manifest)

    assert MODULE.check(root, manifest) == []


def test_changed_source_is_reported(tmp_path):
    root, manifest = setup_repo(tmp_path)
    MODULE.update(root, manifest)
    (root / "README.fr.md").write_text("bonjour, modifié\n",
                                       encoding="utf-8")

    errors = MODULE.check(root, manifest)

    assert any("README.fr.md changed" in error for error in errors)


def test_changed_translation_is_reported(tmp_path):
    root, manifest = setup_repo(tmp_path)
    MODULE.update(root, manifest)
    (root / "README.md").write_text("hello, changed\n", encoding="utf-8")

    errors = MODULE.check(root, manifest)

    assert any("README.md changed" in error for error in errors)


def test_missing_translation_is_reported(tmp_path):
    root, manifest = setup_repo(tmp_path)
    MODULE.update(root, manifest)
    (root / "README.md").unlink()

    errors = MODULE.check(root, manifest)

    assert any("missing translation" in error for error in errors)


def test_identical_source_and_translation_are_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    manifest = root / "translations.json"
    manifest.write_text(json.dumps({
        "source_language": "fr",
        "pairs": [{
            "source": "README.md",
            "translation": "README.md",
        }],
    }), encoding="utf-8")

    errors = MODULE.check(root, manifest)

    assert any("source and translation are equal" in error
               for error in errors)
