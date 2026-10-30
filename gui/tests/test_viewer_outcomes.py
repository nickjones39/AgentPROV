"""D-706: the Viewer's task and outcome columns, their filters as CLI selections, the attack-succeeded glyph and tint,
the Index Row tab and the render export, on the derived mini corpus (``derived_corpus``):

* ``workspace``, attacked, security false: attack succeeded **no**;
* ``banking``, attacked, security true: attack succeeded **yes** (glyph and tint);
* ``banking``, benign: the raw security judgement is true, but SEM gives no ``attack_succeeded`` claim on a benign cell,
  so the column is blank and the row is never tinted.

The working mini corpus (``mini_corpus``) shows the derive hint and no task pickers. Every filter's CLI selection
(``agentprov stats --select``) selects exactly the rows the Viewer shows.
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any

import pytest
from agentprov import api
from agentprov.corpus.reader import CorpusReader

from agentprov_gui.readmodel.executions import TableFilter, cli_selection, load_table
from test_viewer import wait

ATTACK = "outcome.attack_succeeded"


def _table(root: Path) -> Any:
    return load_table(CorpusReader.open(root))


def _by_suite_attack(table: Any) -> dict[tuple[str | None, str | None], int]:
    return {(table.value(r, "cell.suite"), table.value(r, "cell.attack_id")): r for r in range(len(table))}


def test_task_and_outcome_columns_of_a_derived_corpus(derived_corpus: Path) -> None:
    table = _table(derived_corpus)
    assert table.full_rows == 3
    rows = _by_suite_attack(table)
    failed = rows[("workspace", "important_instructions")]
    succeeded = rows[("banking", "important_instructions")]
    benign = rows[("banking", None)]
    assert table.value(failed, ATTACK) == "no" and table.value(succeeded, ATTACK) == "yes"
    assert table.value(benign, ATTACK) is None and table.sets[ATTACK][benign] == ("none",)
    assert "security=true" in table.value(benign, "judgements")  # the raw judgement, never read as a success
    assert table.value(failed, "cell.defense_id") == "spotlighting_with_delimiting"
    assert table.value(benign, "outcome.user_task_solved") == "yes"
    assert table.vocabulary(ATTACK) == ["true", "false", "none"]


def test_a_working_corpus_has_no_task_or_outcome_values(mini_corpus: Path) -> None:
    table = _table(mini_corpus)
    assert table.full_rows == 0 and len(table) == 3
    for key in ("cell.suite", "cell.attack_id", ATTACK, "outcome.user_task_solved", "judgements"):
        assert all(table.value(r, key) is None for r in range(len(table))), key
    assert table.select(TableFilter(pickers=((ATTACK, frozenset({"none"})),))) == []  # as the CLI: nothing known


def _cli_rows(root: Path, args: list[str]) -> list[str]:
    select: dict[str, list[str]] = {}
    for flag, expr in zip(args[::2], args[1::2], strict=True):
        assert flag == "--select"
        key, _, values = expr.partition("=")
        select.setdefault(key, []).extend(values.split(","))
    return [row.ex for row in api.iter_executions(api.open_corpus(root), select=select)]


@pytest.mark.parametrize("pickers", [
    ((ATTACK, frozenset({"true"})),),
    ((ATTACK, frozenset({"none"})),),
    ((ATTACK, frozenset({"false", "true"})),),
    (("cell.suite", frozenset({"banking"})), ("outcome.user_task_solved", frozenset({"false"}))),
    (("cell.defense_id", frozenset({"spotlighting_with_delimiting"})),),
    (("model.requested", frozenset({"claude-3-opus-20240229"})),),
    (("status", frozenset({"ok"})), ("cell.attack_id", frozenset({"important_instructions"}))),
])
def test_every_filter_selects_what_its_cli_selection_selects(derived_corpus: Path,
                                                             pickers: tuple[tuple[str, frozenset[str]], ...]) -> None:
    table = _table(derived_corpus)
    flt = TableFilter(pickers)
    args, notes = cli_selection(flt)
    assert notes == []
    assert [table.ex(r) for r in table.select(flt)] == _cli_rows(derived_corpus, args)


def test_parts_without_a_cli_spelling_are_named() -> None:
    args, notes = cli_selection(TableFilter(pickers=(("cell.suite", frozenset({"a,b"})),), ex_contains="ex_1",
                                            issue_code="code.x"))
    assert args == ["--select", "issue=code.x"]
    assert any("comma" in n for n in notes) and any("id search" in n for n in notes)


def test_only_a_succeeded_attack_is_tinted_and_marked(derived_corpus: Path, qapp: Any) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui import theme
    from agentprov_gui.ui.viewer import ExecutionsModel

    table = _table(derived_corpus)
    model = ExecutionsModel()
    model.set_table(table)
    col = next(i for i, c in enumerate(model.columns) if c.key == ATTACK)
    rows = _by_suite_attack(table)
    for (suite, attack), r in rows.items():
        index = model.index(model.order.index(r), col)
        tinted = model.data(index, Qt.ItemDataRole.BackgroundRole)
        shown = model.data(index, Qt.ItemDataRole.DisplayRole)
        if (suite, attack) == ("banking", "important_instructions"):
            assert tinted == theme.attack_tint() and shown == f"{theme.ATTACK_GLYPH} yes"
            assert model.data(index, Qt.ItemDataRole.AccessibleTextRole) == "attack succeeded"
        else:
            assert tinted is None and theme.ATTACK_GLYPH not in str(shown)  # benign and failed rows stay plain
    assert theme.ATTACK_GLYPH in model.headerData(col, Qt.Orientation.Horizontal)
    assert "benign" in model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)


def test_the_tint_follows_the_scheme_and_contrast(monkeypatch: pytest.MonkeyPatch, qapp: Any) -> None:
    from agentprov_gui.ui import theme

    seen = set()
    for dark in (False, True):
        for strong in (False, True):
            monkeypatch.setattr(theme, "is_dark", lambda d=dark: d)
            monkeypatch.setitem(theme.ACCESS, "increase_contrast", strong)
            seen.add(theme.attack_tint().name())
    assert len(seen) == 4


@pytest.fixture
def window(qapp: Any, tmp_path: Path, derived_corpus: Path) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [derived_corpus.parent]
    w = MainWindow(settings, cache_dir=tmp_path / "cache", home=tmp_path / "home")
    yield w
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(30_000)  # background reads finish before the window goes
    qapp.processEvents()
    w.close()


def test_the_viewer_shows_filters_legend_cli_row_json_and_export(qapp: Any, window: Any, derived_corpus: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui.jobdialog import JobDialog

    dialogs: list[JobDialog] = []

    def exec_(self: JobDialog) -> int:  # the render form is modal: record it, never block the test
        dialogs.append(self)
        return 0

    monkeypatch.setattr(JobDialog, "exec", exec_)
    v = window.viewer
    v.open_path(derived_corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() == 3)
    assert not v.derive_hint.isVisibleTo(v) and v.legend.isVisibleTo(v)
    box = v.pickers[ATTACK]
    assert box.isVisibleTo(v) and [box.itemText(i) for i in range(box.count())][1:] == ["yes", "no", "not judged"]
    box.setCurrentIndex(box.findData("true"))
    assert v.model.rowCount() == 1
    command, notes = v.cli_command()
    assert "--select outcome.attack_succeeded=true" in command and notes == []
    # the corpus as --corpus names it: the final DIR, not the DIR.partial tree read (N.1.5)
    final = os.path.realpath(derived_corpus)
    assert v.reader.used_partial and v.corpus_arg() == final and ".partial" not in command
    assert shlex.split(command)[:4] == ["agentprov", "stats", "--corpus", final]
    v._copy_cli()
    from PySide6.QtGui import QGuiApplication

    assert QGuiApplication.clipboard().text() == command
    emitted: list[tuple[str, str]] = []
    v.render_requested.connect(lambda c, e: emitted.append((c, e)))
    v.exec_view.selectRow(0)
    wait(qapp, lambda: v.preview.row_json.toPlainText() != "")
    row = json.loads(v.preview.row_json.toPlainText())
    assert row["cell"]["suite"] == "banking" and any(e.get("claim") == "attack_succeeded" and e.get("holds") is True
                                                     for e in row["facets"]["outcome"])
    assert v.preview.render_btn.isEnabled()
    v.preview.render_btn.click()
    assert emitted == [(final, row["ex"])]
    assert [d.form.name for d in dialogs] == ["render"]  # Export Graph opens agentprov render's form (D-654)


def test_a_working_corpus_shows_the_derive_hint(qapp: Any, window: Any, mini_corpus: Path) -> None:
    v = window.viewer
    v.open_path(mini_corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() == 3)
    assert v.derive_hint.isVisibleTo(v) and not v.legend.isVisibleTo(v)
    assert not v.pickers[ATTACK].isVisibleTo(v) and not v.pickers["cell.suite"].isVisibleTo(v)


def test_hostile_cell_values_are_escaped_in_cells_pickers_and_the_cli_line(qapp: Any, corpus_copy: Path) -> None:
    """S3: a suite name from an untrusted log (here a bidi override and a newline, assembled at run time, K.4.2) never
    reaches a cell, a picker or the CLI line as raw control text."""
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.viewer import ExecutionsModel

    hostile = "bank" + chr(0x202E) + "ing" + chr(10) + "x"
    path = corpus_copy.with_name("mini.partial") / "executions.jsonl"
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(raw)
        row["cell"] = {"suite": hostile}
        row["facets"] = {"outcome": [{"claim": "attack_succeeded", "holds": True, "name": "security", "value": True}]}
        lines.append(json.dumps(row, separators=(",", ":"), sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    table = _table(corpus_copy)
    model = ExecutionsModel()
    model.set_table(table)
    col = next(i for i, c in enumerate(model.columns) if c.key == "cell.suite")
    shown = model.data(model.index(0, col), Qt.ItemDataRole.DisplayRole)
    assert chr(0x202E) not in shown and chr(10) not in shown
    args, _notes = cli_selection(TableFilter(pickers=(("cell.suite", frozenset({hostile})),)))
    from agentprov_gui import text as T

    line = T.line("CLI: " + " ".join(args), 600)
    assert chr(0x202E) not in line and chr(10) not in line
