"""G3 Run live: the job manager's keychain stdin (D-395, D-655), the run spec and the Run Live dialog."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from agentprov_gui.jobs.commands import JobSpec
from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused, read_json

FAKE = Path(__file__).resolve().parent / "fake" / "fake_cli.py"


def _wait(m: JobManager, job_id: str) -> None:
    end = time.monotonic() + 20
    while time.monotonic() < end and m.jobs[job_id].state == "running":
        time.sleep(0.05)
        m.refresh()


def test_the_gui_never_passes_keys_and_jobs_read_dev_null(tmp_path: Path) -> None:
    """D-702/D-704: no job takes keys from the GUI (``--env-stdin``/``--env-file`` are refused before the CLI runs); a
    job's stdin is /dev/null under the core's supervisor, and job.json holds no environment values."""
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))),
                   environ={**os.environ, "OPENROUTER_API_KEY": "sk-" + "fake-" + "f" * 24})
    for flag in ("--env-stdin", "--env-file"):
        with pytest.raises(SpawnRefused) as exc:
            m.spawn(JobSpec("run", ("run", flag, "agentdojo"), "R2", "live"))
        assert exc.value.code == "gui.keys.refused"
    job = m.spawn(JobSpec("import", ("import", "--units", "1", "x"), "R1", "imp"))
    _wait(m, job.job_id)
    record = job.file("job.json").read_bytes()
    assert b"sk-fake" not in record and b"OPENROUTER_API_KEY" not in record


# ---------------------------------------------------------------------------------------------- the Run Live dialog
CATALOGUE = {"format": "agentprov-backend-catalogue/0.1", "backend": "agentdojo", "benchmark_version": "v1.2.2",
             "benchmark_versions": ["v1.2.2"],
             "suites": [{"name": "banking", "user_tasks": ["user_task_0", "user_task_1"],
                         "injection_tasks": ["injection_task_0"], "tool_definition_chars": 4545}],
             "attacks": [{"name": "direct", "dos": False, "refused": None, "needs": []},
                         {"name": "ours", "dos": False, "refused": "optimiser outputs unsupported", "needs": []}]}


PRICES = {"format": "agentprov-prices-list/0.1", "stale_days": 60,
          "shipped": {"rows": 1, "as_of": "2026-10-21"}, "refreshed": {"rows": 0, "as_of": None}, "overrides": [],
          "endpoints": [{"name": "openrouter", "local": False, "models": [
              {"id": "vendor/m", "model": "vendor/m", "provider": "openrouter", "input": "1", "output": "2",
               "cached_input": None, "source": "https://openrouter.ai/api/v1/models", "as_of": "2026-10-21",
               "stale": False, "note": ""}]}, {"name": "ollama", "local": True, "models": []}]}


def fake_run(calls: list[list[str]]) -> Any:
    def run(_manager: Any, argv: list[str], *, stdin_fd: int | None = None, timeout: float = 0) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if stdin_fd is not None:
            os.close(stdin_fd)
        if argv[0] == "info":
            return 0, json.dumps({"source_id": argv[1], "parts": [{"live": "planned"}]}).encode(), b""
        if "--catalogue" in argv:
            if argv[-1] == "autodojo":
                return 3, b"", b"agentprov: the backend environment autodojo-x is not built; run 'agentprov backends build"
            return 0, json.dumps(CATALOGUE).encode(), b""
        if "--m5ultra" in argv:
            return 0, json.dumps({"counters": {"jobs": 6}}).encode(), b"concurrency: jobs = 6 (computed)\n"
        if argv[:2] == ["prices", "list"]:
            return 0, json.dumps(PRICES).encode(), b""
        if argv[0] == "estimate":  # D-701: the CLI's numbers and lines; the GUI computes none
            attacks = argv[argv.index("--attack") + 1].split(",") if "--attack" in argv else []
            units = 2 + 2 * len(attacks)
            scripted = "--llm-script" in argv
            head = f"{units:,} cell run(s); scripted transport: no cost." if scripted else f"≈ $0.10 for {units} runs"
            doc = {"format": "agentprov-estimate/0.1", "units": units, "attempts_due": 3 * units,
                   "cost_p50": "0" if scripted else "0.1", "cost_p90": "0" if scripted else "0.2",
                   "cost_worst": "0" if scripted else "0.5", "seconds_p50": 60.0, "seconds_p90": 120.0,
                   "price": None, "planned_with": "model" if scripted else "stand-in",
                   "plan": {"plan_sha256": "0" * 64}, "warnings": [],
                   "text": [head + " Time ≈ 1 m (p90 2 m) at --jobs 1.", f"Plan 0000…: {units} cells", "By suite:"]}
            return 0, json.dumps(doc).encode(), b""
        return 2, b"", b"unexpected"

    return run


def wait(app: Any, cond: Any, timeout: float = 30) -> None:
    from PySide6.QtCore import QEventLoop

    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


@pytest.fixture
def dialog(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from agentprov_gui.live import keychain
    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import DEV_SCRIPT, RunLiveDialog

    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(True, "FakeRing"))
    monkeypatch.setattr(keychain, "present", lambda cli, names: {n: False for n in names})
    calls: list[list[str]] = []
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    preset = RunSettings(campaign="t", script=str(DEV_SCRIPT), suites=("banking",), attacks=("direct", "ours"))
    dlg = RunLiveDialog(m, home=tmp_path / "home", checkout=None, preset=preset, run=fake_run(calls))
    dlg.calls = calls
    yield dlg
    dlg.close()


def test_the_dialog_loads_the_catalogue_and_estimates(qapp: Any, dialog: Any) -> None:
    wait(qapp, lambda: dialog.estimate_result is not None)
    assert dialog.settings().suites == ("banking",)
    assert dialog.settings().attacks == ("direct",)  # the refused attack cannot be ticked
    e = dialog.estimate_result
    assert e.units == 4 and e.cost_p90 == 0
    assert "scripted transport: no cost" in dialog.headline.text() and "By suite:" in dialog.details.toPlainText()
    (call,) = [c for c in dialog.calls if c[0] == "estimate"][-1:]
    assert "--llm-script" in call and call[call.index("--format") + 1] == "json" and "--plan-json" not in call
    assert "--keychain" not in call and call[-1] == "agentdojo"
    wait(qapp, lambda: dialog.prices is not None)
    assert dialog.prices.lookup("openrouter", "vendor/m").input == 1
    assert dialog.start_btn.isEnabled() and not dialog.preflight_btn.isEnabled()


def test_a_backend_that_is_not_built_launches_nothing(qapp: Any, dialog: Any) -> None:
    wait(qapp, lambda: "autodojo" in dialog.catalogues)
    dialog.source.setCurrentIndex(dialog.source.findData("autodojo"))
    wait(qapp, lambda: "not built" in dialog.error.text())
    assert "agentprov backends build autodojo" in dialog.error.text() and not dialog.start_btn.isEnabled()
    assert "not built" in dialog.source.itemText(dialog.source.findData("autodojo"))


def test_a_real_model_is_gated_while_the_live_part_is_planned(qapp: Any, dialog: Any) -> None:
    wait(qapp, lambda: dialog.live_status.get("agentdojo") == "planned")
    dialog.mode.setCurrentIndex(1)
    wait(qapp, lambda: "gated" in dialog.error.text())
    assert not dialog.start_btn.isEnabled() and not dialog.preflight_btn.isEnabled()


def test_the_cost_confirmation_needs_the_consent_tick(qapp: Any, dialog: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox

    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import consent_text

    wait(qapp, lambda: dialog.estimate_result is not None)
    seen: dict[str, Any] = {}

    def exec_(self: QDialog) -> int:
        tick = self.findChild(QCheckBox)
        ok = self.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        seen["before"], seen["text"] = ok.isEnabled(), tick.text()
        tick.setChecked(True)
        seen["after"] = ok.isEnabled()
        return 1

    monkeypatch.setattr(QDialog, "exec", exec_)
    assert dialog.confirm_costs(RunSettings(model="openrouter", model_id="vendor/m"), preflight=False)
    assert seen == {"before": False, "after": True, "text": consent_text(dialog.estimate_result.attempts_due)}


def test_a_scripted_start_hands_runs_the_spec(qapp: Any, dialog: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import runlive

    wait(qapp, lambda: dialog.estimate_result is not None)
    monkeypatch.setattr(runlive, "confirm", lambda _p, spec, _a: spec)
    dialog._start(preflight=False)
    start = dialog.start
    assert start is not None and start.key_names == () and start.backend == "agentdojo"
    argv = start.spec.argv
    assert argv[0] == "run" and argv[-1] == "agentdojo" and "--llm-script" in argv and "--env-stdin" not in argv
    assert start.spec.tier == "R1" and "--i-consent-to-api-costs" not in argv


# ---------------------------------------------------------------------------------------------- Prices (D-650, D-701)
def test_refresh_prices_is_the_cli_command_at_r2() -> None:
    """The fetch itself is the core's (tests/cli/test_prices_cmd.py, against a fake transport); the GUI starts it."""
    from agentprov_gui.jobs.commands import FORMS, build_spec

    form = FORMS["prices_refresh"]
    assert form.tool is None and form.menu and form.words == ("prices", "refresh")
    spec = build_spec(form, {})
    assert spec.argv[:3] == ("prices", "refresh", "--allow-network") and spec.tier == "R2"


def test_the_prices_pane_writes_through_agentprov_prices(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.live.plan import parse_prices
    from agentprov_gui.ui import livepanes

    calls: list[list[str]] = []

    def call(_cli: Any, argv: list[str], **_kw: Any) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[:2] == ["prices", "list"]:
            return 0, json.dumps(doc).encode(), b""
        return (2, b"", b"agentprov prices set: input is not a non-negative decimal") if "-1" in argv else (0, b"", b"")

    doc = {**PRICES, "overrides": [{"key": "openrouter:vendor/old", "model": "openrouter:vendor/old",
                                    "provider": "override", "input": "1", "output": "2", "cached_input": None,
                                    "source": "x", "as_of": "2026-10-01", "stale": False}]}
    monkeypatch.setattr(livepanes, "call", call)
    monkeypatch.setattr(livepanes, "submit", lambda _o, fn, done, _f=None: done(fn(None)))
    boxes: list[str] = []
    monkeypatch.setattr(livepanes, "safe_message_box", lambda *a, **k: boxes.append(k.get("informative", "")) or
                        type("B", (), {"exec": lambda self: 0})())
    pane = livepanes.PricesPane(None)
    assert pane.isEnabled() and pane.table.rowCount() == 1 and parse_prices(json.dumps(doc).encode()).overrides
    pane.save()
    assert calls[1:] == []  # nothing changed: nothing written
    pane.table.removeRow(0)
    pane._add(["openrouter:vendor/new:free", "3", "", "4", "", "2026-10-22"])
    pane._add(["openrouter:vendor/bad", "-1", "", "4", "", "2026-10-22"])
    pane.save()
    assert ["prices", "unset", "openrouter", "vendor/old"] in calls
    assert ["prices", "set", "openrouter", "vendor/new:free", "--input", "3", "--output", "4", "--as-of",
            "2026-10-22"] in calls
    assert boxes and "vendor/bad" in boxes[0]
    pane.close()


def test_the_estimate_pane_writes_only_changed_settings(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.ui import livepanes

    calls: list[list[str]] = []

    def call(_cli: Any, argv: list[str], **_kw: Any) -> tuple[int, bytes, bytes]:
        calls.append(list(argv))
        if argv[:2] == ["settings", "list"]:
            values = {"estimate.default.calls_p50": 8}
            return 0, json.dumps({"format": "agentprov-settings/0.1", "values": values}).encode(), b""
        return 0, b"", b""

    monkeypatch.setattr(livepanes, "call", call)
    monkeypatch.setattr(livepanes, "submit", lambda _o, fn, done, _f=None: done(fn(None)))
    pane = livepanes.EstimatePane(None)
    assert pane.spins["calls_p50"].value() == 8 and pane.isEnabled()
    pane.save()
    assert len(calls) == 1
    pane.spins["seconds_p90"].setValue(200)
    pane.save()
    assert calls[-1] == ["settings", "set", "estimate.default.seconds_p90", "200"]
    pane.close()


# ---------------------------------------------------------------------------------------------- live dev run (§19.2)
def test_the_live_dev_run_preset_and_its_call_cap(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.jobs.follow import ProgressState
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.runs import RunsPage

    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    page = RunsPage(m, Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)))
    seen: dict[str, Any] = {}
    monkeypatch.setattr(page, "run_live", lambda preset, **kw: seen.update(preset=preset, **kw))
    page.start_live_dev_run()
    preset = seen["preset"]
    assert preset.scripted and preset.user_tasks == "0-2" and preset.attacks == ("direct",)
    assert preset.corpus.startswith(str(tmp_path / "home" / "dev-runs")) and seen["call_cap"] == 5
    assert seen["dev_run"] is True and seen["cost_cap"] is None

    class Follower:
        state = ProgressState()

    job = m.spawn(JobSpec("run", ("run", "--units", "1", "--sleep", "5", "agentdojo"), "R1", "dev",
                          extra={"call_cap": 2, "progress_level": "steps"}))
    assert "steps" in job.argv[job.argv.index("--progress") + 1]
    f = Follower()
    f.state.steps["model_call"] = 1
    page._enforce_call_cap(job, f)  # type: ignore[arg-type]
    assert job.job_id not in page._capped
    end = time.monotonic() + 20  # the fake installs its SIGTERM handler before its first progress line
    while time.monotonic() < end and not (job.file("progress.jsonl").exists()
                                          and job.file("progress.jsonl").stat().st_size):
        time.sleep(0.05)
    f.state.steps["model_call"] = 2
    page._enforce_call_cap(job, f)  # type: ignore[arg-type]
    assert job.job_id in page._capped
    _wait(m, job.job_id)
    assert m.jobs[job.job_id].exit_code == 130  # no control file: one SIGTERM, as Stop does
    page.close()


def test_more_options_reach_every_other_run_field(qapp: Any, dialog: Any) -> None:
    from agentprov_gui.jobs.commands import FORMS
    from agentprov_gui.ui.runlive import _DIALOG_KEYS

    assert set(dialog.more_inputs) == {f.key for f in FORMS["run"].fields} - _DIALOG_KEYS
    dialog.more_inputs["keep_staging"].setChecked(True)
    dialog.more_inputs["temperature"].setText("0.5")
    s = dialog.settings()
    assert s.extra["keep_staging"] is True and s.extra["temperature"] == "0.5"


def test_anthropic_endpoints_get_the_max_tokens_choice(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui.live import keychain
    from agentprov_gui.live.plan import ENDPOINTS_REL
    from agentprov_gui.live.runspec import RunSettings
    from agentprov_gui.ui.runlive import RunLiveDialog

    repo = tmp_path / "repo"
    path = repo / ENDPOINTS_REL
    path.parent.mkdir(parents=True)
    path.write_text('[endpoints.anthropic]\nbase_url = "https://api.anthropic.com"\napi_key_env = "ANTHROPIC_API_KEY"\n'
                    'api = "anthropic_messages"\nlocal = false\n')
    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(True, "FakeRing"))
    monkeypatch.setattr(keychain, "present", lambda cli, names: dict.fromkeys(names, True))
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    preset = RunSettings(campaign="t", scripted=False, model="anthropic", model_id="claude-opus-5-5",
                         suites=("banking",), containment="vm")
    without = RunLiveDialog(m, home=tmp_path / "home", checkout=repo, preset=preset, run=fake_run([]))
    wait(qapp, lambda: "agentdojo" in without.catalogues and "agentdojo" in without.live_status)
    without.live_status["agentdojo"] = "supported"  # past the planned gate, to reach the --max-tokens rule
    assert "--max-tokens" in (without._gate() or "")
    assert without.max_tokens_box.isHidden() and "max_tokens" not in without.settings().extra
    with_opt = RunLiveDialog(m, home=tmp_path / "home", checkout=repo, preset=preset, run=fake_run([]),
                             cli_options=frozenset({"--max-tokens"}))
    assert with_opt.settings().extra["max_tokens"] == "harness-default"
    with_opt.max_tokens_mode.setCurrentIndex(1)
    with_opt.max_tokens.setValue(4096)
    assert with_opt.settings().extra["max_tokens"] == "4096"
    assert not with_opt.more_inputs["reasoning_effort"].isEnabled() and not with_opt.more_inputs["llm_element"].isEnabled()
    without.close()
    with_opt.close()


def test_api_caps_and_local_consent_follow_the_cli(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-725/D-726 (live pilot): the caps appear for an API endpoint once the CLI has them, are prefilled from the price
    table, are required to start, and reach argv; a local endpoint's consent is the local-run flag."""
    from agentprov_gui.live import keychain
    from agentprov_gui.live.plan import ENDPOINTS_REL
    from agentprov_gui.live.runspec import RunSettings, job_spec
    from agentprov_gui.ui.runlive import RunLiveDialog, consent_text

    repo = tmp_path / "repo"
    path = repo / ENDPOINTS_REL
    path.parent.mkdir(parents=True)
    path.write_text('[endpoints.openrouter]\nbase_url = "https://openrouter.ai/api/v1"\napi_key_env = "OPENROUTER_API_KEY"\n'
                    'local = false\n[endpoints.ollama]\nbase_url = "http://127.0.0.1:11434/v1"\nlocal = true\n')
    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(True, "FakeRing"))
    monkeypatch.setattr(keychain, "present", lambda cli, names: dict.fromkeys(names, True))
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    preset = RunSettings(campaign="t", scripted=False, model="openrouter", model_id="vendor/m", suites=("banking",),
                         containment="vm")
    old = RunLiveDialog(m, home=tmp_path / "home", checkout=repo, preset=preset, run=fake_run([]))
    assert old.caps_box.isHidden() and "max_calls" not in old.settings().extra  # this CLI has no caps yet
    caps = frozenset({"--max-calls", "--max-cost-usd", "--price-in", "--price-out", "--i-consent-to-local-run"})
    dlg = RunLiveDialog(m, home=tmp_path / "home", checkout=repo, preset=preset, run=fake_run([]), cli_options=caps)
    wait(qapp, lambda: "agentdojo" in dlg.catalogues and "agentdojo" in dlg.live_status and dlg.prices is not None)
    dlg.live_status["agentdojo"] = "supported"  # past the planned gate
    assert "both caps" in (dlg._gate() or "") and not dlg.caps_box.isHidden()
    assert (dlg.price_in.value(), dlg.price_out.value()) == (1.0, 2.0)  # prices list's vendor/m (no cache prices)
    dlg.max_calls.setValue(200)
    dlg.max_cost.setValue(5)
    assert "both caps" not in (dlg._gate() or "")
    s = dlg.settings()
    argv = job_spec(s, consent=True).argv
    for flag, value in (("--max-calls", "200"), ("--max-cost-usd", "5.0"), ("--price-in", "1.0"),
                        ("--price-out", "2.0")):
        assert argv[argv.index(flag) + 1] == value, flag
    assert "--i-consent-to-api-costs" in argv
    dlg.endpoint.setCurrentText("ollama")
    assert dlg.caps_box.isHidden() or not dlg._caps_shown()
    assert dlg._local_consent() and "local model run" in consent_text(3, local=True)
    local = job_spec(dlg.settings(), consent=True, local_consent=dlg._local_consent()).argv
    assert "--i-consent-to-local-run" in local and "--i-consent-to-api-costs" not in local and "--max-calls" not in local
    old.close()
    dlg.close()


def test_preflight_only_on_an_api_endpoint_needs_no_caps_and_passes_none(qapp: Any, tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """D-725/D-729: the CLI refuses caps with --preflight-only (exit 2), so Preflight Only… is enabled without them,
    its argv carries none, and its confirmation names the probe's bound (up to three calls), not one call."""
    from PySide6.QtWidgets import QCheckBox, QDialog, QLabel

    from agentprov_gui.live import keychain
    from agentprov_gui.live.plan import ENDPOINTS_REL
    from agentprov_gui.live.runspec import RunSettings, job_spec
    from agentprov_gui.ui.runlive import PROBE_CALLS, RunLiveDialog, consent_text, preflight_settings

    repo = tmp_path / "repo"
    path = repo / ENDPOINTS_REL
    path.parent.mkdir(parents=True)
    path.write_text('[endpoints.openrouter]\nbase_url = "https://openrouter.ai/api/v1"\napi_key_env = "OPENROUTER_API_KEY"\n'
                    'local = false\n')
    monkeypatch.setattr(keychain, "status", lambda cli: keychain.KeychainStatus(True, "FakeRing"))
    monkeypatch.setattr(keychain, "present", lambda cli, names: dict.fromkeys(names, True))
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))))
    preset = RunSettings(campaign="t", scripted=False, model="openrouter", model_id="vendor/m", suites=("banking",),
                         containment="vm")
    caps = frozenset({"--max-calls", "--max-cost-usd", "--price-in", "--price-out"})
    dlg = RunLiveDialog(m, home=tmp_path / "home", checkout=repo, preset=preset, run=fake_run([]), cli_options=caps)
    wait(qapp, lambda: "agentdojo" in dlg.catalogues and "agentdojo" in dlg.live_status and dlg.prices is not None)
    dlg.live_status["agentdojo"] = "supported"  # past the planned gate
    assert "both caps" in (dlg._gate() or "") and dlg.preflight_reason is None
    assert dlg.preflight_btn.isEnabled() and not dlg.start_btn.isEnabled()
    dlg.max_calls.setValue(200)
    dlg.max_cost.setValue(5)
    dlg._gate()
    assert dlg.start_btn.isEnabled() and dlg.preflight_btn.isEnabled()
    probe = preflight_settings(dlg.settings())
    argv = job_spec(probe, consent=True).argv
    assert "--preflight-only" in argv
    assert not {"--max-calls", "--max-cost-usd", "--price-in", "--price-out"} & set(argv)
    seen: dict[str, str] = {}

    def exec_(self: QDialog) -> int:
        seen["tick"] = self.findChild(QCheckBox).text()
        seen["text"] = "\n".join(w.text() for w in self.findChildren(QLabel))
        self.findChild(QCheckBox).setChecked(True)
        return 1

    monkeypatch.setattr(QDialog, "exec", exec_)
    assert dlg.confirm_costs(probe, preflight=True)
    assert seen["tick"] == consent_text(1, preflight=True) and f"up to {PROBE_CALLS} preflight probe calls" in seen["tick"]
    assert f"up to {PROBE_CALLS} probe calls" in seen["text"] and "one probe call" not in seen["text"]
    assert "Caps (D-725)" not in seen["text"]
    assert dlg.confirm_costs(dlg.settings(), preflight=False)
    assert f"the preflight probe makes up to {PROBE_CALLS} calls" in seen["text"] and "Caps (D-725)" in seen["text"]
    dlg.close()


def test_tune_applies_the_preset_jobs(qapp: Any, dialog: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QDialog

    monkeypatch.setattr(QDialog, "exec", lambda self: 1)
    dialog.tune()
    assert dialog.jobs.value() == 6
    assert any("--m5ultra" in c and "--dry-run" in c for c in dialog.calls)


def test_repository_commands_start_in_the_checkout(tmp_path: Path) -> None:
    """The G3 end-to-end run found it: run, backends build and migrate find the repository from their cwd (M.4)."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    m = JobManager(tmp_path / "home", CliLocator(checkout, (sys.executable, str(FAKE))))
    run = m.spawn(JobSpec("run", ("run", "--units", "1", "agentdojo"), "R1", "live"))
    imp = m.spawn(JobSpec("import", ("import", "--units", "1", "x"), "R1", "imp"))
    # D-704: the configured checkout's CLI starts the job, so the cwd is that CLI's own checkout (here, the core this
    # fake delegates to)
    from agentprov.jobs.manager import checkout_root

    assert read_json(run.file("job.json"))["cwd"] == str(checkout_root())  # type: ignore[index]
    assert read_json(imp.file("job.json"))["cwd"] == str(imp.directory)  # type: ignore[index]
    _wait(m, run.job_id)
    _wait(m, imp.job_id)


# ---------------------------------------------------------------------------------------------- keys via the CLI (D-702)
FAKE_KEYS = r"""
import json, sys
args = sys.argv[1:]
assert args[0] == "keys", args
store_path = __STORE__
try:
    store = json.load(open(store_path))
except FileNotFoundError:
    store = {}
if args[1] == "status":
    print(json.dumps({"allowed": True, "backend": "Stub"}))
elif args[1] == "list":
    print(json.dumps({"keys": [{"name": n, "stored": n in store} for n in ("OPENAI_API_KEY", "OPENROUTER_API_KEY")]}))
elif args[1] == "set":
    assert "--stdin" in args and args[3] == "--stdin"  # keys set NAME --stdin: no value anywhere in argv
    store[args[2]] = sys.stdin.readline().rstrip("\n")
    json.dump(store, open(store_path, "w"))
elif args[1] == "delete":
    assert "--yes" in args
    store.pop(args[2], None)
    json.dump(store, open(store_path, "w"))
"""


def test_the_gui_keychain_client_calls_agentprov_keys(tmp_path: Path) -> None:
    from agentprov_gui.live import keychain

    store = tmp_path / "store.json"
    script = tmp_path / "fake_keys.py"
    script.write_text(FAKE_KEYS.replace("__STORE__", repr(str(store))))
    cli = CliLocator(None, (sys.executable, str(script)))
    assert keychain.status(cli) == keychain.KeychainStatus(True, "Stub")
    secret = "sk-" + "gui-" + "a" * 20
    keychain.store(cli, "OPENAI_API_KEY", secret)
    assert json.loads(store.read_text()) == {"OPENAI_API_KEY": secret}
    assert keychain.present(cli, ["OPENAI_API_KEY", "OPENROUTER_API_KEY"]) == {"OPENAI_API_KEY": True,
                                                                              "OPENROUTER_API_KEY": False}
    keychain.delete(cli, "OPENAI_API_KEY")
    assert json.loads(store.read_text()) == {}
    with pytest.raises(keychain.KeychainError):
        keychain.status(CliLocator(None, ()))
