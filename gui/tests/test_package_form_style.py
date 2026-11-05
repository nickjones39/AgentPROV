
"""D-1060: the Package page in the one form style. Each step shows only its own fields, its checks as a checklist (the
raw text stays behind Details) and a command card equal to the argv its action starts; the step list shows each step's
state; no step page scrolls sideways at 900 px."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _page(start: Any = None, checkout: Path | None = None) -> Any:
    from agentprov_gui.ui.package import PackagePage

    page = PackagePage(start or (lambda spec: None), checkout)
    page.timer.stop()
    page.resize(900, 640)
    page.show()
    return page


def _job(tmp_path: Path, exit_code: int | None) -> Any:
    return SimpleNamespace(job_id="j1", state="running" if exit_code is None else "finished", exit_code=exit_code,
                           outcome=None if exit_code is None else ("ok" if exit_code == 0 else "refused"),
                           file=lambda name: tmp_path / "absent" / name)


def test_each_step_shows_only_its_own_fields(qapp: Any) -> None:
    page = _page()
    owners = {0: (page.corpus, page.version), 4: (page.spec, page.licence, page.release_date),
              7: (page.deposit, page.metadata), 8: (page.release_toml_btn, page.zenodo_btn)}
    every = [w for ws in owners.values() for w in ws]
    for step in range(9):
        page.steps.setCurrentRow(step)
        qapp.processEvents()
        shown = [w for w in every if w.isVisible()]
        assert shown == list(owners.get(step, ())), step
    page.close()


@pytest.mark.parametrize(("step", "action", "key"), [(0, "dry_run", "dry-run"), (4, "seal", "seal"),
                                                     (5, "verify", "verify"), (7, "build_deposit", "deposit")])
def test_the_command_card_is_the_argv_the_action_starts(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                        step: int, action: str, key: str) -> None:
    import agentprov_gui.ui.jobdialog as jobdialog

    monkeypatch.setattr(jobdialog, "confirm", lambda parent, spec, preview: spec)
    started: list[Any] = []
    page = _page(lambda spec: started.append(spec) or _job(tmp_path, None))
    page.corpus.setText(str(tmp_path / "c.partial"))
    page.spec.setText(str(tmp_path / "corpus-spec.toml"))
    page.licence.setText(f"UP={tmp_path / 'LICENSE'}")
    page.release_date.setText("2026-11-05")
    page.deposit.setText(str(tmp_path / "out"))
    page.metadata.setText(str(tmp_path / "release.toml"))
    page.steps.setCurrentRow(step)
    card = page.cards[step]
    ((_comment, shown),) = card.commands
    getattr(page, action)()
    assert len(started) == 1 and tuple(started[0].argv) == shown and key in page.jobs
    assert card.plain() == "agentprov " + " ".join(shown)  # Copy: one line, what the job runs
    page.close()


def test_the_card_follows_the_fields_and_says_why_it_is_empty(qapp: Any, tmp_path: Path) -> None:
    page = _page()
    card = page.cards[0]
    assert card.commands == [] and "required" in card.note  # no corpus yet
    page.corpus.setText(str(tmp_path / "c"))
    assert card.commands and "--dry-run" in card.commands[0][1]
    page.version.setText("1.2.3")
    assert card.commands[0][1][card.commands[0][1].index("--corpus-version") + 1] == "1.2.3"
    page.close()


def test_the_release_scan_card_is_the_repository_tool(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.package import RELEASE_SCAN_PROGRAM, release_scan_argv

    page = _page()
    page.corpus.setText(str(tmp_path / "c.partial"))
    page.steps.setCurrentRow(6)
    card = page.cards[6]
    assert card.program == RELEASE_SCAN_PROGRAM and card.commands[0][1] == release_scan_argv(tmp_path / "c")
    assert card.plain().splitlines()[-1] == f"uv run python tools/release_scan.py {tmp_path / 'c'}"
    assert page.checks[6].texts() == ["warn: No release scan yet"]
    (tmp_path / "c.release-scan.json").write_text(json.dumps({"format": "agentprov-release-scan/0.1"}))
    page.corpus.editingFinished.emit()
    assert page.checks[6].texts() == ["ok: Release scan present", "ok: No untriaged findings file"]
    assert page.states[6] == "done"
    page.close()


def test_step_one_shows_its_checks_as_a_checklist(qapp: Any, mini_corpus: Path) -> None:
    page = _page()
    page.corpus.setText(str(mini_corpus))
    page.corpus.editingFinished.emit()
    shown = page.checks[0].texts()
    assert "ok: A working corpus" in shown and "ok: No writer holds the lock" in shown
    assert shown[-1] == "todo: Dry run: not started"
    assert "partial:" in page.texts[0].toPlainText()  # the raw text stays, behind Details
    page.close()


def test_the_step_list_shows_each_steps_state(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import Qt

    page = _page()
    assert page.states == ["todo"] * 9
    page.jobs["dry-run"] = _job(tmp_path, None)
    page.timer.timeout.emit()
    assert page.states[0] == "running"
    page.jobs["dry-run"] = _job(tmp_path, 0)
    page.jobs["seal"] = _job(tmp_path, 2)
    page.timer.timeout.emit()
    assert page.states[0] == "done" and page.states[4] == "failed"
    assert page.steps.item(4).data(Qt.ItemDataRole.AccessibleTextRole) == "5 Seal: failed"
    assert page.checks[0].texts()[-1] == "ok: Dry run: finished"
    page.close()


def test_no_step_scrolls_sideways_at_900_px(qapp: Any, mini_corpus: Path) -> None:
    from agentprov_gui.ui.forms import FormPage

    page = _page()
    page.corpus.setText(str(mini_corpus) + "/a/long/path/that/would/otherwise/widen/the/column/" * 3)
    for step in range(9):
        page.steps.setCurrentRow(step)
        qapp.processEvents()
        form = page.pages.widget(step)
        assert isinstance(form, FormPage)
        assert form.widget().minimumSizeHint().width() <= form.viewport().width(), step
    assert page.width() == 900
    page.close()

