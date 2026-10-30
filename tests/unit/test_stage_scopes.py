"""D-451 (bug pass BF-33): each reused stage's code digest covers the transitive import closure of its seeds.

The pinned closures in :mod:`agentprov.stage_scopes` are recomputed here from the source with ``ast``: every absolute
``agentprov`` import (at any depth, lazy ones included) of every file reached, starting from the stage's seed
directories. A closure that grew (a stage now runs code outside its digest) or a pinned file the closure no longer
reaches fails, with the tuple to paste printed in the message. ``derive`` and the importer read the same scopes, so
their stage definitions stay equal (``test_derive.py`` pins that).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agentprov import stage_scopes as ss

PKG = Path(ss.__file__).resolve().parent


def _module_file(module: str) -> Path | None:
    path = PKG.joinpath(*module.split(".")[1:])
    if (path / "__init__.py").is_file():
        return path / "__init__.py"
    return path.with_suffix(".py") if path.with_suffix(".py").is_file() else None


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names if a.name.split(".")[0] == "agentprov"}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] == "agentprov":
            found |= {node.module, *(f"{node.module}.{a.name}" for a in node.names)}
    return found


def _seed_files(seeds: tuple[str, ...], exclude: tuple[str, ...] = ()) -> set[Path]:
    out: set[Path] = set()
    for seed in seeds:
        base = PKG / seed
        files = [base] if base.is_file() else [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]
        out |= {f for f in files if not f.relative_to(PKG).as_posix().startswith(exclude)}
    return out


def _outside(seeds: tuple[str, ...], exclude: tuple[str, ...] = ()) -> tuple[str, ...]:
    start = _seed_files(seeds, exclude)
    seen, todo = set(start), list(start)
    while todo:
        for module in _imports(todo.pop()):
            path = _module_file(module)
            if path is not None and path not in seen:
                seen.add(path)
                todo.append(path)
    # an excluded prefix stays out of the closure too: prov/specs.py looks the frozen compat oracle's spec up lazily, but
    # the oracle never changes (invariant 8) and is its own stage with its own digest
    return tuple(sorted(rel for p in seen - start if not (rel := p.relative_to(PKG).as_posix()).startswith(exclude)))


def _fix(name: str, value: tuple[str, ...]) -> str:
    return f"{name} must be:\n(\n" + "".join(f'    "{x}",\n' for x in value) + ")"


def test_the_sem_core_closure_is_pinned():
    assert ss.SEM_CLOSURE == _outside(ss.SEM_SEEDS), _fix("SEM_CLOSURE", _outside(ss.SEM_SEEDS))


def test_the_prov_closure_is_pinned():
    found = _outside(ss.PROV_SEEDS, ss.PROV_EXCLUDE)
    assert ss.PROV_CLOSURE == found, _fix("PROV_CLOSURE", found)


def test_the_validation_closure_is_pinned():
    found = _outside(ss.VALIDATION_SEEDS)
    assert ss.VALIDATION_CLOSURE == found, _fix("VALIDATION_CLOSURE", found)


@pytest.mark.parametrize("family", sorted(p.parent.name for p in PKG.glob("adapters/*/semantics")))
def test_each_familys_semantics_closure_is_pinned(family):
    core = set(ss.SEM_CLOSURE) | {p.relative_to(PKG).as_posix() for p in _seed_files(ss.SEM_SEEDS)}
    found = tuple(x for x in _outside((f"adapters/{family}/semantics",)) if x not in core)
    assert ss.SEM_FAMILY_CLOSURE.get(family) == found, _fix(f"SEM_FAMILY_CLOSURE[{family!r}]", found)


def test_a_known_import_outside_the_old_lists_is_now_covered():
    """The BF-33 examples: an edit to these files used to leave the reused stages' digests unchanged."""
    assert "adapters/agentdojo/citation.py" in ss.sem_scope(["adapters/agentdojo/semantics"])
    assert {"aer/reader.py", "aer/evidence.py"} <= set(ss.prov_scope())


def test_the_expand_digest_covers_the_import_closure_of_raw_members():
    """BF-39: ``expand``'s ``engine_code_sha256`` hashed a hand-kept list of 8 modules while ``raw/members.py`` imports 18
    (``raw/origins.py``, ``raw/store.py``, ``ingest/paths.py``, ...), so an edit to one of the 10 left the digest unchanged."""
    from agentprov.raw.members import EXPAND_MODULES

    found = tuple(sorted({"raw/members.py", *_outside(("raw/members.py",))}))
    assert EXPAND_MODULES == found, _fix("raw.members.EXPAND_MODULES", found)


def _aer_core() -> tuple[str, ...]:
    """The map path's closure: imports are followed from ``adapters/runner/__init__.py`` (``job_map``, ``seal_outcome``)
    and ``aer/`` only. The other runner files are hashed but orchestrate the later stages, which have their own digests."""
    hashed = _seed_files(ss.AER_SEEDS)
    start = _seed_files(ss.AER_FOLLOW)
    seen, todo = set(start), list(start)
    while todo:
        for module in _imports(todo.pop()):
            path = _module_file(module)
            if path is not None and path not in seen and path not in hashed:
                seen.add(path)
                todo.append(path)
    return tuple(sorted(p.relative_to(PKG).as_posix() for p in seen - hashed))


def test_the_aer_digest_covers_the_map_paths_import_closure():
    """BF-39: the ``aer`` stage hashed ``adapters/runner`` and ``aer`` only, while the map job runs ``raw/carve.py``,
    ``raw/origins.py``, ``io/workers.py`` and more from outside them."""
    found = _aer_core()
    assert {"raw/carve.py", "raw/origins.py", "io/workers.py"} <= set(found)
    assert ss.AER_CLOSURE == found, _fix("AER_CLOSURE", found)


@pytest.mark.parametrize("family", sorted(p.parent.name for p in PKG.glob("adapters/*/__init__.py")
                                          if p.parent.name not in ("runner", "registry")))
def test_each_familys_mapper_closure_is_pinned(family):
    """BF-39: ``adapter_code_sha256`` hashes ``adapters/<family>/`` only; what the family imports from outside it (and
    outside the aer core) is in the aer stage's scope."""
    covered = set(ss.AER_CLOSURE) | {p.relative_to(PKG).as_posix() for p in _seed_files(ss.AER_SEEDS)}
    found = tuple(x for x in _outside((f"adapters/{family}",)) if x not in covered)
    assert ss.AER_FAMILY_CLOSURE.get(family) == found, _fix(f"AER_FAMILY_CLOSURE[{family!r}]", found)


def test_the_importer_records_the_aer_scope():
    import inspect

    from agentprov.adapters.runner import importer
    from agentprov.corpus import derive

    for module in (importer, derive):
        assert '"adapters/runner", "aer"]' not in inspect.getsource(module), module.__name__
    assert ss.aer_scope("agentdojo")[:2] == list(ss.AER_SEEDS)
    assert "adapters/projection.py" in ss.aer_scope("agentdojo") and "raw/carve.py" in ss.aer_scope("credleak")
