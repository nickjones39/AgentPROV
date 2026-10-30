"""Helpers for the static tests: every module of ``gui/src/agentprov_gui`` and its imports."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "agentprov_gui"


#: D-655: modules that run only in their own helper process, never in the GUI process. The GUI-process network rule
#: (S11) does not scan them; each has its own test (``test_keychain_helper.py``).
HELPER_PROCESS_MODULES: tuple[str, ...] = ()  # D-702 moved the keychain helper into the core


def modules() -> Iterator[tuple[Path, ast.Module]]:
    for path in sorted(SRC.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


#: Calls that import a module named by their first argument (GR-61 adds the pkgutil, runpy and importlib.util
#: routes); ``run_path`` takes a file path, so it never counts as a literal import.
DYNAMIC_IMPORT_CALLS = ("import_module", "__import__", "resolve_name", "run_module", "run_path", "find_spec",
                        "spec_from_file_location", "spec_from_loader")


def _dynamic_import(node: ast.AST) -> ast.Call | None:
    """A call of a ``DYNAMIC_IMPORT_CALLS`` name (any receiver), else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    return node if name in DYNAMIC_IMPORT_CALLS else None


def _literal_module(call: ast.Call) -> str | None:
    """The module a dynamic import names by a string literal (``resolve_name``'s ``a.b:attr`` gives ``a.b``)."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    first = call.args[0] if call.args else None
    if name == "run_path" or not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    return first.value.partition(":")[0]


def whole_module_imports(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """Imports that bind a whole module: ``import a.b`` and string-literal dynamic-import calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif (call := _dynamic_import(node)) and (module := _literal_module(call)) is not None:
            yield call.lineno, module


def computed_imports(tree: ast.Module) -> Iterator[int]:
    """Lines of dynamic-import calls whose module name is not a string literal (every ``run_path``)."""
    for node in ast.walk(tree):
        if (call := _dynamic_import(node)) and _literal_module(call) is None:
            yield call.lineno


def imported_names(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """Fully qualified imported module names (``from a import b`` gives ``a`` and ``a.b``), including literal
    ``import_module``/``__import__`` arguments (the core's ``edges_of`` rule)."""
    yield from whole_module_imports(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module
            for alias in node.names:
                yield node.lineno, f"{node.module}.{alias.name}"


def import_bound_chains(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """Dotted attribute chains rooted at a name bound by ``import a.b [as c]``, spelled as module paths
    (``import a.b as c`` then ``c.d.e`` gives ``a.b.d.e``; ``import a.b`` then ``a.x`` gives ``a.x``)."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bound[alias.asname] = alias.name
                else:
                    top = alias.name.split(".", 1)[0]
                    bound[top] = top
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        parts: list[str] = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name) and cur.id in bound:
            yield node.lineno, ".".join([bound[cur.id], *reversed(parts)])


def rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()
