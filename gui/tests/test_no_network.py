"""S11 (D-396, amended by D-448): the GUI imports no network module, no web view and no QML.

Static: no import of ``socket``, ``ssl``, ``http``, ``urllib.request``, ``ftplib``, ``smtplib``, ``asyncio``,
``webbrowser``, ``logging.handlers`` (it imports ``socket``), ``PySide6.QtNetwork``, ``QtWebEngine*``, ``QtQuick*``
or ``QtQml``. Dynamic: a fresh interpreter (``python -I``) that imports every GUI module has none of the network
modules in ``sys.modules`` (as ``tests/boundary/test_release_offline.py`` does for the core). PyObjC's
``objc._convenience`` import of ``socket`` is tolerated by D-448 only from the native layer. In the same way,
``psutil`` imports ``socket`` at module level (address-family constants; it opens no socket): ``socket`` is tolerated
only when its importer is ``psutil`` (build-log deviation 19); ``ssl``, ``http`` and ``urllib.request`` stay banned.
The GUI needs no dynamic import, so ``importlib`` and any reference to ``__import__`` or ``import_module`` are banned
too (GR-13): they hide the imported name from the static check. The dynamic check attributes ``socket`` loads made
through every import route (statement, ``importlib``, meta-path find) to the first frame outside importlib.
A module taking the already-loaded ``socket`` from a tolerated importer's namespace loads nothing, so the static
check also bans (GR-60) any imported name or ``import``-bound attribute chain that has a network module as a dotted
component (``psutil.socket``) or reaches a private ``psutil._*``/``objc._*`` module (the GUI uses only their public
API).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Iterator

from _ast_support import HELPER_PROCESS_MODULES, SRC, import_bound_chains, imported_names, modules, rel

BANNED_PREFIXES = ("socket", "ssl", "http", "urllib.request", "ftplib", "smtplib", "asyncio", "webbrowser",
                   "logging.handlers", "PySide6.QtNetwork", "PySide6.QtWebEngine", "PySide6.QtQuick", "PySide6.QtQml",
                   "requests", "httpx", "urllib3", "keyring", "importlib", "pkgutil", "runpy")
#: GR-13, GR-61: names whose use hides the imported module from the static check.
DYNAMIC_IMPORT = ("__import__", "import_module", "resolve_name", "run_module", "run_path")
#: D-545 (psutil) and D-448 (PyObjC's objc._convenience, macOS only): the only importers socket may have.
TOLERATED: dict[str, tuple[str, ...]] = {"socket": ("psutil", "objc._convenience"), "_socket": ("socket",)}
#: GR-60: a dotted component naming one of these is a network module re-exported by another namespace.
REEXPORTED = frozenset({"socket", "_socket", "ssl", "_ssl"})
#: GR-60: private modules of the tolerated importers (``psutil._common`` and ``objc._convenience`` hold ``socket``).
PRIVATE_PREFIXES = ("psutil._", "objc._")
NETWORK_MODULES = ("socket", "_socket", "ssl", "_ssl", "http.client", "urllib.request", "asyncio",
                   "PySide6.QtNetwork", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick")


def dynamic_import_refs(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """Every reference to a ``DYNAMIC_IMPORT`` name (a name or an attribute, called or not)."""
    for node in ast.walk(tree):
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
        if name in DYNAMIC_IMPORT:
            yield node.lineno, name


def network_name(name: str) -> bool:
    """A banned module, a network module re-exported under another name, or a private psutil/objc module."""
    return (any(name == p or name.startswith(p + ".") for p in BANNED_PREFIXES)
            or not REEXPORTED.isdisjoint(name.split(".")) or name.startswith(PRIVATE_PREFIXES))


def test_static_no_network_imports() -> None:
    bad = [
        f"{rel(path)}:{line}: {name}"
        for path, tree in modules() if rel(path) not in HELPER_PROCESS_MODULES
        for refs in (imported_names(tree), import_bound_chains(tree))
        for line, name in refs
        if network_name(name)
    ]
    bad += [f"{rel(path)}:{line}: {name}" for path, tree in modules() if rel(path) not in HELPER_PROCESS_MODULES
            for line, name in dynamic_import_refs(tree)]
    assert not bad, "\n".join(bad)


def fresh_interpreter_imports(before: str = "", after: str = "") -> tuple[list[str], dict[str, list[str]]]:
    """Network modules a fresh interpreter has after importing every GUI module, and who imported socket and
    _socket. ``before``/``after`` are extra driver lines run before/after the GUI imports (the self-tests' probes)."""
    names = sorted(
        "agentprov_gui." + rel(p)[:-3].replace("/", ".").removesuffix(".__init__")
        for p in SRC.rglob("*.py") if p.name != "__main__.py" and rel(p) not in HELPER_PROCESS_MODULES
    )  # fmt: skip
    # Three hooks, one record: the builtins.__import__ hook sees every import statement (cache hits included), the
    # meta-path finder sees every first load by any route (importlib.__import__, _gcd_import, C imports) and the
    # import_module wrapper sees importlib cache hits. Hooks without importer globals walk the stack past importlib
    # and this driver to the real importer.
    code = (
        "import builtins, importlib, sys\n"
        "importers = {}\n"
        "driver = globals()\n"
        "def note(name, f):\n"
        "    while f is not None and (f.f_globals is driver\n"
        "                             or f.f_globals.get('__name__', '').partition('.')[0] == 'importlib'):\n"
        "        f = f.f_back\n"
        "    importers.setdefault(name, set()).add('?' if f is None else f.f_globals.get('__name__', '?'))\n"
        "class Finder:\n"
        "    @staticmethod\n"
        "    def find_spec(name, path=None, target=None):\n"
        "        if name in ('socket', '_socket'):\n"
        "            note(name, sys._getframe(1))\n"
        "sys.meta_path.insert(0, Finder)\n"
        "real = builtins.__import__\n"
        "def hook(name, g=None, *a, **k):\n"
        "    if name in ('socket', '_socket'):\n"
        "        importers.setdefault(name, set()).add((g or {}).get('__name__', '?'))\n"
        "    return real(name, g, *a, **k)\n"
        "builtins.__import__ = hook\n"
        "real_module = importlib.import_module\n"
        "def import_module(name, package=None):\n"
        "    if name in ('socket', '_socket'):\n"
        "        note(name, sys._getframe(1))\n"
        "    return real_module(name, package)\n"
        "importlib.import_module = import_module\n"
        f"{before}"
        f"for n in {names!r}: importlib.import_module(n)\n"
        f"{after}"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from agentprov_gui.ui.mainwindow import MainWindow\n"
        "if sys.platform == 'darwin':\n"
        "    import AppKit, Foundation, UserNotifications, objc\n"
        f"print(sorted(m for m in {NETWORK_MODULES!r} if m in sys.modules))\n"
        "print(sorted((k, sorted(v)) for k, v in importers.items()))\n"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, check=True,
                          timeout=120)
    loaded_line, importers_line = done.stdout.strip().splitlines()[-2:]
    return ast.literal_eval(loaded_line), dict(ast.literal_eval(importers_line))


def network_violations(loaded: list[str], importers: dict[str, list[str]]) -> list[str]:
    """``<module> imported by <importer>`` for every loaded network module whose importer is not tolerated."""
    return [
        f"{name} imported by {who}"
        for name in loaded
        for who in importers.get(name, ["?"])
        if not ((who == "?" and name == "_socket") or who in TOLERATED.get(name, ())
                or who.split(".")[0] in TOLERATED.get(name, ()))
    ]


def test_fresh_interpreter_loads_no_network_module() -> None:
    loaded, importers = fresh_interpreter_imports()
    bad = network_violations(loaded, importers)
    assert not bad, "\n".join(bad)
    if "socket" in loaded and "objc._convenience" in importers.get("socket", []):
        assert sys.platform == "darwin"
