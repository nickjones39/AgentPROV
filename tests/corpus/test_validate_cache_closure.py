"""D-1068 P5: the code part of the tier-4 cache context is the import closure of ``validate_prov`` (and of the cache).

The closure is derived from the source each time (``ast``), never listed by hand. An edit to a module inside it changes
the context, so every entry made before is a miss; an edit outside it (the CLI, the importer, an adapter) leaves the
context and its entries alone. Before D-1068 any edit to any package file emptied the cache. The walk is cross-checked
against an independent walker (the one ``tests/unit/test_stage_scopes.py`` uses for the stage digests).
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from agentprov.validate import cache as tc
from agentprov.validate.cache import DiskCache
from agentprov.validate.tiers import CheckOutcome

PKG = Path(tc.__file__).resolve().parents[1]
OUTCOMES = [CheckOutcome(i, "pass") for i in tc.ROUNDTRIP_IDS]
DOC = b'{"prefix": {}}'


def _package_copy(dest: Path) -> Path:
    """The package's Python sources only (what the closure can reach), at ``dest/agentprov``."""
    def ignore(directory: str, names: list[str]) -> set[str]:
        return {n for n in names if n == "__pycache__" or (not n.endswith(".py") and not (Path(directory) / n).is_dir())}

    return Path(shutil.copytree(PKG, dest / "agentprov", ignore=ignore))


def _append(path: Path, text: str) -> None:
    path.write_bytes(path.read_bytes() + text.encode())


@pytest.fixture
def package(tmp_path: Path) -> Path:
    return _package_copy(tmp_path)


def test_the_closure_holds_what_the_round_trip_runs_and_not_the_rest():
    files = set(tc.closure_files())
    assert {"validate/prov.py", "validate/roundtrip.py", "validate/cache.py", "validate/tiers.py", "validate/_provdoc.py",
            "prov/serialise/nquads.py", "ingest/loaders.py", "io/canonical.py", "__init__.py",
            "validate/__init__.py"} <= files
    assert not {f for f in files if f.startswith(("cli/", "corpus/", "adapters/", "raw/", "release/", "views/"))}
    assert "io/workers.py" not in files and "stage_scopes.py" not in files


def _independent_walk(seeds: tuple[str, ...]) -> set[str]:
    """``tests/unit/test_stage_scopes.py``'s walk (absolute imports at any depth), plus enclosing package inits."""
    def module_file(module: str) -> Path | None:
        path = PKG.joinpath(*module.split(".")[1:])
        if (path / "__init__.py").is_file():
            return path / "__init__.py"
        return path.with_suffix(".py") if path.with_suffix(".py").is_file() else None

    def imports(path: Path) -> set[str]:
        found: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name for a in node.names if a.name.split(".")[0] == "agentprov"}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith("agentprov"):
                found |= {node.module, *(f"{node.module}.{a.name}" for a in node.names)}
        return found

    start = {module_file(s) for s in seeds} - {None}
    seen, todo = set(start), list(start)
    while todo:
        for module in imports(todo.pop()):
            parts = module.split(".")
            for depth in range(1, len(parts) + 1):
                path = module_file(".".join(parts[:depth]))
                if path is not None and path not in seen:
                    seen.add(path)
                    todo.append(path)
    return {p.relative_to(PKG).as_posix() for p in seen if p is not None}


def test_the_closure_equals_an_independent_walk():
    assert set(tc.closure_files()) == _independent_walk(tc.CLOSURE_SEEDS)


@pytest.mark.parametrize("inside", ["validate/roundtrip.py", "prov/serialise/nquads.py", "aer/reader.py",
                                    "validate/cache.py", "prov/compat/adprov_v2_3/serialise.py", "__init__.py"])
def test_an_edit_inside_the_closure_changes_the_digest(package: Path, inside: str):
    before = tc.closure_digest(package)
    _append(package / inside, "\n# an edit\n")
    assert tc.closure_digest(package) != before


@pytest.mark.parametrize("outside", ["cli/main.py", "corpus/derive.py", "adapters/runner/importer.py",
                                     "adapters/agentdojo/mapper.py", "io/workers.py", "stage_scopes.py"])
def test_an_edit_outside_the_closure_leaves_the_digest(package: Path, outside: str):
    assert (package / outside).is_file()
    before = tc.closure_digest(package)
    _append(package / outside, "\n# an edit\n")
    assert tc.closure_digest(package) == before


def test_a_new_import_brings_its_module_into_the_closure(package: Path):
    """The closure is recomputed, not pinned: an inside module that starts importing an outside one (lazily, here)
    takes it in, and from then on an edit to that module is a miss too."""
    before = tc.closure_digest(package)
    _append(package / "validate/roundtrip.py", "\n\ndef _late():\n    from agentprov.corpus import selection\n")
    grown = tc.closure_digest(package)
    assert grown != before and "corpus/selection.py" in tc.closure_files(package)
    _append(package / "corpus/selection.py", "\n# an edit\n")
    assert tc.closure_digest(package) != grown


def test_relative_and_literal_dynamic_imports_are_followed(package: Path):
    _append(package / "validate/roundtrip.py", "\n\ndef _a():\n    from ..release import builder\n"
                                               "\n\ndef _b():\n    import importlib\n"
                                               "    importlib.import_module('agentprov.views.transcript_v1')\n")
    files = tc.closure_files(package)
    assert "release/builder.py" in files and "release/__init__.py" in files and "views/transcript_v1.py" in files


def _context_at(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(tc, "_PACKAGE_ROOT", root)
    tc.context.cache_clear()
    tc.context_digest.cache_clear()


@pytest.fixture
def restore_context():
    yield
    tc.context.cache_clear()
    tc.context_digest.cache_clear()


@pytest.mark.parametrize(("edited", "served"), [("validate/roundtrip.py", False), ("cli/main.py", True)])
def test_an_entry_is_a_miss_after_an_edit_inside_and_a_hit_after_one_outside(
        package: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restore_context: None, edited: str,
        served: bool) -> None:
    _context_at(monkeypatch, package)
    root = tmp_path / "cache"
    DiskCache(root).store(DOC, OUTCOMES)
    assert DiskCache(root).lookup(DOC) == OUTCOMES
    _append(package / edited, "\n# an edit\n")
    _context_at(monkeypatch, package)  # a new process: the context is computed again
    assert (DiskCache(root).lookup(DOC) == OUTCOMES) is served


def test_the_context_names_the_closure_and_the_format():
    context = tc.context()
    assert context["code"] == {"closure_sha256": tc.closure_digest(), "seeds": list(tc.CLOSURE_SEEDS)}
    assert tc.CACHE_FORMAT == "agentprov-tier4-cache/2" and "agentprov_code_sha256" not in context
