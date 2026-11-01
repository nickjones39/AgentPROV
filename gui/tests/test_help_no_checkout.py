"""D-1030: Help › Docs, Help › Assistant and the CLI-backed Settings panes without an AgentPROV checkout (the downloaded
``.dmg`` or ``.zip`` alone).

* Docs reads the checkout's guide, else the copy the bundle takes from ``docs/user-guide/`` at build time, and says which
  one it shows; :func:`agentprov_gui.guide.bundle_files` names what the bundle takes and ``build_bundle.check_guide``
  checks the bundle has exactly those files with the guide's bytes.
* Without a checkout the CLI is the ``agentprov`` of ``pip install agentprov`` (a path in Settings › General, else
  PATH): here a stand-in script, so no model and no network is reached.
* A pane that cannot read its settings says why and what to set, above its disabled fields.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pytest

GUI = Path(__file__).resolve().parents[1]
REPO = GUI.parent
GUIDE = REPO / "docs" / "user-guide"


def wait(app: Any, cond: Any, timeout: float = 30) -> None:
    from PySide6.QtCore import QEventLoop

    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


def _bundled(tmp_path: Path) -> Path:
    """The guide as the bundle carries it (``agentprov_gui/data/user-guide``)."""
    from agentprov_gui.guide import bundle_files

    out = tmp_path / "bundled" / "user-guide"
    for name in bundle_files(GUIDE):
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(GUIDE / name, out / name)
    return out


def _program(tmp_path: Path, script: str, name: str = "agentprov") -> Path:
    """A stand-in for the ``agentprov`` that ``pip install agentprov`` puts in a ``bin`` folder."""
    body = tmp_path / f"{name}-impl.py"
    body.write_text(script, encoding="utf-8")
    exe = tmp_path / "bin" / name
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{body}" "$@"\n', encoding="utf-8")
    exe.chmod(0o755)
    return exe


# ---------------------------------------------------------------------------------------------- what the bundle takes
def test_the_bundle_takes_the_chapters_and_every_image_they_show() -> None:
    import re

    from agentprov_gui.guide import bundle_files
    from agentprov_gui.ui.help import chapters

    files = bundle_files(GUIDE)
    names = [p.name for _t, p in chapters(GUIDE)]
    assert files[:len(names)] == names and not [n for n in files if n.startswith("_")]
    shown = {m.group(1) for _t, p in chapters(GUIDE)
             for m in re.finditer(r"!\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)", p.read_text(encoding="utf-8"))
             if "://" not in m.group(1)}
    assert shown and shown == set(files[len(names):])  # every image a chapter shows, and no other
    assert all((GUIDE / name).is_file() for name in files)


def test_the_spec_takes_the_guide_with_bundle_files() -> None:
    spec = (GUI / "packaging" / "agentprov-gui.spec").read_text(encoding="utf-8")
    assert "bundle_files(GUIDE)" in spec and '"agentprov_gui/data/user-guide"' in spec
    from agentprov_gui.guide import BUNDLED

    assert BUNDLED == GUI / "src" / "agentprov_gui" / "data" / "user-guide"
    assert not BUNDLED.exists()  # built, never committed: the copy cannot drift from docs/user-guide


def test_the_bundle_check_finds_a_missing_a_changed_and_an_extra_guide_file(tmp_path: Path) -> None:
    sys.path.insert(0, str(GUI / "tools"))
    try:
        import build_bundle as bb
    finally:
        sys.path.pop(0)
    from agentprov_gui.guide import bundle_files

    for platform in ("darwin", "win32", "linux"):
        app = bb.bundle_path(tmp_path / platform / "dist", platform)
        inside = bb._resources(app, platform) / "agentprov_gui" / "data" / "user-guide"
        assert bb.check_guide(app, platform) == [f"missing: {n}" for n in bundle_files(GUIDE)]
        shutil.copytree(_bundled(tmp_path / platform), inside)
        assert bb.check_guide(app, platform) == []
        (inside / "08-desktop-app.md").write_bytes(b"# edited\n")
        (inside / "_go-live.md").write_bytes(b"internal\n")
        (inside / "README.md").unlink()
        assert bb.check_guide(app, platform) == ["missing: README.md", "differs: 08-desktop-app.md",
                                                 "extra: _go-live.md"]


# ---------------------------------------------------------------------------------------------- Docs
def test_without_a_checkout_docs_shows_the_bundled_guide_and_says_so(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument

    from agentprov_gui import __version__
    from agentprov_gui.ui.help import DocsPage

    bundled = _bundled(tmp_path)
    page = DocsPage(None, bundled=bundled)
    assert page.source == "bundled" and page.guide == bundled.resolve() and page.toc.count() > 10
    assert "came with this app" in page.note.text() and __version__ in page.note.text()
    assert page.settings_btn.isVisibleTo(page)
    assert page.current is not None and page.current.name == "README.md"
    page.follow(QUrl("07-live-runs.md#containment"))
    assert page.current is not None and page.current.name == "07-live-runs.md"
    image = QTextDocument.ResourceType.ImageResource.value
    assert page.view.loadResource(image, QUrl("images/gui/run-live-models.png")) is not None
    page.set_checkout(tmp_path / "no-guide")  # a checkout without docs/user-guide: still the bundled copy
    assert page.source == "bundled" and "has no docs/user-guide folder" in page.note.text()


def test_a_checkouts_guide_wins_over_the_bundled_copy(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.help import DocsPage

    page = DocsPage(REPO, bundled=_bundled(tmp_path))
    assert page.source == "checkout" and page.guide == GUIDE.resolve()
    assert "user guide of the checkout" in page.note.text() and not page.settings_btn.isVisibleTo(page)


# ---------------------------------------------------------------------------------------------- the installed CLI
def test_the_installed_program_is_the_named_one_else_the_first_on_path(tmp_path: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.jobs import manager

    exe = _program(tmp_path, "pass\n")
    assert manager.installed_program(exe) == exe
    assert manager.installed_program(tmp_path / "missing") is None  # a named program is never swapped for another
    plain = tmp_path / "plain"
    plain.write_text("", encoding="utf-8")
    assert manager.installed_program(plain) is None  # not executable
    monkeypatch.setattr(manager, "USER_BIN_DIRS", ())
    assert manager.installed_program(environ={"PATH": os.pathsep.join([str(tmp_path / "empty"),
                                                                        str(exe.parent)])}) == exe
    assert manager.installed_program(environ={"PATH": str(tmp_path / "empty")}) is None
    monkeypatch.setattr(manager, "USER_BIN_DIRS", (str(exe.parent),))  # ~/.local/bin and the like, off a short PATH
    assert manager.installed_program(environ={"PATH": "/usr/bin"}) == exe
    monkeypatch.setattr(sys, "frozen", True, raising=False)  # the app's own executable is never the CLI
    monkeypatch.setattr(sys, "executable", str(exe))
    assert manager.installed_program(environ={"PATH": str(exe.parent)}) is None


def test_without_a_checkout_the_locator_runs_the_installed_program(tmp_path: Path) -> None:
    from agentprov_gui.jobs.manager import CliLocator, set_installed_program

    assert not CliLocator.for_checkout(None).available
    exe = _program(tmp_path, "pass\n")
    set_installed_program(exe)
    cli = CliLocator.for_checkout(None)
    assert cli.program == (str(exe),) and cli.python == () and cli.checkout is None
    assert cli.describe() == f"the installed agentprov ({exe})"
    assert "pip install agentprov" in CliLocator(None, ()).describe()
    assert CliLocator.for_checkout(REPO).checkout == REPO  # a checkout still wins


ASSIST = r'''
import json, sys
argv = sys.argv[1:]
log = __file__ + ".calls"
with open(log, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")
if argv[:2] == ["settings", "list"]:
    print(json.dumps({"format": "agentprov-settings/0.1", "values": {
        "assistant.server": "splash", "assistant.base_url": "http://127.0.0.1:8003/v1", "assistant.model": "m"}}))
elif argv[:1] == ["assist"]:
    request = json.loads(sys.stdin.read())
    print(json.dumps({"format": "agentprov-assist-reply/0.1", "endpoint": "splash", "model": "m",
                      "reply": "asked: " + request["messages"][-1]["content"], "truncated": False,
                      "sources": ["docs/user-guide/08-desktop-app.md"], "usage": {}}))
else:
    sys.exit(2)
'''


def test_the_assistant_answers_through_the_installed_program(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.jobs.manager import CliLocator, set_installed_program
    from agentprov_gui.ui.help import AssistantPage

    exe = _program(tmp_path, ASSIST)
    set_installed_program(exe)
    page = AssistantPage(CliLocator.for_checkout(None))
    wait(qapp, lambda: page.ready)
    assert "Model: m on splash" in page.status.text()
    page.input.setPlainText("How do I verify a corpus?")
    page.send()
    wait(qapp, lambda: not page.busy)
    assert page.messages[-1]["content"] == "asked: How do I verify a corpus?"
    calls = [json.loads(x) for x in (tmp_path / "agentprov-impl.py.calls").read_text(encoding="utf-8").splitlines()]
    assist = next(c for c in calls if c[0] == "assist")
    assert "--keychain" in assist and "--allow-network" not in assist  # a local server: no egress, key from keychain


def test_the_assistant_without_any_cli_says_what_to_set(qapp: Any) -> None:
    from agentprov_gui.jobs.manager import CliLocator
    from agentprov_gui.ui.help import AssistantPage

    page = AssistantPage(CliLocator.for_checkout(None))
    wait(qapp, lambda: "Settings › General" in page.status.text())
    assert "pip install agentprov" in page.status.text() and not page.send_btn.isEnabled()


# ---------------------------------------------------------------------------------------------- Settings
def test_settings_general_names_the_program_and_shows_the_cli_in_use(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    exe = _program(tmp_path, "pass\n")
    dlg = SettingsDialog(settings)
    dlg.checkout.setText("")
    dlg.cli_program.setText(str(exe))
    dlg._show_cli()
    assert dlg.cli_in_use.text() == f"the installed agentprov ({exe})"
    dlg.cli_program.setText(str(tmp_path / "missing"))
    dlg._show_cli()
    assert dlg.cli_in_use.text().startswith("none:")
    dlg.cli_program.setText(str(exe))
    dlg._accept()
    assert settings.cli_program == exe
    settings.cli_program = Path("/tmp/a\x00b")  # a control character is refused (GR-66)
    assert settings.cli_program == exe


FAILING = r'''
import sys
sys.stderr.write("INFO agentprov.cli: start\nagentprov: error [settings.store]: the settings file is not readable\n"
                 "INFO agentprov.cli: end command=settings exit=3\n")
sys.exit(3)
'''


def test_a_pane_that_cannot_read_its_settings_says_why_and_what_to_set(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.jobs.manager import CliLocator
    from agentprov_gui.ui.livepanes import KeysPane
    from agentprov_gui.ui.settings_panes import AssistantPane, JobsPane

    jobs = JobsPane(None)
    wait(qapp, lambda: "Settings › General" in jobs.notice.text())
    assert "pip install agentprov" in jobs.notice.text() and jobs.notice.isVisibleTo(jobs)
    assert jobs.isEnabled() and jobs.notice.isEnabled() and not jobs.body.isEnabled() and jobs.loaded is None
    broken = AssistantPane(None, cli=CliLocator(None, (str(_program(tmp_path, FAILING)),)))
    wait(qapp, lambda: "not readable" in broken.notice.text())
    assert "exit 3" in broken.notice.text() and "end command" not in broken.notice.text()
    keys = KeysPane(None, None)
    assert "Settings › General" in keys.status.text() and not keys.store_btn.isEnabled()


def test_a_pane_that_reads_its_settings_hides_the_notice(qapp: Any, fake_checkout: Path) -> None:
    from agentprov_gui.ui.settings_panes import JobsPane

    pane = JobsPane(fake_checkout)
    wait(qapp, lambda: pane.loaded is not None)
    assert pane.body.isEnabled() and not pane.notice.isVisibleTo(pane)
