"""``agentprov.prov`` is a pure function (EF E.0.1 item 2, E.9 item 3): a static ban-list over the engine sources.

The engine reads no clock, randomness, environment, network or file: catalogues come through ``importlib.resources``
only. The frozen compat port (``prov/compat/``) is exempt: it is AST-equal to the baseline and gated by its own tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "agentprov" / "prov"
SOURCES = sorted(p for p in ROOT.rglob("*.py") if "compat" not in p.relative_to(ROOT).parts)
BANNED_MODULES = frozenset({"random", "secrets", "uuid", "socket", "urllib", "http", "requests", "httpx", "subprocess",
                            "tempfile", "time", "zoneinfo", "locale"})
BANNED_ATTRS = frozenset({("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("date", "today"),
                          ("os", "environ"), ("os", "getenv"), ("os", "urandom"), ("Path", "read_bytes"),
                          ("Path", "read_text"), ("Path", "open")})
BANNED_CALLS = frozenset({"open", "input", "eval", "exec", "__import__"})


def test_there_are_engine_sources() -> None:
    assert len(SOURCES) >= 8


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_impure_construct(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] in BANNED_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in BANNED_MODULES:
            found.append(f"from {node.module} import")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in BANNED_ATTRS:
                found.append(f"{node.value.id}.{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
            found.append(f"{node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr in ("now", "utcnow", "environ", "urandom"):
            found.append(f"*.{node.attr}")
    assert found == [], f"{path.name}: {found}"
