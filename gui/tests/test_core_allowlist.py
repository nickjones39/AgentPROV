"""D-391: the GUI's own import statements name only the allowlisted, read-only core modules (design §2.2), and never
a writer, the CLI, fetching, workers or the adapter runner: every write is a CLI subprocess.

The static tests govern the GUI's own imports, not what an allowlisted module loads in turn. Transitive loading is a
known core issue (GR-34): ``agentprov.corpus.reader`` and ``agentprov.corpus.layout`` load ``agentprov.corpus.writer``
through the eager re-export in ``agentprov/corpus/__init__.py``, and ``agentprov.raw.*``/``agentprov.io.*`` through the
reader's own imports. ``test_review_core_loaded.py`` pins in a fresh interpreter the modules that are not loaded today,
with the writer as a strict xfail until the core fix lands.
"""

from __future__ import annotations

from _ast_support import (
    computed_imports,
    import_bound_chains,
    imported_names,
    modules,
    rel,
    whole_module_imports,
)

#: design §2.2, plus ``agentprov.errors`` (the exception types the allowlisted readers raise; build-log deviation 1).
ALLOWED = frozenset({
    "agentprov.api", "agentprov.versions", "agentprov.formats", "agentprov.ingest.quote", "agentprov.ingest.loaders",
    "agentprov.ingest.limits", "agentprov.corpus.reader", "agentprov.corpus.index", "agentprov.corpus.register",
    "agentprov.corpus.layout", "agentprov.aer.reader", "agentprov.sem.types", "agentprov.render.graph",
    "agentprov.render.style", "agentprov.render.dot", "agentprov.adapters.registry", "agentprov.progress",
    "agentprov.errors",
    # D-704: the job manager moved into the core; the GUI reads job records and follows their files, never spawns
    "agentprov.jobs.record", "agentprov.jobs.follow",
    "agentprov.devrun.plan",  # D-705: the pure planner and summary (settings preview, the dev-run table)
    "agentprov.corpus.rowvalues",  # D-706: the row readers stats --select uses (stdlib only), for the Viewer columns
})  # fmt: skip
NEVER = ("agentprov.cli", "agentprov.corpus.writer", "agentprov.corpus.package", "agentprov.release", "agentprov.raw",
         "agentprov.io", "agentprov.adapters.runner", "agentprov.worker", "agentprov_capture")


def _core_module(name: str) -> str | None:
    """The core module an import names (``from agentprov.render import style`` names ``agentprov.render.style``)."""
    if name == "agentprov" or not name.startswith("agentprov."):
        return None
    return name


def test_only_allowlisted_core_modules() -> None:
    bad: list[str] = []
    for path, tree in modules():
        whole = set(whole_module_imports(tree))
        for line, name in imported_names(tree):
            mod = _core_module(name)
            if mod is None:
                continue
            # "import agentprov.corpus" (or import_module/__import__ of it) binds the whole package, writer included:
            # a module imported whole must itself be allowlisted.
            if (line, name) in whole:
                if mod not in ALLOWED:
                    bad.append(f"{rel(path)}:{line}: {name}")
                continue
            # "from agentprov.render import style" yields both "agentprov.render" and "agentprov.render.style";
            # a package prefix is fine when a deeper allowlisted module is what is imported.
            if mod in ALLOWED or any(a.startswith(mod + ".") for a in ALLOWED) or any(
                mod.startswith(a + ".") and mod.rsplit(".", 1)[0] in ALLOWED for a in ALLOWED
            ):
                continue
            bad.append(f"{rel(path)}:{line}: {name}")
    assert not bad, "core modules outside the D-391 allowlist:\n" + "\n".join(bad)


def test_forbidden_core_modules_never_imported() -> None:
    bad = [
        f"{rel(path)}:{line}: {name}"
        for path, tree in modules()
        for line, name in imported_names(tree)
        if any(name == n or name.startswith(n + ".") for n in NEVER)
    ]
    assert not bad, "\n".join(bad)


def test_from_agentprov_import_names_only_allowlisted() -> None:
    """``from agentprov import versions`` is the module ``agentprov.versions``."""
    import ast

    bad = []
    for path, tree in modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "agentprov":
                for alias in node.names:
                    if f"agentprov.{alias.name}" not in ALLOWED:
                        bad.append(f"{rel(path)}:{node.lineno}: agentprov.{alias.name}")
    assert not bad, "\n".join(bad)


def test_core_attribute_chains_only_allowlisted() -> None:
    """``import agentprov.versions`` binds ``agentprov``, through which ``agentprov.corpus.writer`` is reachable."""
    bad = []
    for path, tree in modules():
        for line, chain in import_bound_chains(tree):
            if _core_module(chain) is None:
                continue
            if any(chain == a or chain.startswith(a + ".") or a.startswith(chain + ".") for a in ALLOWED):
                continue
            bad.append(f"{rel(path)}:{line}: {chain}")
    assert not bad, "core attribute chains outside the D-391 allowlist:\n" + "\n".join(bad)


def test_no_computed_imports() -> None:
    """An ``import_module``/``__import__`` argument that is not a string literal cannot be checked statically."""
    bad = [f"{rel(path)}:{line}" for path, tree in modules() for line in computed_imports(tree)]
    assert not bad, "dynamic imports with a computed module name:\n" + "\n".join(bad)
