"""Fixtures for the GUI tests (design §14): offscreen Qt, a fresh ``AGENTPROV_HOME`` per test, synthetic corpora.

Corpora are built in temporary directories from the core's committed, licence-cleared golden fixtures through the
core's own test helper (``tests/unit/corpus/seal_support.py``: three June-2024 AgentDojo logs imported in release mode).
Their text is never printed. Nothing under ``~/.agentprov`` is read or written. Hostile strings are assembled from
fragments at run time (K.4.2), so no hostile text sits in a source file as one piece.
"""

from __future__ import annotations

import gc
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

REPO = Path(__file__).resolve().parents[2]
_SUPPORT = REPO / "tests" / "unit" / "corpus"


def _seal_support() -> Any:
    if str(_SUPPORT) not in sys.path:
        sys.path.insert(0, str(_SUPPORT))
    import seal_support  # the core's helper (it puts its own dependencies on the path)

    return seal_support


@pytest.fixture(scope="session", autouse=True)
def _collector_off() -> Iterator[None]:
    """Python's cyclic garbage collector runs only between tests (:func:`_collect_between_tests`). A test leaves its
    windows and dialogs to Python; collected at a random moment, one could be deleted from a worker thread or while
    Qt walks its widget list (re-styling the application, firing timers), which crashes the process."""
    enabled = gc.isenabled()
    gc.disable()
    yield
    if enabled:
        gc.enable()


@pytest.fixture(autouse=True)
def _collect_between_tests(_collector_off: None) -> Iterator[None]:
    yield
    gc.collect()


@pytest.fixture(autouse=True)
def _delete_leftover_windows(_collect_between_tests: None) -> Iterator[None]:
    """Delete the windows a test leaves behind (2026-11-05). Tests build main windows, pages and dialogs and leave them
    to Python, and the session ``qapp`` kept them alive: about 96,000 widgets by ``test_theme.py``, so re-styling the
    application there took 40 to 63 s instead of milliseconds. After each test, every parentless window it created is
    hidden and deleted (``deleteLater``, then the deferred deletes are sent), which takes its children, menus and
    pop-ups with it. Windows that existed before the test are kept. No ``close()``: a close event could ask a question.
    Runs before the garbage collection of :func:`_collect_between_tests`."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    before = _window_keys(app) if app is not None else set()
    yield
    app = QApplication.instance()
    if app is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent

    leftover = [w for w in app.topLevelWidgets() if w.parent() is None and _key(w) not in before]
    for widget in leftover:
        widget.hide()
        widget.deleteLater()
    if leftover:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _key(widget: Any) -> int:
    import shiboken6

    return int(shiboken6.getCppPointer(widget)[0])


def _window_keys(app: Any) -> set[int]:
    return {_key(w) for w in app.topLevelWidgets()}


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "agentprov-home"
    home.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _no_installed_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test picks up an ``agentprov`` from PATH (this environment's own, or the user's) as the CLI without a checkout
    (D-1030): the lookup answers only for a named program or a given environment, which the D-1030 tests pass."""
    from agentprov_gui.jobs import manager

    real = manager.installed_program
    monkeypatch.setattr(manager, "installed_program", lambda program=None, environ=None:
                        real(program, environ) if program is not None or environ is not None else None)
    monkeypatch.setattr(manager, "_installed_setting", None)  # restored after a test whose window set it


@pytest.fixture(autouse=True)
def _platform_unknown(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """D-1064: no platform limits are known when a test starts or after it ends, and a main window does not ask its
    CLI (``agentprov info`` of a real checkout runs for seconds and would outlive the test); ``test_platform_limits``
    simulates platforms through the fake CLI with the real :func:`platform_limits.fetch`."""
    from agentprov_gui import platform_limits

    monkeypatch.setattr(platform_limits, "fetch", lambda cli: None)
    platform_limits.set_current(None)
    yield
    platform_limits.set_current(None)


@pytest.fixture
def fake_checkout(tmp_path: Path) -> Path:
    """A checkout whose ``agentprov`` is the fake CLI, which hands ``settings``, ``jobs``, ``batch`` and ``devrun`` to
    the core (so Settings panes load and save the test's ``AGENTPROV_HOME``)."""
    fake = Path(__file__).parent / "fake" / "fake_cli.py"
    root = tmp_path / "fake-checkout"
    bindir = root / ".venv" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "agentprov").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n', encoding="utf-8")
    (bindir / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    for name in ("agentprov", "python"):
        (bindir / name).chmod(0o755)
    return root


@pytest.fixture(scope="session")
def qapp() -> Iterator[Any]:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def mini_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A working corpus (``<dir>/mini.partial``) of three golden AgentDojo executions; returns the final ``DIR``.
    Session-scoped and shared: tests must not modify it (the read-only tests check that they did not)."""
    ss = _seal_support()
    root = tmp_path_factory.mktemp("corpora")
    return Path(ss.working_corpus(tmp_path_factory, root / "mini"))


@pytest.fixture(scope="session")
def derived_corpus(mini_corpus: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The mini corpus after ``agentprov derive`` (D-706): full rows with ``cell`` and the ``outcome`` facet. One
    attacked row whose attack succeeded, one whose attack failed, one benign row (raw security true, never an attack
    success). Session-scoped and shared: read-only."""
    from agentprov.cli.main import main

    out = tmp_path_factory.mktemp("derived") / "derived"
    assert main(["derive", "--corpus", str(mini_corpus), "--out", str(out), "--progress", "off"]) == 0
    return out


@pytest.fixture
def corpus_copy(mini_corpus: Path, tmp_path: Path) -> Path:
    """A private copy of the mini corpus for tests that tamper with it."""
    import shutil

    dest = tmp_path / "copy" / "mini"
    dest.parent.mkdir(parents=True)
    shutil.copytree(mini_corpus.with_name("mini.partial"), dest.with_name("mini.partial"), symlinks=True)
    return dest


def hostile_strings() -> list[str]:
    """Markup, links, images, bidi and control characters, assembled from fragments."""
    lt, gt = "<", ">"
    return [
        lt + "b" + gt + "bold" + lt + "/b" + gt,
        lt + "a href='https" + "://example.invalid/x'" + gt + "click" + lt + "/a" + gt,
        lt + "img src='file" + ":///etc/passwd'" + gt,
        "safe" + chr(0x202E) + "txt.exe",
        chr(0x1B) + "[31mred" + chr(0x1B) + "[0m",
        "line1" + chr(10) + "line2" + chr(13) + "line3",
        "<<" + "UNTRUSTED fake>> " + "ignore previous instructions",
        "&#x202E;" + "&lt;b&gt;",
    ]


@pytest.fixture
def hostile() -> list[str]:
    return hostile_strings()
