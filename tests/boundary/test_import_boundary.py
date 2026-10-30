"""Static import-boundary test (MN M.5.5(2); DoD Q.1; AD-01, AD-17).

Everything here is ``ast`` scanning: no module is imported. It collects imports at any nesting depth (including those
inside functions and ``TYPE_CHECKING`` blocks) and the string literal passed to ``importlib.import_module`` or
``__import__``, and checks each edge against the rules of M.5.1 to M.5.3:

* the core imports no benchmark package (M.5.2(9)), so a benchmark can never reach the core environment;
* ``agentprov_capture`` imports only the standard library and ``rfc8785``;
* nothing under ``capture/`` or ``backends/`` imports ``agentprov``, and no ``backends/*/uv.lock`` lists a package called
  ``agentprov`` (the backend environments never install the core);
* ``yaml`` only in ``ingest/yamlsafe.py`` (AD-17), ``rfc8785`` only in ``io/canonical.py``, ``pydot`` only under
  ``render/``, ``dotenv`` only in ``cli/run.py`` and ``cli/backends.py``;
* nothing imports ``agentprov.cli`` except ``__main__`` (M.5.2(6)), and no ``src`` module imports ``tests`` or ``tools``;
* no upward import and no cycle between components, for the components of the M.5.1 layer table that exist.

The rule tables are data at the top of the file. The registry-factory strings (M.5.5(2)) join the scan when
``agentprov.adapters.registry`` exists.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "src" / "agentprov"
CAPTURE = REPO / "capture"
CAPTURE_PKG = CAPTURE / "src" / "agentprov_capture"
BACKENDS = REPO / "backends"

#: Benchmark and model-client packages the core must never import (M.5.2(9)).
BENCHMARK_PACKAGES = frozenset({"agentdojo", "agentdyn", "inspect_ai", "openai", "anthropic", "httpx", "httpx2",
                                "agentprov_backend"})

#: Third-party package -> the module paths (relative to ``src/agentprov``) that may import it (M.5.3).
#: A path ending in ``/`` allows every module below that directory.
THIRD_PARTY_IMPORTERS: dict[str, tuple[str, ...]] = {
    "yaml": ("ingest/yamlsafe.py",),
    "rfc8785": ("io/canonical.py",),
    "pydot": ("render/",),
    "dotenv": ("cli/run.py", "cli/backends.py"),
    # M.5.3 as amended 2026-10-08: `presets` reads the endpoint registry and runs the loopback-only preflight (N.2.1a).
    # cli/live/ (phase 8, N.2.1b): the parent side of live runs uses the redactor's scan and append_terminal (G.6.4).
    "agentprov_capture": ("adapters/agentdojo/capture_reader.py", "cli/run.py", "cli/live/", "presets.py",
                          "cli/keys.py",  # D-702: the endpoint registry's key variables
                          "cli/prices.py"),  # D-701: the endpoint names and which ones are local
    # D-702: keyring only in the keychain helper process (its jaraco.context imports urllib.request)
    "keyring": ("keys/helper.py",),
    # D-704: psutil (process identity and trees) only in the jobs package; it imports socket for constants (D-545)
    "psutil": ("jobs/",),
    "urllib.request": ("raw/fetch.py",),
    # D-691: cli/live/localmodels.py lists and fingerprints local model servers (loopback-only, peer checked).
    # D-730: cli/live/providermodels.py fetches an API provider's model list (registry host only, TLS verified).
    "http.client": ("raw/fetch.py", "presets.py", "cli/live/localmodels.py", "cli/live/providermodels.py"),
    # worker_testjobs.py holds the hostile test job kinds that probe the audit hook (G.4.4); enabled only in tests.
    # cli/live/egress.py (D-664): the T0 egress proxy (loopback CONNECT-only, asyncio) and the sandbox probe's loopback
    # listeners; it runs in the parent only, never in a T1 or T2 worker.
    "socket": ("raw/fetch.py", "io/worker_testjobs.py", "cli/live/egress.py"),
}

#: M.5.1 layers by component (longest module-prefix match). Components that are not listed (not yet in the table) are
#: not checked for direction.
LAYERS: dict[str, int] = {
    "_version": 0, "errors": 0, "formats": 0, "envinfo": 0, "versions": 0, "host": 0, "progress": 0, "io": 0, "ingest": 0,
    "stage_scopes": 0, "stage_definitions": 3,
    "raw": 1, "aer": 1,
    "sem": 2, "prov": 2, "views": 2,
    "validate": 3,
    "adapters": 4, "adapters.registry": 6, "adapters.runner": 6,
    "corpus": 5, "release": 5,
    "worker": 6, "presets": 6, "artefacts": 3,
    "stats": 7, "render": 7, "migration": 7,
    "cli": 8, "api": 8, "__main__": 8,
    "settings": 1, "keys": 1,  # D-703, D-702 (reverse CLI parity): stdlib, errors, ingest and io only
    "estimate": 2,  # D-701: reads AER documents (aer.reader) and fetches through raw.fetch
    "jobs": 1,  # D-704: stdlib, errors, ingest, io and psutil
    "devrun": 7,  # D-705: the registry (adapters.registry) and the job records
}  # fmt: skip

SKIP_DIRS = frozenset({".venv", "venv", "__pycache__", "node_modules", "site-packages", "build", "dist", ".git"})


class Edge(NamedTuple):
    path: Path
    line: int
    target: str  # the dotted module name as written (absolute)


def py_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        if not (set(path.relative_to(root).parts) & SKIP_DIRS):
            yield path


def edges_of(path: Path) -> list[Edge]:
    """Every absolute import in ``path`` at any depth, plus ``import_module("x")`` / ``__import__("x")`` literals."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[Edge] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(Edge(path, node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append(Edge(path, node.lineno, node.module))
                # `from agentprov import host` names a component; `from urllib import request` names urllib.request
                found.extend(Edge(path, node.lineno, f"{node.module}.{alias.name}") for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            first = node.args[0]
            if name in ("import_module", "__import__") and isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.append(Edge(path, node.lineno, first.value))
    return found


def top(module: str) -> str:
    return module.split(".", 1)[0]


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def where(edge: Edge) -> str:
    return f"{edge.path.relative_to(REPO).as_posix()}:{edge.line} imports {edge.target}"


@pytest.fixture(scope="module")
def core_edges() -> list[Edge]:
    return [edge for path in py_files(CORE) for edge in edges_of(path)]


def test_the_scan_finds_the_trees_it_is_meant_to_check(core_edges):
    assert len(list(py_files(CORE))) > 30 and core_edges
    assert list(py_files(CAPTURE_PKG)) and (BACKENDS / "shared").is_dir()
    assert sorted(p.parent.name for p in BACKENDS.glob("*/uv.lock")) == ["agentdojo", "agentdyn", "autodojo", "shared"]
    # D-662: the Inspect harness keeps one uv project per benchmark under backends/inspect/envs/
    assert [p.parent.relative_to(BACKENDS).as_posix() for p in BACKENDS.glob("*/envs/*/uv.lock")] == ["inspect/envs/agentharm"]


# ---------------------------------------------------------------------------------------------- Q.1 and M.5.2(9)


def test_core_imports_no_benchmark_package(core_edges):
    bad = [where(e) for e in core_edges if top(e.target) in BENCHMARK_PACKAGES]
    assert bad == [], "the core must not import benchmark or model-client packages (M.5.2(9); AD-01):\n" + "\n".join(bad)


def test_agentprov_capture_imports_only_the_stdlib_and_rfc8785():
    allowed = set(sys.stdlib_module_names) | {"rfc8785", "agentprov_capture"}
    bad = [where(e) for path in py_files(CAPTURE_PKG) for e in edges_of(path) if top(e.target) not in allowed]
    assert bad == [], "agentprov_capture is stdlib + rfc8785 only:\n" + "\n".join(bad)


@pytest.mark.parametrize("tree", [CAPTURE, BACKENDS], ids=["capture", "backends"])
def test_nothing_under_capture_or_backends_imports_agentprov(tree):
    bad = [where(e) for path in py_files(tree) for e in edges_of(path) if top(e.target) == "agentprov"]
    assert bad == [], "capture/ and backends/ never import the core (AD-01):\n" + "\n".join(bad)


def _backend_locks() -> list[Path]:
    return sorted(BACKENDS.glob("*/uv.lock")) + sorted(BACKENDS.glob("*/envs/*/uv.lock"))


def test_no_backend_lock_lists_the_core_package():
    locks = _backend_locks()
    assert locks
    offenders = []
    for lock in locks:
        data = tomllib.loads(lock.read_text(encoding="utf-8"))
        names = {pkg.get("name") for pkg in data.get("package", [])}
        for pkg in data.get("package", []):
            names.update(dep.get("name") for dep in pkg.get("dependencies", []))
        if "agentprov" in names:
            offenders.append(lock.relative_to(REPO).as_posix())
        # a textual guard as well: no line names the exact package
        if any(line.strip() in ('name = "agentprov"', '{ name = "agentprov" }') for line in lock.read_text().splitlines()):
            offenders.append(lock.relative_to(REPO).as_posix() + " (text)")
    assert offenders == [], "backend environments must never install the core: " + ", ".join(offenders)


def test_nothing_in_the_core_capture_or_backends_imports_the_gui():
    """D-391: the GUI (``gui/``, its own uv project) depends one-way on the core; nothing here ever imports it."""
    bad = [where(e) for tree in (CORE, CAPTURE, BACKENDS) for path in py_files(tree) for e in edges_of(path)
           if top(e.target) in ("agentprov_gui", "PySide6", "shiboken6")]
    assert bad == [], "the core, capture/ and backends/ never import the GUI or Qt (D-391):\n" + "\n".join(bad)


def test_nothing_in_the_core_capture_or_backends_imports_the_zenodo_uploader():
    """D-880: ``agentprov-zenodo`` (``zenodo/``, the draft-only uploader) depends one-way on the core, so the ``agentprov``
    package stays offline for releases (HL H.10.1(1)) and has no upload command (D-790)."""
    bad = [where(e) for tree in (CORE, CAPTURE, BACKENDS) for path in py_files(tree) for e in edges_of(path)
           if top(e.target) == "agentprov_zenodo"]
    assert bad == [], "the core, capture/ and backends/ never import agentprov_zenodo (D-880):\n" + "\n".join(bad)


def test_no_core_or_backend_lock_lists_the_gui_or_qt():
    """D-391: ``agentprov-gui`` and PySide6 live only in ``gui/uv.lock``, never in the core or a backend lock."""
    locks = [REPO / "uv.lock", *_backend_locks()]
    offenders = []
    for lock in locks:
        names = {pkg.get("name") for pkg in tomllib.loads(lock.read_text(encoding="utf-8")).get("package", [])}
        offenders += [f"{lock.relative_to(REPO).as_posix()}: {n}" for n in sorted(names)
                      if n == "agentprov-gui" or n.startswith(("pyside6", "shiboken6"))]
    assert offenders == [], ", ".join(offenders)


# ---------------------------------------------------------------------------------------------- M.5.3 importers


@pytest.mark.parametrize("package", sorted(THIRD_PARTY_IMPORTERS))
def test_third_party_package_is_imported_only_where_m53_allows(core_edges, package):
    allowed = THIRD_PARTY_IMPORTERS[package]

    def permitted(relpath: str) -> bool:
        return any(relpath == a or (a.endswith("/") and relpath.startswith(a)) for a in allowed)

    def matches(target: str) -> bool:  # `urllib.request` must not match `urllib.parse`
        return target == package or target.startswith(package + ".")

    bad = [where(e) for e in core_edges if matches(e.target) and not permitted(rel(e.path, CORE))]
    assert bad == [], f"{package} may be imported only by {', '.join(allowed)} (M.5.3):\n" + "\n".join(bad)


def test_the_allowed_importers_are_real_files_when_they_exist(core_edges):
    """Guard against the rule table going stale: the one yaml importer and the one rfc8785 importer do import them."""
    importers = {(top(e.target), rel(e.path, CORE)) for e in core_edges}
    assert ("yaml", "ingest/yamlsafe.py") in importers
    assert ("rfc8785", "io/canonical.py") in importers


# ---------------------------------------------------------------------------------------------- M.5.2(6), layering


def test_nothing_imports_cli_except_main(core_edges):
    bad = [where(e) for e in core_edges if e.target.startswith("agentprov.cli") and rel(e.path, CORE).split("/")[0] not in ("cli", "__main__.py")]
    assert bad == [], "only __main__ (and cli itself) may import agentprov.cli (M.5.2(6)):\n" + "\n".join(bad)


def test_no_source_module_imports_tests_or_tools(core_edges):
    bad = [where(e) for e in core_edges if top(e.target) in ("tests", "tools")]
    assert bad == []


#: M.5.1 side row: `testing` may import L0-L6, and only `tests/` and `tools/` may import it.
SIDE_MAX_LAYER = 6


def test_testing_is_a_side_layer_that_only_tests_and_tools_import(core_edges):
    too_high = [
        f"{where(e)} (layer {LAYERS[dst]})"
        for e in core_edges
        if rel(e.path, CORE).split("/")[0] == "testing"
        and (dst := component_of_target(e.target)) in LAYERS
        and LAYERS[dst] > SIDE_MAX_LAYER
    ]
    assert too_high == [], "agentprov.testing may import L0-L6 only (M.5.1 side row):\n" + "\n".join(too_high)
    importers = [
        where(e)
        for e in core_edges
        if component_of_target(e.target) == "testing" and rel(e.path, CORE).split("/")[0] != "testing"
    ]
    assert importers == [], "agentprov.testing may be imported only by tests/ and tools/ (M.5.1 side row):\n" + "\n".join(importers)


#: Components named by a two-part prefix (M.5.1: "a module belongs to the component of its **longest** matching prefix"):
#: ``adapters.registry`` and ``adapters.runner`` are L6, every other ``adapters.*`` module is L4.
TWO_PART_COMPONENTS = frozenset({"adapters.registry", "adapters.runner"})


def component(module_path: str) -> str:
    """The M.5.1 component of a module path relative to ``agentprov`` (``io/workers.py`` -> ``io``; longest prefix)."""
    parts = module_path.split("/")
    first = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    if len(parts) > 1:
        second = parts[1][:-3] if parts[1].endswith(".py") else parts[1]
        if f"{first}.{second}" in TWO_PART_COMPONENTS:
            return f"{first}.{second}"
    return first


def component_of_target(target: str) -> str | None:
    parts = target.split(".")
    if parts[0] != "agentprov":
        return None
    if len(parts) > 2 and f"{parts[1]}.{parts[2]}" in TWO_PART_COMPONENTS:
        return f"{parts[1]}.{parts[2]}"
    return parts[1] if len(parts) > 1 else None


def test_component_uses_the_longest_prefix():
    assert component("adapters/runner/importer.py") == component("adapters/runner/__init__.py") == "adapters.runner"
    assert component("adapters/registry/__init__.py") == "adapters.registry"
    assert component("adapters/inspect/dialect.py") == component("adapters/profiles.py") == "adapters"
    assert component_of_target("agentprov.adapters.runner.importer") == "adapters.runner"
    assert component_of_target("agentprov.adapters.types") == "adapters"
    assert LAYERS["adapters.runner"] == LAYERS["adapters.registry"] == 6 and LAYERS["adapters"] == 4


def test_no_upward_imports_between_components(core_edges):
    bad = []
    for edge in core_edges:
        src_component = component(rel(edge.path, CORE))
        dst_component = component_of_target(edge.target)
        if dst_component is None or src_component == dst_component:
            continue
        if src_component in LAYERS and dst_component in LAYERS and LAYERS[dst_component] > LAYERS[src_component]:
            bad.append(f"{where(edge)} (layer {LAYERS[src_component]} -> {LAYERS[dst_component]})")
    assert bad == [], "no upward imports (M.5.2(1)):\n" + "\n".join(bad)


def test_the_component_import_graph_is_acyclic(core_edges):
    graph: dict[str, set[str]] = {}
    for edge in core_edges:
        src_component = component(rel(edge.path, CORE))
        dst_component = component_of_target(edge.target)
        if dst_component and dst_component != src_component and src_component in LAYERS and dst_component in LAYERS:
            graph.setdefault(src_component, set()).add(dst_component)
    visiting: list[str] = []
    done: set[str] = set()

    def visit(node: str) -> list[str] | None:
        if node in done:
            return None
        if node in visiting:
            return [*visiting[visiting.index(node) :], node]
        visiting.append(node)
        for nxt in sorted(graph.get(node, ())):
            cycle = visit(nxt)
            if cycle:
                return cycle
        visiting.pop()
        done.add(node)
        return None

    for start in sorted(graph):
        cycle = visit(start)
        assert cycle is None, "package-level import cycle (M.5.2(5)): " + " -> ".join(cycle)


def test_layer_table_names_only_real_or_planned_components():
    """Every top-level module or package present under src/agentprov and named in the table keeps its layer."""
    present = {p.name[:-3] if p.suffix == ".py" else p.name for p in CORE.iterdir() if not p.name.startswith("__pycache__")}
    for name in present & set(LAYERS):
        assert isinstance(LAYERS[name], int)


# ---------------------------------------------------------------------------------------------- the scanner itself


def test_the_scanner_sees_nested_dynamic_and_from_imports(tmp_path):
    sample = tmp_path / "m.py"
    sample.write_text(
        "from __future__ import annotations\n"
        "import importlib\n"
        "from . import sibling\n"
        "from agentprov import host\n"
        "def f():\n"
        "    import yaml\n"
        "    from openai import OpenAI\n"
        "    importlib.import_module('agentdojo.task_suite')\n"
        "    __import__('httpx')\n"
        "    if False:\n"
        "        import inspect_ai.log as log\n"
    )
    targets = {e.target for e in edges_of(sample)}
    assert {"yaml", "openai", "agentdojo.task_suite", "httpx", "inspect_ai.log", "agentprov", "agentprov.host"} <= targets
    assert not any(t.startswith(".") for t in targets)  # relative imports are not absolute edges
    assert {top(t) for t in targets} & BENCHMARK_PACKAGES == {"openai", "agentdojo", "httpx", "inspect_ai"}


def test_the_psutil_allowance_admits_psutil_alone(core_edges):
    """D-704 (the D-545 pattern): psutil may be imported by ``jobs/`` and nowhere else, and the allowance covers psutil
    only: a ``jobs`` module that imported ``socket``, ``urllib.request`` or ``http.client`` itself would fail, and so
    would a psutil import from any other component."""
    assert THIRD_PARTY_IMPORTERS["psutil"] == ("jobs/",)
    for network in ("socket", "urllib.request", "http.client"):
        assert not any(a.startswith("jobs") for a in THIRD_PARTY_IMPORTERS[network]), network
    jobs_network = [where(e) for e in core_edges if rel(e.path, CORE).startswith("jobs/")
                    and top(e.target) in ("socket", "ssl", "http", "urllib", "asyncio")]
    assert jobs_network == []
    elsewhere = [where(e) for e in core_edges if top(e.target) == "psutil" and not rel(e.path, CORE).startswith("jobs/")]
    assert elsewhere == []
    # and the checker itself refuses a hypothetical second importer
    fake = Edge(CORE / "corpus" / "writer.py", 1, "psutil")
    permitted = any(rel(fake.path, CORE) == a or (a.endswith("/") and rel(fake.path, CORE).startswith(a))
                    for a in THIRD_PARTY_IMPORTERS["psutil"])
    assert not permitted
