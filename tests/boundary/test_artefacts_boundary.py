"""``agentprov.artefacts`` is an L3 package beside ``validate`` (MN M.1.2, D.15.3; DECISIONS D-12).

Static ``ast`` checks, no module imported:

* it imports only L0-L3 components of the core and never an adapter module (``adapters`` is L4: catalogues are read as
  package data through ``importlib.resources``);
* it is pure: no clock, randomness, environment, network, subprocess or file writing, and no ``open`` (catalogues come
  only through ``importlib.resources``);
* it changes nothing it observes: ``aer``, ``prov``, ``validate`` and ``corpus`` do not import it, so the layer can be
  removed without touching them.

(The generic layering test in ``test_import_boundary.py`` already covers direction and cycles for it, since ``artefacts``
is in its layer table.)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_import_boundary import CORE, LAYERS, edges_of, py_files, rel, top  # noqa: E402

ROOT = CORE / "artefacts"
SOURCES = sorted(py_files(ROOT))
BANNED_MODULES = frozenset(
    {"random", "secrets", "uuid", "socket", "urllib", "http", "requests", "httpx", "subprocess", "tempfile", "time",
     "zoneinfo", "locale", "shutil", "pickle", "marshal", "tarfile", "zipfile", "platform", "dotenv", "yaml", "datetime"}
)  # fmt: skip
BANNED_ATTRS = frozenset(
    {("os", "environ"), ("os", "getenv"), ("os", "urandom"), ("os", "system"), ("Path", "write_bytes"), ("Path", "write_text"),
     ("Path", "open"), ("Path", "read_bytes"), ("Path", "read_text"), ("Path", "unlink"), ("Path", "mkdir")}
)  # fmt: skip
BANNED_CALLS = frozenset({"open", "input", "eval", "exec", "__import__", "compile"})


def test_the_package_exists_and_is_in_the_layer_table():
    assert {p.name for p in SOURCES} >= {"__init__.py", "catalogue.py", "detectors.py", "scan.py"}
    assert LAYERS["artefacts"] == LAYERS["validate"] == 3


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: rel(p, ROOT))
def test_imports_only_lower_layers_and_no_adapter_module(path: Path):
    bad = []
    for edge in edges_of(path):
        parts = edge.target.split(".")
        if parts[0] != "agentprov" or len(parts) < 2:
            continue
        component = parts[1]
        if component == "adapters" or LAYERS.get(component, 0) > LAYERS["artefacts"]:
            bad.append(f"{edge.line}: {edge.target}")
    assert bad == [], f"{rel(path, ROOT)} reaches above L3 or into an adapter: {bad}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: rel(p, ROOT))
def test_no_impure_construct(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if top(a.name) in BANNED_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module and top(node.module) in BANNED_MODULES:
            found.append(f"from {node.module} import")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and (node.value.id, node.attr) in BANNED_ATTRS:
            found.append(f"{node.value.id}.{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
            found.append(f"{node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr in ("now", "utcnow", "environ", "urandom"):
            found.append(f"*.{node.attr}")
    assert found == [], f"{rel(path, ROOT)}: {found}"


def test_the_protected_core_does_not_import_the_artefact_layer():
    importers = []
    for component in ("aer", "prov", "validate", "corpus", "ingest", "raw", "io"):
        for path in py_files(CORE / component):
            importers += [f"{rel(path, CORE)}:{e.line}" for e in edges_of(path) if e.target.split(".")[:2] == ["agentprov", "artefacts"]]
    assert importers == [], "aer/, prov/, validate/, corpus/ and the layers below must not depend on artefacts/: " + ", ".join(importers)
