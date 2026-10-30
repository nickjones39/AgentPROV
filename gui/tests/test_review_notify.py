"""GUI review GR-6: notification and subtitle text reaches the native layer as one escaped line (S15). The job-ended
notification used to pass ``job.command`` and ``job.outcome`` from the job files unescaped, and ``platform/macos.py``
only truncated what it was given."""

from __future__ import annotations

import json
import sys
import time
import types
import unicodedata
from pathlib import Path
from typing import Any

import pytest

RLO = chr(0x202E)
LF = chr(10)


def _single_line(text: str) -> bool:
    return not any(unicodedata.category(c) in {"Cc", "Cf"} for c in text)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.calls.append((title, body))

    def set_activity(self, *_a: object) -> None:
        pass

    def set_progress(self, *_a: object) -> None:
        pass


def test_job_ended_notification_is_escaped(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.jobs.manager import Job
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    w = MainWindow(Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)), cache_dir=tmp_path / "c",
                   home=tmp_path / "home", jobs=False)
    rec = _Recorder()
    w.chrome = rec  # type: ignore[assignment]
    d = tmp_path / "jobdir"
    d.mkdir()
    record = {"command": "import" + RLO + "kcatta" + LF + "line2", "writes": [str(tmp_path / "corpus-a")]}
    (d / "job.json").write_text(json.dumps(record), encoding="utf-8")
    job = Job("j1", d, record, state="ended", outcome="ok" + LF + "Your" + RLO + " data")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 1000)
    w._job_ended(job)
    monkeypatch.undo()
    w.close()
    assert len(rec.calls) == 1
    title, body = rec.calls[0]
    assert _single_line(title) and _single_line(body), ascii(body)
    assert body.endswith(": ended")  # an outcome outside the CLI vocabulary is not shown


def test_native_layer_escapes_notification_and_subtitle(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.platform import macos

    seen: dict[str, str] = {}

    class Content:
        def setTitle_(self, t: str) -> None:
            seen["title"] = t

        def setBody_(self, b: str) -> None:
            seen["body"] = b

    un = types.ModuleType("UserNotifications")
    un.UNUserNotificationCenter = types.SimpleNamespace(  # type: ignore[attr-defined]
        currentNotificationCenter=lambda: types.SimpleNamespace(
            addNotificationRequest_withCompletionHandler_=lambda req, _h: seen.setdefault("id", req)))
    un.UNMutableNotificationContent = types.SimpleNamespace(  # type: ignore[attr-defined]
        alloc=lambda: types.SimpleNamespace(init=Content))
    un.UNNotificationRequest = types.SimpleNamespace(  # type: ignore[attr-defined]
        requestWithIdentifier_content_trigger_=lambda ident, _c, _t: ident)
    monkeypatch.setitem(sys.modules, "UserNotifications", un)
    monkeypatch.setitem(sys.modules, "AppKit", types.ModuleType("AppKit"))
    monkeypatch.setattr(macos, "signed_bundle", lambda: True)
    monkeypatch.setattr(macos, "_auth", {"requested": True, "granted": True})  # GR-39

    macos._notify("Job" + LF + "done" + RLO, "x" + RLO + "y" + LF + "z")
    assert set(seen) == {"title", "body", "id"}
    assert all(_single_line(v) for v in seen.values()), ascii(seen)

    window = types.SimpleNamespace(setSubtitle_=lambda s: seen.__setitem__("subtitle", s))
    macos.NativeChrome(window, None, None, None, macos.DisplayFlags()).set_subtitle("a" + RLO + "b" + LF + "c")
    assert _single_line(seen["subtitle"]), ascii(seen["subtitle"])


def test_native_layer_does_not_escape_escaped_ids_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """GR-42: the caller escapes ids with ``text.line``; the native layer must not escape the ``<U+…>`` marker again."""
    from agentprov_gui import text as T
    from agentprov_gui.platform import macos

    seen: dict[str, str] = {}

    class Content:
        def setTitle_(self, t: str) -> None:
            seen["title"] = t

        def setBody_(self, b: str) -> None:
            seen["body"] = b

    un = types.ModuleType("UserNotifications")
    un.UNUserNotificationCenter = types.SimpleNamespace(  # type: ignore[attr-defined]
        currentNotificationCenter=lambda: types.SimpleNamespace(
            addNotificationRequest_withCompletionHandler_=lambda req, _h: None))
    un.UNMutableNotificationContent = types.SimpleNamespace(  # type: ignore[attr-defined]
        alloc=lambda: types.SimpleNamespace(init=Content))
    un.UNNotificationRequest = types.SimpleNamespace(  # type: ignore[attr-defined]
        requestWithIdentifier_content_trigger_=lambda ident, _c, _t: ident)
    monkeypatch.setitem(sys.modules, "UserNotifications", un)
    monkeypatch.setitem(sys.modules, "AppKit", types.ModuleType("AppKit"))
    monkeypatch.setattr(macos, "signed_bundle", lambda: True)
    monkeypatch.setattr(macos, "_auth", {"requested": True, "granted": True})

    name = T.line("corp" + RLO + "a", 80)  # as MainWindow._corpus_opened and _job_ended build it
    assert name == "corp<U+202E>a"
    macos._notify("Job finished", f"{T.line('import', 40)} {name}: ok")
    assert seen["body"] == "import corp<U+202E>a: ok", ascii(seen["body"])

    window = types.SimpleNamespace(setSubtitle_=lambda s: seen.__setitem__("subtitle", s))
    macos.NativeChrome(window, None, None, None, macos.DisplayFlags()).set_subtitle(name)
    assert seen["subtitle"] == "corp<U+202E>a", ascii(seen["subtitle"])
