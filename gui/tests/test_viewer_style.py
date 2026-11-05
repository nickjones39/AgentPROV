"""D-1060: the Viewer restyled in the one style, on the derived mini corpus (``derived_corpus``).

* The **terminal command** cards show what the page shows, built by the code that builds what the GUI runs: the
  Viewer's ``agentprov stats`` is its own selection (D-700, D-706) and its ``agentprov verify`` (while the corpus is
  not verified) the argv the banner's Verify… form builds; the preview's and each execution tab's ``agentprov
  inspect`` follows the open sub-tab and their ``agentprov render`` is the argv the Export Graph… form builds. Copy
  copies those lines.
* The banner shows the corpus's state and verification as badges, with the action.
* Column headers are plain words, the raw field name in the header's tooltip; a hostile value is escaped in the card.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import FORMS, build_spec
from test_viewer import choose_filter, wait

ATTACK = "outcome.attack_succeeded"


@pytest.fixture
def window(qapp: Any, tmp_path: Path, derived_corpus: Path) -> Any:
    from PySide6.QtCore import QSettings, QThreadPool

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.mainwindow import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.corpus_roots = [derived_corpus.parent]
    w = MainWindow(settings, cache_dir=tmp_path / "cache", home=tmp_path / "home")
    w.resize(1400, 900)
    w.show()
    yield w
    QThreadPool.globalInstance().waitForDone(30_000)
    qapp.processEvents()
    w.close()


@pytest.fixture
def dialogs(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every job form opened (modal: recorded, never shown)."""
    from agentprov_gui.ui.jobdialog import JobDialog

    seen: list[Any] = []

    def exec_(self: JobDialog) -> int:
        seen.append(self)
        return 0

    monkeypatch.setattr(JobDialog, "exec", exec_)
    return seen


def _open(qapp: Any, window: Any, corpus: Path, row: int = 0) -> Any:
    v = window.viewer
    v.open_path(corpus)
    wait(qapp, lambda: v.table is not None and v.model.rowCount() == 3)
    v.exec_view.selectRow(row)
    wait(qapp, lambda: v.preview.state == "ready")
    return v


def _tab(pane: Any, title: str) -> None:
    pane.tabs.setCurrentIndex(next(i for i in range(pane.tabs.count()) if pane.tabs.tabText(i) == title))


def _commands(v: Any) -> dict[str, list[str]]:
    """The Viewer's card and the preview's, by command."""
    cards = (*v.commands.commands, *v.preview.command_card.commands)
    return {argv[0]: list(argv) for _comment, argv in cards}


def test_the_card_shows_the_stats_selection_and_copies_it(qapp: Any, window: Any, derived_corpus: Path) -> None:
    from PySide6.QtGui import QGuiApplication

    v = _open(qapp, window, derived_corpus)
    assert _commands(v)["stats"] == v.cli_argv()[0]
    choose_filter(v, ATTACK, "true")
    stats = _commands(v)["stats"]
    assert stats == v.cli_argv()[0] and "outcome.attack_succeeded=true" in stats
    assert "agentprov " + " ".join(stats) in v.commands.plain().replace("'", "")
    assert not v.terminal.is_open() and v.terminal_preview.isVisibleTo(v)  # collapsed: the command's start shows
    assert v.terminal_preview.full_text() == "agentprov " + " ".join(stats)
    v.terminal.set_open(True)
    v.set_search("ex_")  # the id search has no --select: the card says so
    assert v.cli_notes.isVisibleTo(v) and "id search" in v.cli_notes.text()
    v.commands.copy()
    assert QGuiApplication.clipboard().text() == v.commands.plain()
    assert os.path.realpath(derived_corpus) in v.commands.plain()
    v._copy_cli()  # the method Copy CLI ran: the stats line alone
    assert QGuiApplication.clipboard().text() == v.cli_command()[0]


def test_the_inspect_command_follows_the_open_sub_tab(qapp: Any, window: Any, derived_corpus: Path) -> None:
    v = _open(qapp, window, derived_corpus)
    pane = v.preview
    final = os.path.realpath(derived_corpus)
    expected = {"AER": "records", "SEM": "sem", "Raw": "raw", "Register": "summary", "Validation": "summary",
                "Index Row": "summary", "PROV-JSON": "prov", "Graph": "prov"}
    for title, view in expected.items():
        _tab(pane, title)
        inspect = _commands(v)["inspect"]
        assert inspect[inspect.index("--view") + 1] == view, title
        assert inspect[inspect.index("--corpus") + 1] == final and inspect[-1] == pane.ex
        values = {"target": pane.ex, "corpus": final, "view": view, "format": None,
                  "bundle": inspect[inspect.index("--bundle") + 1] if "--bundle" in inspect else None}
        assert inspect == list(build_spec(FORMS["inspect"], values).argv)  # the inspect form's own argv
    # the graph's bundles: core alone is --bundle core; an overlay shown is --bundle all
    _tab(pane, "Graph")
    pane.graph.cb_inf.setChecked(False)
    pane.graph.cb_assess.setChecked(False)
    assert _commands(v)["inspect"][-3:-1] == ["--bundle", "core"]
    pane.graph.cb_assess.setChecked(True)
    assert _commands(v)["inspect"][-3:-1] == ["--bundle", "all"]


def test_the_render_command_is_what_export_graph_runs(qapp: Any, window: Any, derived_corpus: Path,
                                                      dialogs: list[Any]) -> None:
    v = _open(qapp, window, derived_corpus)
    render = _commands(v)["render"]
    v.preview.render_btn.click()
    assert [d.form.name for d in dialogs] == ["render"]
    assert list(dialogs[0].build().argv) == render  # the form Export Graph… opens builds the card's argv
    # a full execution tab shows its own card: inspect for its sub-tab, and the same render
    pane = v.open_row(0)
    wait(qapp, lambda: pane.state == "ready")
    assert pane.command_card is not None and pane.command_card.isVisibleTo(pane)
    full = {argv[0]: list(argv) for _c, argv in pane.command_card.commands}
    assert full["render"] == render and full["inspect"][full["inspect"].index("--view") + 1] == "prov"
    _tab(pane, "AER")
    full = {argv[0]: list(argv) for _c, argv in pane.command_card.commands}
    assert full["inspect"][full["inspect"].index("--view") + 1] == "records"


def test_an_id_of_another_shape_gets_no_command(qapp: Any, window: Any, derived_corpus: Path) -> None:
    """S13: only a well-formed execution id reaches a terminal command (and so the clipboard)."""
    v = _open(qapp, window, derived_corpus)
    pane = v.preview
    pane.ex = "ex_" + chr(27) + "[31m"
    assert pane.terminal_commands() == []


def test_the_notice_verifies_with_the_verify_form(qapp: Any, window: Any, derived_corpus: Path,
                                                  dialogs: list[Any]) -> None:
    v = _open(qapp, window, derived_corpus)
    assert v.state_badge.text() == "Working"
    assert v.banner.isVisibleTo(v) and v.banner_badge.text() == "Not verified" and "Verify" in v.banner_text.text()
    assert v.verify_btn.isVisibleTo(v) and v.needs_verify()
    verify = _commands(v)["verify"]
    v.verify_btn.click()
    assert [d.form.name for d in dialogs] == ["verify"]
    assert list(dialogs[0].build().argv) == verify  # the form Verify… opens builds the card's argv
    # once a verify job of the GUI passed on a sealed corpus: Verified, no action and no verify command
    from dataclasses import replace

    v.verified_lookup = lambda _p: "chain, today, job 1"
    v.summary = replace(v.summary, state="sealed")
    v._show_banner(v.summary)
    v._update_cli()
    assert v.state_badge.text() == "Sealed" and v.banner_badge.text() == "Verified" and not v.verify_btn.isVisibleTo(v)
    assert "verify" not in _commands(v)


def test_headers_are_plain_with_the_field_in_the_tooltip(qapp: Any, window: Any, derived_corpus: Path) -> None:
    from PySide6.QtCore import Qt

    v = _open(qapp, window, derived_corpus)
    headers = {v.model.headerData(c, Qt.Orientation.Horizontal): v.model.headerData(
        c, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole) for c in range(v.model.columnCount())}
    assert "Record type" in headers and "unit" in headers["Record type"]
    assert "Suite" in headers and "cell.suite" in headers["Suite"]
    assert "benign" in next(t for h, t in headers.items() if "Attack succeeded" in h)  # D-706's rule is kept
    details = v.show_details()  # D-1060: the corpora table's facts are in Corpus Details
    assert [details.facts.names[k].text() for k in list(details.facts.names)[:3]] == ["Corpus", "State", "Corpus id"]
    assert "content_digest" in details.facts.names["Content digest"].toolTip()
    details.close()
    assert v.exec_view.alternatingRowColors() and not v.exec_view.showGrid()


def test_a_hostile_value_is_escaped_in_the_card() -> None:
    from agentprov_gui.ui.viewer import display_argv

    hostile = "bank" + chr(0x202E) + "ing" + chr(10) + "x"
    shown, escaped = display_argv(["stats", "--select", f"cell.suite={hostile}"])
    assert escaped and all(chr(0x202E) not in a and chr(10) not in a for a in shown)
    assert display_argv(["stats", "--corpus", "/tmp/c"]) == (["stats", "--corpus", "/tmp/c"], False)
