"""Run Live in the one form style (D-1060): rows per transport, the scope, the summary and quote panel, the terminal
command card (the exact argv Start hands Runs), the cost cap from the quote, the remembered disclosures, no
horizontal scrolling, and the daily price refresh (D-1062). The gates themselves are tested in test_g3_live.py."""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.manager import CliLocator, JobManager
from test_g3_live import CATALOGUE, FAKE, fake_run, wait

ENDPOINTS = ('[endpoints.openrouter]\nbase_url = "https://openrouter.ai/api/v1"\napi_key_env = "OPENROUTER_API_KEY"\n'
             'local = false\n')
CAPS = frozenset({"--max-calls", "--max-cost-usd", "--price-in", "--price-out"})
QUOTE = {"usd_p50": "4.10", "usd_p90": "9.80", "calls_p50": 960, "calls_p90": 1800.0, "tokens_in_p50": 1_100_000,
         "tokens_in_p90": 2_000_000, "tokens_out_p50": 36_000, "tokens_out_p90": 84_000, "seconds_p50": 600,
         "seconds_p90": 1320, "seconds_serial_p50": 600, "seconds_serial_p90": 1320, "jobs": 1, "cells": 4,
         "p50_aggregation": "sum of per-cell medians", "p90_aggregation": "upper (sum of per-cell 90th percentiles)",
         "basis": {"priors": "shipped", "family_specific": False, "family": None, "executions": 75, "corpora": [],
                   "token_basis": "chars/4", "price_source": "openrouter", "price_as_of": "2026-10-21",
                   "discounts_assumed": False, "estimate_only": True}}  # agentprov estimate's final shape (D-1062)


def quoting_run(calls: list[list[str]], quote: dict[str, Any] | None, *, status: str = "supported") -> Any:
    """``fake_run`` with a live status that admits real runs and, for a real model, the estimate's ``quote``."""
    base = fake_run(calls)

    def run(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if argv[0] == "info":
            calls.append(list(argv))
            return 0, json.dumps({"source_id": argv[1], "parts": [{"live": status}]}).encode(), b""
        code, out, err = base(manager, argv, **kw)
        if argv[0] == "estimate" and "--llm-script" not in argv and quote is not None:
            doc = json.loads(out)
            doc["quote"] = quote
            out = json.dumps(doc).encode()
        return code, out, err

    return run


def _dialog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, scripted: bool, quote: dict[str, Any] | None = None,
            **kw: Any) -> Any:
    from agentprov_gui.live import keychain
    from agentprov_gui.live.plan import ENDPOINTS_REL
    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import DEV_SCRIPT, RunLiveDialog

    repo = tmp_path / "repo"
    path = repo / ENDPOINTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ENDPOINTS)
    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(True, "FakeRing"))
    monkeypatch.setattr(keychain, "present", lambda cli, names: dict.fromkeys(names, True))
    calls: list[list[str]] = []
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    preset = RunSettings(campaign="t", script=str(DEV_SCRIPT), suites=("banking",), attacks=("direct",),
                         scripted=scripted, model="" if scripted else "openrouter",
                         model_id="" if scripted else "vendor/m", containment="" if scripted else "vm")
    dlg = RunLiveDialog(m, home=tmp_path / "home", checkout=repo, preset=preset,
                        run=kw.pop("run", None) or quoting_run(calls, quote), cli_options=kw.pop("cli_options", CAPS),
                        **kw)
    dlg.calls = calls
    return dlg


def _settle(qapp: Any, dlg: Any) -> None:
    wait(qapp, lambda: "agentdojo" in dlg.catalogues and "agentdojo" in dlg.live_status and dlg.prices is not None)
    dlg.refresh_estimate()
    wait(qapp, lambda: dlg.current_estimate() is not None)


def test_rows_show_only_for_the_chosen_transport(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 3: the script row for scripted runs; endpoint, model, price, key and containment for a real model."""
    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    dlg.show()
    qapp.processEvents()
    assert dlg.mode.currentIndex() == 0 and dlg.script_row.isVisible()
    assert not any(row.isVisible() for row in dlg.real_rows) and dlg.model_section.note.isVisible()
    assert dlg.caps_box.isHidden()
    dlg.mode.setCurrentIndex(1)
    qapp.processEvents()
    assert not dlg.script_row.isVisible() and all(row.isVisible() for row in dlg.real_rows)
    assert not dlg.model_section.note.isVisible() and not dlg.caps_box.isHidden()  # an API endpoint: the limits
    assert dlg.settings().model == "openrouter" and not dlg.settings().scripted
    dlg.mode.setCurrentIndex(0)
    assert dlg.script_row.isVisible() and dlg.caps_box.isHidden()
    dlg.close()


def test_the_hidden_transport_rows_never_reach_the_argv(qapp: Any, tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-NG-6 (rule 3): a real-model preset switched to Scripted runs and estimates without the hidden model id and
    containment; switched back, the real run has them again."""
    dlg = _dialog(tmp_path, monkeypatch, scripted=False)
    _settle(qapp, dlg)
    real = dlg.run_spec().argv
    assert real[real.index("--model-id") + 1] == "vendor/m" and real[real.index("--containment") + 1] == "vm"
    dlg.mode.setCurrentIndex(0)  # Scripted
    qapp.processEvents()
    for argv in (dlg.run_spec().argv, dlg._estimate_argv()):
        assert "--llm-script" in argv
        assert "--model-id" not in argv and "--containment" not in argv and "--model" not in argv
    dlg.mode.setCurrentIndex(1)  # Real model again
    qapp.processEvents()
    assert dlg.run_spec().argv == real
    dlg.close()


def test_the_command_card_is_the_argv_start_hands_runs(qapp: Any, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import runlive
    from agentprov_gui.ui.forms import command_text

    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    _settle(qapp, dlg)
    ((comment, shown),) = dlg.command_card.commands
    assert comment == "" and shown[0] == "run" and "--llm-script" in shown
    monkeypatch.setattr(runlive, "confirm", lambda _p, spec, _a: spec)
    dlg._start(preflight=False)
    assert dlg.start is not None and dlg.start.spec.argv == shown
    assert dlg.command_card.plain() == command_text(shown)
    dlg.close()


def test_a_real_model_card_shows_the_quote_command_and_the_consented_run(qapp: Any, tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Both commands come from the builders the dialog runs; the key's value is never in either (``--keychain``)."""
    secret = "sk-" + "or-" + "z" * 30
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    _settle(qapp, dlg)
    dlg.max_calls.setValue(5000)
    dlg.max_cost.setValue(10)
    dlg.refresh_estimate()
    wait(qapp, lambda: dlg.current_estimate() is not None)
    (c1, quote_argv), (c2, run_argv) = dlg.command_card.commands
    assert (c1, c2) == ("the quote", "the run")
    assert quote_argv == dlg._estimate_argv() == tuple([c for c in dlg.calls if c[0] == "estimate"][-1])
    assert "--keychain" in run_argv and "--i-consent-to-api-costs" in run_argv
    monkeypatch.setattr(dlg, "confirm_costs", lambda s, preflight: True)
    dlg._start(preflight=False)
    assert dlg.start is not None and dlg.start.spec.argv == run_argv
    assert all(secret not in a for a in (*quote_argv, *run_argv)) and secret not in dlg.command_card.plain()
    dlg.close()


def test_the_quote_panel_shows_the_clis_figures_and_names_a_fallback(qapp: Any, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    _settle(qapp, dlg)
    assert dlg.summary_heading.text() == "QUOTE FOR THIS RUN"
    assert dlg.big.text() == "$4.10"
    assert dlg.sub.text() == "Upper estimate: $9.80 (sum of per-cell 90th percentiles)"  # not the run's 90th percentile
    assert dlg.facts.value("cells") == "4" and dlg.facts.value("calls") == "960 – 1,800"
    assert dlg.facts.value("tokens_in") == "1.1 M – 2.0 M" and dlg.facts.value("tokens_out") == "36.0 k – 84.0 k"
    assert dlg.facts.value("time") == "10 – 22 min" and dlg.facts.names["time"].text() == "Time at 1 trace"
    assert dlg.estimate_only.text().startswith("Estimate only") and not dlg.estimate_only.isHidden()
    basis = dlg.basis.text()
    assert "No recorded run of vendor/m yet" in basis and "figures for all models" in basis and "75 recorded" in basis
    assert "the shipped priors" in basis and "characters / 4" in basis and "OpenRouter's list price, as of 2026-10-21" \
        in basis and "Batch and cache discounts are not assumed." in basis
    # D-1090: a quote without suggested caps (an older CLI) fills nothing: the caps are typed, as before
    dlg.use_quote_upper()
    assert dlg.max_cost.number() is None and dlg.max_calls.number() is None
    assert dlg.cap_rows["cost"].caption.text() == "Enter it yourself: this agentprov suggests no caps"
    dlg.close()


def test_a_family_specific_basis_says_so_and_a_missing_quote_falls_back(qapp: Any, tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    own = {**QUOTE, "basis": {**QUOTE["basis"], "priors": "local", "family_specific": True, "executions": 1285,
                              "family": "deepseek-chat", "corpora": ["c1", "c2"], "token_basis": "usage",
                              "discounts_assumed": True}}
    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=own)
    _settle(qapp, dlg)
    basis = dlg.basis.text()
    assert "From 1,285 recorded executions of deepseek-chat in your sealed corpora (2 of yours)." in basis
    assert "all models" not in basis and "usage recorded in past runs" in basis and "cache rate" in basis
    dlg.close()
    part = {**QUOTE, "basis": {**QUOTE["basis"], "priors": "mixed", "family": "deepseek-chat"}}
    mixed = _dialog(tmp_path, monkeypatch, scripted=False, quote=part)
    _settle(qapp, mixed)
    assert mixed.basis.text().startswith("Partly deepseek-chat's own: where no run of it is recorded, the figures for "
                                         "all models are used (75 recorded executions in your sealed corpora and the "
                                         "shipped priors).")
    mixed.close()
    old = _dialog(tmp_path, monkeypatch, scripted=False, quote=None)  # an older CLI: no quote object
    _settle(qapp, old)
    e = old.current_estimate()
    assert e.quote is None and old.big.text() == "$0.1000"  # the estimate's own cost_p50
    assert old.facts.value("tokens_in") == "—" and "does not say how many recorded executions" in old.basis.text()
    assert "not stated" in old.basis.text()  # discounts: unknown, never claimed
    old.close()


def test_the_full_benchmark_is_ticking_everything(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui.runlive import CHOOSE, FULL

    cat = {**CATALOGUE, "suites": [*CATALOGUE["suites"], {**CATALOGUE["suites"][0], "name": "slack"}]}
    base = quoting_run([], None, status="planned")

    def run(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if "--catalogue" in argv and argv[-1] == "agentdojo":
            return 0, json.dumps(cat).encode(), b""
        return base(manager, argv, **kw)

    dlg = _dialog(tmp_path, monkeypatch, scripted=True, run=run)
    wait(qapp, lambda: "agentdojo" in dlg.catalogues)
    dlg.user_tasks.setText("0-2")
    dlg.scope.setCurrentIndex(FULL)
    assert dlg.suites_row.isHidden() and not dlg.includes_row.isHidden()
    assert dlg.includes.text() == "2 suites · 1 attack · benign cells"  # the refused attack is not offered
    full = dlg.run_spec().argv
    dlg.scope.setCurrentIndex(CHOOSE)
    dlg.user_tasks.setText("")
    dlg.suites.set_checked(dlg.suites.selectable())
    dlg.attacks.set_checked([c.key for c in dlg.attacks.choices])  # a refused attack cannot be ticked
    dlg.benign.setCurrentText("include")
    assert dlg.run_spec().argv == full
    assert full[full.index("--suite") + 1] == "banking,slack" and full[full.index("--attack") + 1] == "direct"
    dlg.close()


def test_disclosures_are_remembered_per_screen(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    store = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    dlg = _dialog(tmp_path, monkeypatch, scripted=True, store=store)
    assert not dlg.advanced.is_open() and not dlg.tasks.is_open()  # collapsed by default
    dlg.advanced.set_open(True)
    dlg.close()
    again = _dialog(tmp_path, monkeypatch, scripted=True, store=store)
    assert again.advanced.is_open() and not again.tasks.is_open()
    assert store.value("forms/disclosure/run-live/advanced") == "true"
    again.close()


def test_run_live_never_scrolls_sideways(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.forms import COLUMN_MAX

    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    dlg.advanced.set_open(True)
    dlg.tasks.set_open(True)
    dlg.resize(1000, 800)
    dlg.show()
    _settle(qapp, dlg)
    qapp.processEvents()
    page = dlg.page
    assert page.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert page.widget().minimumSizeHint().width() <= page.viewport().width()
    assert page.column.width() <= COLUMN_MAX
    assert dlg.summary.widget().minimumSizeHint().width() <= dlg.summary.viewport().width()
    dlg.close()


def test_plan_by_suite_shows_the_estimate_lines(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    _settle(qapp, dlg)
    dlg.show_plan()
    assert dlg.plan_dialog is not None and dlg.details.parent() is dlg.plan_dialog
    assert "By suite:" in dlg.details.toPlainText()
    dlg.plan_dialog.close()
    dlg.close()


# ---------------------------------------------------------------------------------------------- D-1062
def test_prices_status_is_read_defensively() -> None:
    from agentprov_gui.live import pricerefresh as P

    when = dt.datetime(2026, 11, 4, 20, 14, tzinfo=dt.UTC)
    doc = {"format": "agentprov-prices-status/0.1", "auto_refresh": True, "refresh_due": False,
           "openrouter_snapshot": {"as_of": "2026-11-04", "written_at": "2026-11-04T20:14:00Z", "rows": 3}}
    assert P.parse_status(0, json.dumps(doc).encode()) == P.PricesStatus(when, False, True, "2026-11-04")
    never = {"format": "agentprov-prices-status/0.1", "openrouter_snapshot": None, "refresh_due": True,
             "auto_refresh": True}
    assert P.parse_status(0, json.dumps(never).encode()) == P.PricesStatus(None, True, True, None)
    assert P.parse_status(0, b'{"format": "x"}') is None  # not the status document
    assert P.parse_status(2, b"") is None and P.parse_status(0, b"not json") is None
    today = dt.date(2026, 11, 5)
    due = P.PricesStatus(None, True, True)
    assert P.due(due, attempted="", today=today)
    assert not P.due(due, attempted="2026-11-05", today=today)  # started today already
    assert not P.due(P.PricesStatus(None, True, False), attempted="", today=today)  # prices.auto_refresh is off
    assert not P.due(P.PricesStatus(when, False, True), attempted="", today=today)  # written today: not due
    assert not P.due(None, attempted="", today=today)  # an older CLI: nothing is started
    now = dt.datetime.now(dt.UTC)
    assert P.local_time_text(now).startswith("today ")
    assert P.local_time_text(when, today=dt.date(2030, 1, 1)).count(" ") >= 3


def _status(written: str | None, *, due: bool, auto: bool = True) -> dict[str, Any]:
    snap = None if written is None else {"as_of": written[:10], "written_at": written, "rows": 3}
    return {"format": "agentprov-prices-status/0.1", "openrouter_snapshot": snap, "refresh_due": due,
            "auto_refresh": auto}


def _refresh_dialog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: dict[str, Any] | None,
                    record: list[str]) -> Any:
    calls: list[list[str]] = []
    base = quoting_run(calls, QUOTE)

    def run(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if argv[:2] == ["prices", "status"]:
            calls.append(list(argv))
            return (0, json.dumps(status).encode(), b"") if status is not None else (2, b"", b"no such command")
        return base(manager, argv, **kw)

    def remember(value: str | None) -> str:
        if value is not None:
            record.append(value)
        return record[-1] if record else ""

    dlg = _dialog(tmp_path, monkeypatch, scripted=False, run=run, daily_refresh=True, refresh_record=remember)
    dlg.calls = calls
    return dlg


@pytest.mark.parametrize("outcome", [0, 3])
def test_the_daily_price_refresh_starts_a_job_once_and_never_blocks(qapp: Any, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch,
                                                                     outcome: int) -> None:
    from types import SimpleNamespace

    jobs: dict[str, Any] = {}
    spawned: list[tuple[str, ...]] = []

    def spawn(spec: Any, **_kw: Any) -> Any:
        spawned.append(spec.argv)
        job = SimpleNamespace(job_id="j1", state="running", exit_code=None, file=lambda name: tmp_path / "err.txt")
        jobs["j1"] = job
        return job

    (tmp_path / "err.txt").write_bytes(b"agentprov: error [prices.fetch]: the host did not answer\n")
    record: list[str] = []
    dlg = _refresh_dialog(tmp_path, monkeypatch, _status("2020-01-01T00:00:00Z", due=True), record)
    monkeypatch.setattr(dlg.manager, "spawn", spawn)  # before the event loop delivers the status (in the pool)
    monkeypatch.setattr(dlg.manager, "refresh", lambda: list(jobs.values()))
    monkeypatch.setattr(dlg.manager, "jobs", jobs)
    wait(qapp, lambda: bool(spawned))
    assert spawned == [("prices", "refresh", "--allow-network", "--if-stale")]
    assert record == [dt.date.today().isoformat()]
    assert dlg.isEnabled() and "Refreshing prices" in dlg.prices_line
    lists = sum(1 for c in dlg.calls if c[:2] == ["prices", "list"])
    jobs["j1"].state, jobs["j1"].exit_code = "ended", outcome
    wait(qapp, lambda: "Refreshing" not in dlg.prices_line)
    if outcome == 0:
        assert dlg.prices_line.startswith("Prices refreshed ")
        wait(qapp, lambda: sum(1 for c in dlg.calls if c[:2] == ["prices", "list"]) > lists)  # then re-estimated
    else:
        assert "refresh failed: agentprov: error [prices.fetch]: the host did not answer" in dlg.prices_line
        assert dlg.prices_line.startswith("Using prices of 2026-10-21")
    spawned.clear()
    dlg._daily_refresh()  # the same day again: nothing is started
    wait(qapp, lambda: sum(1 for c in dlg.calls if c[:2] == ["prices", "status"]) >= 2)
    qapp.processEvents()
    assert spawned == []
    dlg.refresh_timer.stop()
    dlg.close()


def test_a_closed_dialog_stops_its_refresh_and_starts_nothing(qapp: Any, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-NG-2: Cancel while the daily refresh runs stops the polls; the job's end then runs no prices list, prices
    status or estimate (``--keychain``) for the closed window. The job list is refreshed on the UI thread only."""
    import threading
    import time
    from types import SimpleNamespace

    jobs: dict[str, Any] = {}
    spawned: list[tuple[str, ...]] = []
    threads: list[bool] = []

    def spawn(spec: Any, **_kw: Any) -> Any:
        spawned.append(spec.argv)
        jobs["j1"] = SimpleNamespace(job_id="j1", state="running", exit_code=None, file=lambda name: tmp_path / "e")
        return jobs["j1"]

    def refresh() -> list[Any]:
        threads.append(threading.current_thread() is threading.main_thread())
        return list(jobs.values())

    record: list[str] = []
    dlg = _refresh_dialog(tmp_path, monkeypatch, _status("2020-01-01T00:00:00Z", due=True), record)
    monkeypatch.setattr(dlg.manager, "spawn", spawn)
    monkeypatch.setattr(dlg.manager, "refresh", refresh)
    monkeypatch.setattr(dlg.manager, "jobs", jobs)
    wait(qapp, lambda: bool(spawned) and dlg.refresh_timer.isActive())
    wait(qapp, lambda: bool(threads))  # polled at least once
    end = time.monotonic() + 1.5
    wait(qapp, lambda: time.monotonic() > end)  # the opening estimate settles
    dlg.reject()
    assert not dlg.refresh_timer.isActive() and not dlg.timer.isActive()
    before, polls = len(dlg.calls), len(threads)
    jobs["j1"].state, jobs["j1"].exit_code = "ended", 0
    end = time.monotonic() + 2.5
    wait(qapp, lambda: time.monotonic() > end)
    assert dlg.calls[before:] == [] and len(threads) == polls
    assert all(threads)


def test_no_refresh_when_the_prices_were_refreshed_today(qapp: Any, tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    now = dt.datetime.now(dt.UTC).isoformat()
    record: list[str] = []
    dlg = _refresh_dialog(tmp_path, monkeypatch, _status(now, due=False), record)
    spawned: list[Any] = []
    monkeypatch.setattr(dlg.manager, "spawn", lambda spec, **kw: spawned.append(spec))
    wait(qapp, lambda: dlg.prices_line.startswith("Prices refreshed today"))
    assert spawned == [] and record == []
    dlg.close()


def test_the_refresh_switch_is_the_cli_setting(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings › Estimate's "Refresh prices once a day when Run Live opens" is ``prices.auto_refresh`` (unset: on),
    written through agentprov settings; the GUI keeps only the date it last started a refresh."""
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import livepanes

    calls: list[list[str]] = []

    def call(_cli: Any, argv: list[str], **_kw: Any) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[:2] == ["settings", "list"]:
            return 0, json.dumps({"format": "agentprov-settings/0.1", "values": {}}).encode(), b""
        return 0, b"", b""

    monkeypatch.setattr(livepanes, "call", call)
    monkeypatch.setattr(livepanes, "submit", lambda _o, fn, done, _f=None: done(fn(None)))
    pane = livepanes.EstimatePane(None)
    assert pane.auto_refresh.isChecked() and livepanes.EstimatePane.KEYS["auto_refresh"] == "prices.auto_refresh"
    pane.save()
    assert calls == [["settings", "list", "--format", "json"]]  # nothing changed: nothing written
    pane.auto_refresh.setChecked(False)
    pane.save()
    assert calls[-1] == ["settings", "set", "prices.auto_refresh", "false"]
    pane.close()
    s = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert s.prices_refresh_attempted == ""
    s.prices_refresh_attempted = "2026-11-05"
    assert s.prices_refresh_attempted == "2026-11-05"


def test_build_cost_figures_starts_priors_build_and_asks_again(qapp: Any, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from agentprov_gui.ui import runlive

    dlg = _dialog(tmp_path, monkeypatch, scripted=False, quote=QUOTE)
    _settle(qapp, dlg)
    jobs: dict[str, Any] = {}
    seen: list[Any] = []

    def spawn(spec: Any, **_kw: Any) -> Any:
        seen.append(spec)
        jobs["p1"] = SimpleNamespace(job_id="p1", state="running", exit_code=None, file=lambda n: tmp_path / "none")
        return jobs["p1"]

    monkeypatch.setattr(runlive, "confirm", lambda _p, spec, _a: spec)
    monkeypatch.setattr(dlg.manager, "spawn", spawn)
    monkeypatch.setattr(dlg.manager, "refresh", lambda: list(jobs.values()))
    monkeypatch.setattr(dlg.manager, "jobs", jobs)
    dlg.build_priors()
    wait(qapp, lambda: bool(seen))
    assert seen[0].argv == ("priors", "build", "--jobs", "8") and seen[0].tier == "R1"
    assert not dlg.build_priors_btn.isEnabled() and "Building cost figures" in dlg.priors_status.text()
    n = sum(1 for c in dlg.calls if c[0] == "estimate")
    jobs["p1"].state, jobs["p1"].exit_code = "ended", 0
    wait(qapp, lambda: dlg.build_priors_btn.isEnabled())
    assert dlg.priors_status.text().startswith("Cost figures built")
    wait(qapp, lambda: sum(1 for c in dlg.calls if c[0] == "estimate") > n)  # the quote is asked again
    dlg.close()


def test_parse_quote_drops_malformed_fields() -> None:
    from decimal import Decimal

    from agentprov_gui.live.plan import parse_quote

    q = parse_quote({"usd_p50": "1.5", "usd_p90": -2, "calls_p50": "many", "cells": True,
                     "basis": {"priors": "elsewhere", "family_specific": "yes", "executions": [1, 2, 3],
                               "family": "<b>x</b>"}})
    assert q is not None and q.usd_p50 == Decimal("1.5") and q.usd_p90 is None and q.calls_p50 is None
    assert q.cells is None and q.basis.priors is None and q.basis.family_specific is None
    assert q.basis.executions == 3 and q.basis.family == "<b>x</b>"  # a label, shown escaped through text.line
    assert parse_quote(None) is None and parse_quote([]) is None


def test_start_stagger_and_retry_inconsistent_reach_the_argv(qapp: Any, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """The Run section's Start stagger (--start-stagger) and Retry inconsistent units (--retry-inconsistent): left
    out while unset, in the run and the command card once set, each with its tooltip, and neither repeated under
    Other run options."""
    from agentprov_gui.ui.forms import command_text

    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    _settle(qapp, dlg)
    argv = dlg.run_spec().argv
    assert "--start-stagger" not in argv and "--retry-inconsistent" not in argv
    assert "start_stagger" not in dlg.more_inputs and "retry_inconsistent" not in dlg.more_inputs
    dlg.jobs.setValue(18)
    dlg.start_stagger.setValue(20)
    dlg.retry_inconsistent.setChecked(True)
    qapp.processEvents()
    argv = dlg.run_spec().argv
    assert argv[argv.index("--jobs") + 1] == "18"
    assert argv[argv.index("--start-stagger") + 1] == "20.0" and "--retry-inconsistent" in argv
    wait(qapp, lambda: "--retry-inconsistent" in dlg.command_card.plain())  # the card follows each change
    ((_comment, shown),) = dlg.command_card.commands  # the terminal command shown is this run's argv
    assert shown == argv
    card = dlg.command_card.plain()
    assert card == command_text(argv)
    assert "--jobs 18" in card and "--start-stagger 20.0" in card and "--retry-inconsistent" in card
    for w in (dlg.start_stagger, dlg.retry_inconsistent):
        assert w.toolTip().strip() or w.property("apvTip")
    dlg.close()


# ---------------------------------------------------------------------------------------------- no blank catalogue
def _captions(group: Any) -> list[str]:
    from agentprov_gui.ui.safe import SafeLabel

    return [lab.text() for lab in group.findChildren(SafeLabel) if not lab.isHidden()]  # a replaced one is hidden


def test_empty_rows_say_why_and_never_stay_blank(qapp: Any) -> None:
    from agentprov_gui.ui.forms import Checklist, ChipGroup, Choice

    for group in (Checklist(name="Suites"), ChipGroup(name="Attacks")):
        group.set_choices([], empty="Loading…")
        assert group.count() == 0 and "Loading…" in _captions(group)
        group.set_choices([Choice("banking", "banking")])
        qapp.processEvents()  # the old caption is deleted later
        assert group.count() == 1 and group.selectable() == ["banking"]
        group.set_choices([])
        assert group.count() == 0  # no empty text: nothing added (the old behaviour)
        group.deleteLater()


def test_a_reopened_run_live_shows_the_last_catalogue_at_once(qapp: Any, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """The catalogue call takes about 2 s (it starts the backend's interpreter): the first Run Live of an app session
    shows "Loading…" in the Suites and Attacks rows until it answers; a later one shows the last good catalogue at
    once, and the call's same answer redraws nothing, so what was ticked meanwhile stays."""
    import threading

    gate = threading.Event()
    base = quoting_run([], None, status="planned")

    def run(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if "--catalogue" in argv:
            gate.wait(30)  # the backend answers only when the test lets it
        return base(manager, argv, **kw)

    first = _dialog(tmp_path, monkeypatch, scripted=True, run=run)
    assert first.suites.count() == 0 and "Loading the suites from the backend…" in _captions(first.suites)
    assert "Loading the attacks…" in _captions(first.attacks)
    gate.set()
    wait(qapp, lambda: isinstance(first.catalogues.get("agentdojo"), type(first.catalogue)) and first.suites.count())
    manager = first.manager
    first.close()

    gate.clear()
    from agentprov_gui.ui.runlive import RunLiveDialog

    again = RunLiveDialog(manager, home=tmp_path / "home", checkout=first.checkout, preset=first.settings(), run=run,
                          cli_options=CAPS)
    assert again.suites.count() == len(CATALOGUE["suites"]) and again.catalogue is not None  # before any answer
    again.suites.set_checked([])  # the user unticks while the call checks the catalogue again
    gate.set()
    wait(qapp, lambda: not again.suites.checked() and _calls_done(again))
    assert again.suites.count() == len(CATALOGUE["suites"]) and not again.suites.checked()  # not redrawn
    shown = first.cat_label.text()
    assert "suites" in shown and again.cat_label.text() == shown  # the answer replaced "Catalogue: loading…"
    again.close()

    def broken(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if "--catalogue" in argv:
            return 3, b"", b"agentprov: error [backend.unavailable]: the backend environment x is not built\n"
        return base(manager, argv, **kw)

    third = RunLiveDialog(manager, home=tmp_path / "home", checkout=first.checkout, preset=first.settings(),
                          run=broken, cli_options=CAPS)
    wait(qapp, lambda: isinstance(third.catalogues.get("agentdojo"), str))
    assert third.catalogue is None and third.suites.count() == 0  # the cached list is not kept over a failure
    assert not any(key[-1] == "agentdojo" for key in manager.catalogue_cache)
    third.close()


def _calls_done(dlg: Any) -> bool:
    from PySide6.QtCore import QThreadPool

    return QThreadPool.globalInstance().activeThreadCount() == 0


# ---------------------------------------------------------------------------------------------- Tune and cost figures
def test_tune_needs_a_model_with_known_weights(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A host preset sizes the concurrency from the model's weights here (run.model.facts_missing without them): a
    scripted run or an API model disables Tune… with the reason; a weight size under Advanced enables it."""
    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import RunLiveDialog

    for scripted in (True, False):  # the scripted transport; an API model (openrouter)
        dlg = _dialog(tmp_path, monkeypatch, scripted=scripted)
        dlg._changed()
        assert not dlg.tune_btn.isEnabled() and "weight size" in dlg.tune_btn.toolTip()
        dlg.close()
    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    preset = replace(dlg.settings(), extra={**dlg.settings().extra, "model_size_gb": 9})
    dlg.close()
    sized = RunLiveDialog(JobManager(tmp_path / "home2", CliLocator(None, (sys.executable, str(FAKE)))),
                          home=tmp_path / "home2", checkout=None, preset=preset, run=quoting_run([], None),
                          cli_options=CAPS)
    assert isinstance(sized, RunLiveDialog) and isinstance(preset, RunSettings)
    sized._changed()
    assert sized.tune_btn.isEnabled() and "weight size" not in sized.tune_btn.toolTip()
    sized.close()


def test_tune_explains_a_missing_weight_size(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QDialog

    from agentprov_gui.ui.safe import SafeLabel

    base = quoting_run([], None)

    def run(manager: Any, argv: list[str], **kw: Any) -> tuple[int, bytes, bytes]:
        if "--dry-run" in argv and "--m5ultra" in argv:
            return 2, b"", (b"agentprov: error [run.model.facts_missing]: model weight size is unknown: give "
                            b"--model-dir or --model-size-gb\n")
        return base(manager, argv, **kw)

    shown: list[list[str]] = []

    def exec_(box: Any) -> int:
        shown.append([lab.text() for lab in box.findChildren(SafeLabel)])
        return 0

    monkeypatch.setattr(QDialog, "exec", exec_)
    dlg = _dialog(tmp_path, monkeypatch, scripted=True, run=run)
    dlg.tune()
    ((labels),) = shown
    assert any("does not know the weight size" in t and "Settings › Local models" in t for t in labels)
    dlg.close()


def test_the_spinner_turns_only_while_started(qapp: Any) -> None:
    from agentprov_gui.ui.forms import Spinner

    s = Spinner(name="Working")
    assert s.isHidden() and not s.spinning
    s.start()
    first = s.text()
    s._turn()
    assert not s.isHidden() and s.spinning and s.text() != first and s.text() in Spinner.FRAMES
    s.stop()
    assert s.isHidden() and not s.spinning
    s.deleteLater()


def test_building_cost_figures_shows_batches_time_left_and_a_spinner(qapp: Any, tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    dlg._priors_working(True)
    assert dlg.priors_spinner.spinning and not dlg.priors_bar.isHidden() and dlg.priors_bar.maximum() == 0  # moving
    dlg._priors_progress(0, None, None)
    assert "counting the executions" in dlg.priors_status.text()
    dlg._priors_progress(5, 40, None)
    assert dlg.priors_bar.maximum() == 40 and dlg.priors_bar.value() == 5
    assert "5 of 40 batches of 32 executions read (12 %)" in dlg.priors_status.text()
    assert "working out the time left" in dlg.priors_status.text()
    dlg._priors_progress(20, 40, (110.0, 130.0))
    assert "about 2 m 00 s left" in dlg.priors_status.text() and " to " not in dlg.priors_status.text()
    dlg._priors_progress(20, 40, (60.0, 300.0))
    assert "(1 m 00 s to 5 m 00 s)" in dlg.priors_status.text()  # a wide range is shown
    dlg._priors_built(0, "")
    assert not dlg.priors_spinner.spinning and dlg.priors_bar.isHidden()
    assert "Cost figures built" in dlg.priors_status.text()
    dlg.close()


def test_a_running_build_s_progress_file_reaches_the_dialog(qapp: Any, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """The watcher folds the job's progress.jsonl in the pool and hands done of total to the UI thread each tick."""
    from agentprov_gui.jobs.manager import Job

    dlg = _dialog(tmp_path, monkeypatch, scripted=True)
    folder = tmp_path / "job"
    folder.mkdir()
    lines = [{"v": "0.2", "event": "start", "total": 10, "command": "priors build"}]
    lines += [{"v": "0.2", "event": "unit_done", "unit": f"batch {i}", "status": "ok"} for i in range(1, 5)]
    (folder / "progress.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    job = Job("j1", folder, {"command": "priors"}, state="running")
    monkeypatch.setattr(dlg.manager, "refresh", lambda: None)
    dlg.manager.jobs = {"j1": job}
    seen: list[tuple[int, int | None]] = []
    ended: list[int | None] = []
    dlg._watch_job("j1", lambda code, _why: ended.append(code), progress=lambda d, t, _left: seen.append((d, t)))
    wait(qapp, lambda: bool(seen))
    assert seen[-1] == (4, 10) and not ended
    job.state, job.exit_code = "ended", 0
    wait(qapp, lambda: ended == [0])
    dlg.close()
