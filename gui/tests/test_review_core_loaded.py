"""GR-34 (D-391, design §2.2): a fresh interpreter (``python -I``) that imports every GUI module and the main window
has not loaded the CLI, release, packaging, fetching, the adapter runner, the worker or the capture package, by any
route. The static allowlist (``test_core_allowlist.py``) governs only the GUI's own imports; an allowlisted core module
can load others in turn. Since the GR-34 core fix (lazy re-exports in ``agentprov/corpus/__init__.py`` and
``agentprov/raw/__init__.py``), the writer, ``raw.members``, ``io.workers`` and ``agentprov.host`` are not among them."""

from __future__ import annotations

import ast
import functools
import os
import subprocess
import sys

import pytest

from _ast_support import SRC, rel

#: Modules a fresh interpreter has not loaded after importing every GUI module (a subset of the static ``NEVER``).
NEVER_LOADED = ("agentprov.cli", "agentprov.release", "agentprov.corpus.package", "agentprov.raw.fetch",
                "agentprov.adapters.runner", "agentprov.worker", "agentprov_capture")


def fresh_interpreter_core_modules(before: str = "") -> list[str]:
    """Every ``agentprov``/``agentprov_capture`` module a fresh interpreter (``python -I``) has after importing every
    GUI module and the main window. ``before`` is extra driver lines run first (the self-test's probe)."""
    names = sorted(
        "agentprov_gui." + rel(p)[:-3].replace("/", ".").removesuffix(".__init__")
        for p in SRC.rglob("*.py") if p.name != "__main__.py"
    )  # fmt: skip
    code = (
        "import importlib, sys\n"
        f"{before}"
        f"for n in {names!r}: importlib.import_module(n)\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "from agentprov_gui.ui.mainwindow import MainWindow\n"
        "print(sorted(m for m in sys.modules if m.partition('.')[0] in ('agentprov', 'agentprov_capture')))\n"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, check=True,
                          timeout=120)
    loaded: list[str] = ast.literal_eval(done.stdout.strip().splitlines()[-1])
    return loaded


@functools.cache
def _loaded() -> tuple[str, ...]:
    return tuple(fresh_interpreter_core_modules())


def _assert_not_loaded(forbidden: tuple[str, ...]) -> None:
    bad = [m for m in _loaded() if any(m == n or m.startswith(n + ".") for n in forbidden)]
    assert not bad, "loaded in the GUI process after importing every GUI module:\n" + "\n".join(bad)


def test_never_modules_not_loaded_transitively() -> None:
    _assert_not_loaded(NEVER_LOADED)


def test_corpus_writer_not_loaded() -> None:
    """GR-34 (core fix): the lazy re-exports in ``agentprov.corpus`` and ``agentprov.raw`` keep the writer, the expand
    stage, the worker pool and the host probes out of the GUI process (design §2.2, transitive core modules)."""
    _assert_not_loaded(("agentprov.corpus.writer", "agentprov.raw.members", "agentprov.io.workers", "agentprov.host"))


def test_never_loaded_check_catches_a_gui_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """A GUI module importing ``agentprov.cli`` (a probe run as ``agentprov_gui.probe``) fails the dynamic test."""
    body = "import agentprov." + "cli\n"
    probe = (
        "probe = __import__('types').ModuleType('agentprov_gui.probe')\n"
        "sys.modules['agentprov_gui.probe'] = probe\n"
        f"exec(compile({body!r}, 'agentprov_gui.probe', 'exec'), probe.__dict__)\n"
    )
    monkeypatch.setitem(globals(), "_loaded", lambda: tuple(fresh_interpreter_core_modules(before=probe)))
    with pytest.raises(AssertionError, match=r"agentprov\.cli"):
        test_never_modules_not_loaded_transitively()
