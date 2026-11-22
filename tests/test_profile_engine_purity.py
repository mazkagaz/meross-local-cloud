import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / \
    "meross_local_cloud" / "profiles"
ALLOWED_IMPORTS = {
    "__future__",
    "asyncio",
    "contextlib",
    "dataclasses",
    "json",
    "logging",
    "math",
    "packaging",
    "re",
    "time",
    "typing",
}
FORBIDDEN_CALLS = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "getattr",
    "setattr",
}


def modules():
    return sorted(PACKAGE.glob("*.py"))


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_engine_modules_only_use_pure_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in ALLOWED_IMPORTS, \
                    f"{path.name} imports {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            root = (node.module or "").split(".")[0]
            assert root in ALLOWED_IMPORTS, \
                f"{path.name} imports from {node.module}"


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_engine_modules_avoid_blocking_or_dynamic_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_CALLS, \
                f"{path.name} calls {node.func.id}()"
