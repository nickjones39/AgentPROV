"""The Settings window in the form style (D-1060; Settings.dc.html): a sidebar of grouped panes, pages that never scroll
sideways, rows hidden when a choice makes them moot, and each pane's terminal command card, which shows exactly the
commands OK runs (built by the same function: :func:`settings_client.plan`, the Prices and Estimate panes' ``pending``,
the keychain's argv), never a key's value."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest


def wait(app: Any, cond: Any, timeout: float = 30) -> None:
    from PySide6.QtCore import QEventLoop

    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


def _settle(qapp: Any) -> None:
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(60_000)
    qapp.processEvents()


def _dialog(tmp_path: Path, checkout: Path | None = None, pane: str | None = None) -> Any:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    settings.checkout = checkout
    return SettingsDialog(settings, pane=pane)


def _argvs(pane: Any) -> list[list[str]]:
    return [list(argv) for _comment, argv in pane.command.commands]


def test_the_sidebar_groups_every_pane(qapp: Any, tmp_path: Path) -> None:
    from agentprov_gui.ui.dialogs import GROUPS

    dlg = _dialog(tmp_path, pane="Assistant")
    rows = [dlg.sidebar.item(i).text() for i in range(dlg.sidebar.count())]
    assert rows == ["APP", "General", "Appearance", "Viewer", "Updates", "RUNNING", "Jobs", "Compute", "Dev Runs", "CI",
                    "MODELS AND COSTS", "Keys", "Local Models", "Prices", "Estimate", "Assistant", "RELEASE", "Zenodo"]
    assert dlg.titles == [t for _g, titles in GROUPS for t in titles] and len(dlg.titles) == 14
    assert dlg.current_pane() == "Assistant" and dlg.stack.currentWidget() is dlg.panes[-2]
    for title in dlg.titles:
        dlg.show_pane(title)
        assert dlg.current_pane() == title
    dlg.show_pane("APP")  # a group heading is not a pane
    assert dlg.current_pane() == "Zenodo"
    dlg.deleteLater()
    _settle(qapp)


def test_no_page_scrolls_sideways_at_900_px(qapp: Any, tmp_path: Path, fake_checkout: Path) -> None:
    from agentprov_gui.ui.forms import FormPage

    dlg = _dialog(tmp_path, fake_checkout)
    _settle(qapp)
    dlg.resize(900, 700)
    dlg.show()
    seen = 0
    for title in dlg.titles:
        dlg.show_pane(title)
        qapp.processEvents()
        page = next(p for p in dlg.stack.currentWidget().findChildren(FormPage)) \
            if not isinstance(dlg.stack.currentWidget(), FormPage) else dlg.stack.currentWidget()
        assert page.horizontalScrollBar().maximum() == 0, title
        assert page.widget().width() <= page.viewport().width(), title
        seen += 1
    assert seen == 14
    dlg.close()
    dlg.deleteLater()


def test_moot_rows_are_hidden(qapp: Any, tmp_path: Path, fake_checkout: Path) -> None:
    dlg = _dialog(tmp_path, fake_checkout)
    _settle(qapp)
    compute = dlg.panes[1]
    assert all(not row.isHidden() for row in compute.queue_rows)
    compute.queue.setChecked(False)  # the reservation and the budgets apply only to queued jobs
    assert all(row.isHidden() for row in compute.queue_rows)
    qapp.processEvents()  # the card follows the change
    assert "compute.queue_heavy" in json.dumps(_argvs(compute))
    dlg.deleteLater()


def _cli(stored: dict[str, Any], writes: list[list[str]]) -> Any:
    def cli(argv: Any) -> tuple[int, bytes, bytes]:
        argv = list(argv)
        if argv[:2] == ["settings", "list"]:
            return 0, json.dumps({"values": stored}).encode(), b""
        writes.append(argv)
        return 0, b"", b""

    return cli


def test_the_command_card_is_what_ok_runs(qapp: Any) -> None:
    from agentprov_gui import settings_client
    from agentprov_gui.ui.settings_panes import COPY_NAME, NOT_READ, ComputePane, JobsPane

    writes: list[list[str]] = []
    jobs = JobsPane(None, cli=_cli({"jobs.retention_days": 30}, writes))
    assert jobs.command.commands == [] and NOT_READ in jobs.command.body.text()  # nothing read yet: nothing to run
    wait(qapp, lambda: jobs.loaded is not None)
    assert _argvs(jobs) == [settings_client.list_argv("jobs.")]  # nothing changed: the stored values' command
    jobs.retention.setValue(300)
    jobs.retention_days.setValue(90)  # back to the default: unset
    jobs.continue_on_failure.setChecked(True)
    wait(qapp, lambda: len(jobs.command.commands) == 3)
    shown = _argvs(jobs)
    assert shown == [["settings", "unset", "jobs.retention_days"], ["settings", "set", "jobs.continue_on_failure",
                                                                    "true"], ["settings", "set", "jobs.retention", "300"]]
    assert jobs.command.copy_button.accessibleName() == COPY_NAME
    assert jobs.command.plain().splitlines()[1] == "agentprov settings unset jobs.retention_days"
    jobs.save()
    assert writes == shown  # the card is exactly what OK ran
    compute = ComputePane(None, cli=_cli({}, writes := []))
    wait(qapp, lambda: compute.loaded is not None)
    compute.preset.setCurrentText("Named preset")
    compute.preset_name.setText("studio")
    compute.cpu_budget.setText("abc")  # refused by the form: neither shown nor written
    compute.jobs["import"].setValue(8)
    qapp.processEvents()
    shown = _argvs(compute)
    assert shown == [["settings", "set", "compute.jobs.import", "8"], ["settings", "set", "compute.preset", "studio"]]
    compute.save()
    assert writes == shown
    for pane in (jobs, compute):
        pane.deleteLater()


def test_the_estimate_and_prices_cards_are_what_ok_runs(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import livepanes

    calls: list[list[str]] = []
    prices = {"format": "agentprov-prices-list/0.1", "stale_days": 60, "shipped": {"rows": 1, "as_of": "2026-10-21"},
              "refreshed": {"rows": 0, "as_of": None}, "endpoints": [],
              "overrides": [{"key": "openrouter:vendor/old", "model": "openrouter:vendor/old", "provider": "override",
                             "input": "1", "output": "2", "cached_input": None, "source": "x", "as_of": "2026-10-01",
                             "stale": False}]}

    def call(_cli: Any, argv: list[str], **_kw: Any) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[:2] == ["settings", "list"]:
            return 0, json.dumps({"values": {"estimate.default.calls_p50": 8}}).encode(), b""
        if argv[:2] == ["prices", "list"]:
            return 0, json.dumps(prices).encode(), b""
        return 0, b"", b""

    monkeypatch.setattr(livepanes, "call", call)
    monkeypatch.setattr(livepanes, "submit", lambda _o, fn, done, _f=None: done(fn(None)))
    estimate = livepanes.EstimatePane(None)
    assert _argvs(estimate) == [list(livepanes.SETTINGS_LIST)]
    estimate.spins["seconds_p90"].setValue(200)
    estimate.auto_refresh.setChecked(False)
    qapp.processEvents()
    shown = _argvs(estimate)
    assert shown == [["settings", "set", "estimate.default.seconds_p90", "200"],
                     ["settings", "set", "prices.auto_refresh", "false"]]
    calls.clear()
    estimate.save()
    assert calls == shown
    pane = livepanes.PricesPane(None)
    assert pane.isEnabled() and pane.table.rowCount() == 1
    pane.table.removeRow(0)
    pane._add(["openrouter:vendor/new", "3", "", "4", "", "2026-10-22"])
    qapp.processEvents()
    shown = _argvs(pane)
    assert shown == [["prices", "unset", "openrouter", "vendor/old"],
                     ["prices", "set", "openrouter", "vendor/new", "--input", "3", "--output", "4", "--as-of",
                      "2026-10-22"]]
    calls.clear()
    pane.save()
    assert calls == shown
    for w in (estimate, pane):
        w.deleteLater()


def test_the_price_overrides_columns_fit_the_table_with_their_headers(qapp: Any,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """Each price column (As of included) is as wide as its header, and the model column takes what they leave, so at
    the Settings pane's width no header runs past the table's edge (As of did once the others were widened)."""
    from agentprov_gui.ui import livepanes

    monkeypatch.setattr(livepanes, "call", lambda *_a, **_k: (1, b"", b""))
    monkeypatch.setattr(livepanes, "submit", lambda _o, fn, done, _f=None: done(fn(None)))
    pane = livepanes.PricesPane(None)
    pane.resize(700, 700)
    pane.show()
    qapp.processEvents()
    header = pane.table.horizontalHeader()
    widths = [header.sectionSize(c) for c in range(header.count())]
    assert sum(widths) <= pane.table.viewport().width()
    for c in range(1, header.count()):
        assert widths[c] >= header.sectionSizeFromContents(c).width(), pane.COLUMNS[c]
    assert widths[0] >= 120
    pane.deleteLater()


def test_the_keys_card_is_the_keychain_argv_and_never_holds_a_value(qapp: Any,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from agentprov_gui.jobs.manager import CliLocator
    from agentprov_gui.live import keychain
    from agentprov_gui.ui import livepanes

    ran: list[list[str]] = []

    def run(cli: Any, argv: Any, *, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
        ran.append(["keys", *argv])
        return subprocess.CompletedProcess(argv, 0, b'{"allowed": true, "backend": "FakeRing", "keys": []}', b"")

    monkeypatch.setattr(keychain, "_run", run)
    secret = "sk-" + "x" * 12  # a value as typed; assembled so no key shape sits in the source
    monkeypatch.setattr(livepanes.StoreKeyDialog, "exec", lambda self: (self.field.setText(secret), 1)[1])
    monkeypatch.setattr(livepanes, "ask", lambda *a, **k: True)
    pane = livepanes.KeysPane(None, None)
    pane.cli = CliLocator(None, ("agentprov",))
    assert _argvs(pane) == [["keys", "status", "--format", "json"]]  # no key chosen: the status only
    pane.table.setCurrentCell(0, 0)
    name = pane.names[0]
    shown = _argvs(pane)
    assert shown[1:] == [["keys", "set", name, "--stdin"], ["keys", "delete", name, "--yes"]]
    pane.store_selected()
    pane.delete_selected()
    assert shown[0] in ran and shown[1] in ran and shown[2] in ran  # the card's commands are the ones run
    assert all(secret not in " ".join(argv) for argv in ran + _argvs(pane))
    assert secret not in pane.command.plain() and secret not in pane.command.body.text()
    pane.deleteLater()


def test_about_is_in_the_same_style(qapp: Any) -> None:
    from agentprov_gui.about import REPOSITORY, default_checkout
    from agentprov_gui.ui.dialogs import AboutDialog
    from agentprov_gui.ui.forms import FormRow, FormSection

    dlg = AboutDialog(default_checkout())
    assert [s.accessibleName() for s in dlg.findChildren(FormSection)] == ["Versions", "Updates", "Formats",
                                                                          "Project", "Third-party notices"]
    rows = {r.accessibleName(): r for r in dlg.findChildren(FormRow)}
    assert "Execution Record" in rows["Format: aer"].label.toolTip() and rows["Repository"].field.text() == REPOSITORY
    assert len([n for n in rows if n.startswith("Format: ")]) == len(dlg.facts.formats)
    dlg.deleteLater()
