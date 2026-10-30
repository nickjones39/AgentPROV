"""SEC-11 scoped to src/agentprov/ingest (K.12.6 static list) plus the host-agnostic rule: no platform branching in ingest."""

from __future__ import annotations

import ast
import pathlib

import pytest

import agentprov.ingest as ingest_pkg

INGEST_DIR = pathlib.Path(ingest_pkg.__file__).parent
FILES = sorted(INGEST_DIR.glob("*.py"))
FORBIDDEN_IMPORTS = {"pickle", "marshal", "tarfile", "shutil", "subprocess", "dotenv", "shelve", "dill", "joblib", "platform"}
FORBIDDEN_CALL_NAMES = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_ATTRS = {"extract", "extractall", "unpack_archive", "splitlines", "system", "popen", "entry_points", "load_dotenv",
                   "unsafe_load", "full_load", "FullLoader", "UnsafeLoader", "CLoader", "CSafeLoader", "literal_eval"}


def tree_of(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_the_scan_sees_every_ingest_module():
    assert {p.name for p in FILES} >= {
        "__init__.py", "limits.py", "loaders.py", "archives.py", "streams.py", "names.py", "paths.py", "quote.py",
        "yamlsafe.py",
    }


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_sec11_no_dangerous_imports_calls_or_attributes(path):
    for node in ast.walk(tree_of(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in FORBIDDEN_IMPORTS, f"{path.name}: import {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in FORBIDDEN_IMPORTS, f"{path.name}: from {node.module}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALL_NAMES, f"{path.name}: {node.func.id}()"
            for kw in node.keywords:
                assert not (kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value), "shell=True"
        elif isinstance(node, ast.Attribute):
            assert node.attr not in FORBIDDEN_ATTRS, f"{path.name}: .{node.attr}"


def test_sec11_yaml_is_imported_only_by_yamlsafe_and_only_load_is_called_with_the_strict_loader():
    for path in FILES:
        imports_yaml = any(
            (isinstance(n, ast.Import) and any(a.name.split(".")[0] == "yaml" for a in n.names))
            or (isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "yaml")
            for n in ast.walk(tree_of(path))
        )
        assert imports_yaml == (path.name == "yamlsafe.py"), path.name
    loads = [
        n
        for n in ast.walk(tree_of(INGEST_DIR / "yamlsafe.py"))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"load", "safe_load"}
    ]
    assert len(loads) == 1 and loads[0].func.attr == "load"  # type: ignore[attr-defined]
    assert [kw.value.id for kw in loads[0].keywords if kw.arg == "Loader"] == ["StrictSafeLoader"]  # type: ignore[attr-defined]


def test_sec11_json_loads_is_called_only_by_the_strict_loader_and_never_on_bytes():
    for path in FILES:
        calls = [
            n
            for n in ast.walk(tree_of(path))
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"loads", "load"}
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "json"
        ]
        assert len(calls) == (1 if path.name == "loaders.py" else 0), path.name
        for call in calls:
            assert isinstance(call.args[0], ast.Name) and call.args[0].id == "text"  # the strictly decoded str


def test_sec11_no_text_mode_open_and_no_extraction_vocabulary_in_ingest():
    for path in FILES:
        for node in ast.walk(tree_of(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                pytest.fail(f"{path.name}: builtin open() (ingest reads descriptors and caller-supplied binary streams)")


def test_host_agnostic_no_platform_branching_in_ingest():
    for path in FILES:
        for node in ast.walk(tree_of(path)):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                assert (node.value.id, node.attr) not in {("sys", "platform"), ("os", "name")}, f"{path.name}: {node.value.id}.{node.attr}"
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in {"darwin", "linux", "win32", "Windows", "Darwin", "Linux"}, f"{path.name}: {node.value!r}"
            if isinstance(node, ast.Constant) and node.value == 0x20000000:
                pytest.fail(f"{path.name}: hard-coded O_NOFOLLOW_ANY constant")


def test_platform_primitives_are_read_only_inside_the_paths_probe():
    for path in FILES:
        for node in ast.walk(tree_of(path)):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                if node.attr.startswith("O_") and path.name != "paths.py":
                    pytest.fail(f"{path.name}: os.{node.attr}")
