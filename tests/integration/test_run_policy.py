"""``agentprov run``: endpoint classes, local consent and the API caps against the fake backend (D-721, D-725, D-726).

The fake environment (``live_fake.make_fake_env``) runs no benchmark, no model and no network. The real-model cases
lift the ``planned`` status gate as the consent tests do, give ``.env`` as a canned mapping with placeholder values, and
stop at the preflight probe, so no call is made and no key exists.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import make_fake_env, repo_root  # noqa: E402

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")


class Run(NamedTuple):
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.chdir(repo_root())
    return path


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    from agentprov.cli.main import main

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


@pytest.fixture
def script(tmp_path: Path) -> str:
    path = tmp_path / "script.json"
    path.write_text("[]")
    return str(path)


CORPUS_ARGS = ("--campaign", "t", "--suite", "banking", "--progress", "off")
CAPS = ("--max-calls", "100", "--max-cost-usd", "1", "--price-in", "0.15", "--price-out", "0.6")


@pytest.fixture
def real_model(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Lift the planned gate, serve ``.env`` from ``state["env"]`` and record whether it was read, and stop at the probe."""
    from agentprov.cli import run as run_mod

    state: dict[str, Any] = {"env": {}, "env_read": 0, "probe": 0}
    gate = run_mod._live_capability
    monkeypatch.setattr(run_mod, "_live_capability", lambda source, result, *, scripted: gate(source, result, scripted=True))

    def read_env(args: Any, root: Any) -> dict[str, str]:
        state["env_read"] += 1
        return dict(state["env"])

    def probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
        state["probe"] += 1
        raise run_mod.LiveRefused("probe reached (test stop)", code="cli.refused.test_stop")

    def resolve_local(ctx: Any, args: Any, agent: Any, result: Any, *, writable_cache: bool,
                      api_key: str | None = None) -> Any:
        state["resolved_local"] = state.get("resolved_local", 0) + 1  # D-691: no server is contacted in these tests
        return dict(agent), None, None

    monkeypatch.setattr(run_mod, "_read_env_file", read_env)
    monkeypatch.setattr(run_mod, "_preflight", probe)
    monkeypatch.setattr(run_mod, "_resolve_local", resolve_local)
    return state


def _real(cli: Callable[..., Run], tmp_path: Path, *extra: str) -> Run:
    return cli("run", "agentdojo", "--containment", "vm", "--corpus", str(tmp_path / "corpus"), *CORPUS_ARGS, *extra)


# ---------------------------------------------------------------------------------------------- API endpoints
def test_an_api_endpoint_without_caps_is_refused_before_dotenv_is_read(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    for extra in ((), ("--max-calls", "10")):
        run = _real(cli, tmp_path, "--model", "openrouter", "--model-id", "m", "--i-consent-to-api-costs", *extra)
        assert run.code == 4 and "needs its caps" in run.err and "--max-cost-usd" in run.err, run.err
    assert real_model["env_read"] == 0 and real_model["probe"] == 0


def test_an_api_endpoint_with_caps_reaches_the_probe_after_consent(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    real_model["env"] = {"OPENROUTER_API_KEY": "placeholder-not-a-key"}
    run = _real(cli, tmp_path, "--model", "openrouter", "--model-id", "m", "--i-consent-to-api-costs", *CAPS)
    assert run.code == 4 and "probe reached" in run.err, run.err
    assert "a cell may need up to 48 billed call(s)" in run.err and "may be billed by the provider" in run.err
    assert real_model["probe"] == 1


def test_local_consent_is_not_consent_for_an_api_endpoint(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    real_model["env"] = {"OPENROUTER_API_KEY": "placeholder-not-a-key"}
    run = _real(cli, tmp_path, "--model", "openrouter", "--model-id", "m", "--i-consent-to-local-run", *CAPS)
    assert run.code == 4 and "--i-consent-to-local-run is consent for a local model server" in run.err, run.err
    assert real_model["probe"] == 0


def test_a_local_entry_on_a_lan_address_is_an_api_endpoint(home: Path, tmp_path: Path, cli, real_model) -> None:
    """D-721: until the egress proxy forwards LAN traffic, a LAN server (D-698) is classed api, so it needs the caps;
    a local entry pointed at any other host is refused outright by the endpoint rules (D-698)."""
    make_fake_env(home, "ok")
    real_model["env"] = {"LOCAL_LLM_BASE_URL": "http://192.168.1.20:11434/v1"}
    run = _real(cli, tmp_path, "--model", "ollama", "--model-id", "m", "--allow-lan-endpoint",
                "--i-consent-to-local-run")
    assert run.code == 4 and "needs its caps" in run.err and "not a local server on loopback" in run.err, run.err
    real_model["env"] = {"LOCAL_LLM_BASE_URL": "https://models.example.org/v1"}
    run = _real(cli, tmp_path, "--model", "ollama", "--model-id", "m", "--allow-custom-endpoint",
                "--i-consent-to-local-run")
    assert run.code == 4 and "endpoint.url.not_loopback" in run.err, run.err
    assert real_model["probe"] == 0


# ---------------------------------------------------------------------------------------------- local endpoints
def test_a_local_endpoint_needs_consent_only(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    run = _real(cli, tmp_path, "--model", "ollama", "--model-id", "m")
    assert run.code == 4 and "pass --i-consent-to-local-run" in run.err and "no provider billing" in run.err, run.err
    assert real_model["probe"] == 0
    run = _real(cli, tmp_path, "--model", "ollama", "--model-id", "m", "--i-consent-to-local-run")
    assert run.code == 4 and "probe reached" in run.err, run.err
    assert real_model["probe"] == 1


def test_preflight_only_needs_no_caps_for_an_api_endpoint(home: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    real_model["env"] = {"OPENROUTER_API_KEY": "placeholder-not-a-key"}
    run = cli("run", "agentdojo", "--preflight-only", "--model", "openrouter", "--model-id", "m", "--containment", "vm",
              "--i-consent-to-api-costs", "--progress", "off")
    assert run.code == 4 and "probe reached" in run.err, run.err


# ---------------------------------------------------------------------------------------------- options (exit 2)
@pytest.mark.parametrize("extra", [
    ("--price-in", "1"),
    ("--max-cost-usd", "1", "--price-in", "1"),
    ("--max-cost-usd", "0"),
])
def test_incomplete_cost_options_are_usage_errors(home: Path, tmp_path: Path, cli, script: str, extra: tuple[str, ...]) -> None:
    run = cli("run", "agentdojo", "--corpus", str(tmp_path / "corpus"), *CORPUS_ARGS, "--llm-script", script, *extra)
    assert run.code == 2, run.err


def test_caps_do_not_go_with_preflight_only(home: Path, cli, script: str) -> None:
    run = cli("run", "agentdojo", "--preflight-only", "--llm-script", script, "--max-calls", "5", "--progress", "off")
    assert run.code == 2 and "caps belong to a campaign" in run.err, run.err


# ---------------------------------------------------------------------------------------------- the budget (scripted)
def _scripted(cli: Callable[..., Run], tmp_path: Path, script: str, *extra: str) -> Run:
    return cli("run", "agentdojo", "--corpus", str(tmp_path / "corpus"), *CORPUS_ARGS, "--llm-script", script,
               "--max-attempts", "1", "--json", *extra)


def _live(tmp_path: Path) -> dict[str, Any]:
    live: dict[str, Any] = json.loads((tmp_path / "corpus.partial" / "corpus.json").read_text())["live"]
    return live


def test_a_call_cap_below_one_cell_starts_nothing(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    run = _scripted(cli, tmp_path, script, "--max-calls", "47")
    assert run.code == 1 and "cap_reached" in run.err, run.err
    assert run.json()["counters"]["attempted"] == 0
    live = _live(tmp_path)
    assert live["caps"] == {"max_calls": 47, "cell_call_bound": 48, "billed_calls": 0} and live["partial"] is True


def test_a_cell_that_fits_runs_and_the_caps_are_recorded(home: Path, tmp_path: Path, cli, script: str) -> None:
    """The fake worker's log records no model call, so nothing is billed (the counting is unit-tested on real event
    shapes in tests/cli/test_live_policy.py)."""
    make_fake_env(home, "ok")
    run = _scripted(cli, tmp_path, script, "--max-calls", "48", "--max-cost-usd", "10", "--price-in", "1",
                    "--price-out", "1")
    assert run.code in (0, 1) and "cap_" not in run.err, run.err
    assert run.json()["counters"]["attempted"] == 1
    caps = _live(tmp_path)["caps"]
    assert caps == {"max_calls": 48, "cell_call_bound": 48, "max_cost_usd": "10", "price_in_usd_per_mtok": "1",
                    "price_out_usd_per_mtok": "1", "billed_calls": 0, "spend_upper_bound_usd": "0.000"}


def test_the_caps_count_the_corpus_s_earlier_attempts(home: Path, tmp_path: Path, cli, script: str) -> None:
    """Resume: an earlier invocation's attempt (here killed, so charged one call for the reply in flight) counts, so a
    second invocation under the same cap cannot start a cell whose worst case no longer fits."""
    make_fake_env(home, "hang")
    first = _scripted(cli, tmp_path, script, "--max-calls", "48", "--cell-timeout", "2")
    assert first.json()["counters"]["attempted"] == 1, first.err
    again = _scripted(cli, tmp_path, script, "--max-calls", "48", "--cell-timeout", "2", "--max-attempts", "2")
    assert again.code == 1 and "cap_reached" in again.err, again.err
    assert again.json()["counters"]["attempted"] == 0
    assert _live(tmp_path)["caps"]["billed_calls"] >= 1


def test_a_scripted_run_without_caps_records_no_caps(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    run = _scripted(cli, tmp_path, script)
    assert run.code in (0, 1), run.err
    live = _live(tmp_path)
    assert "caps" not in live and "endpoint_class" not in live


def test_the_dry_run_states_the_cell_bound(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    run = _scripted(cli, tmp_path, script, "--dry-run", "--max-calls", "100")
    assert run.code == 0, run.err
    assert any("a cell may need up to 48 billed call(s)" in n for n in run.json()["notices"])


# ---------------------------------------------------------------------------------------------- setup refusal
def test_a_setup_refusal_stops_the_campaign_after_one_attempt(home: Path, tmp_path: Path, cli, script: str) -> None:
    """A fatal UnsupportedConfiguration at cell setup (e.g. a missing --model-display-name) is a property of the
    configuration: the campaign starts no further cell and no re-attempt, and says what to fix."""
    make_fake_env(home, "setuprefusal")
    run = _scripted(cli, tmp_path, script, "--repeats", "3", "--max-attempts", "2", "--canary", "0")
    assert run.code == 1, run.err
    assert run.json()["counters"]["attempted"] == 1  # without the stop: 3 units x 2 attempts
    text = run.out + run.err  # with --json the summary carries the error and the notices
    assert "setup refused this configuration" in text and "--model-display-name is required" in text, text
    assert _live(tmp_path)["partial"] is True


def test_a_name_addressing_attack_without_a_display_name_gets_a_hint(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    hinted = _real(cli, tmp_path, "--model", "ollama", "--model-id", "m", "--i-consent-to-local-run",
                   "--attack", "important_instructions", "--injection-tasks", "injection_task_0", "--dry-run", "--json")
    named = _real(cli, tmp_path, "--model", "ollama", "--model-id", "m", "--i-consent-to-local-run",
                  "--attack", "important_instructions", "--injection-tasks", "injection_task_0",
                  "--model-display-name", "Local model", "--dry-run", "--json")
    assert hinted.code == 0 and named.code == 0, hinted.out + hinted.err
    assert any("address the model by name" in n for n in hinted.json()["notices"]), hinted.out
    assert not any("address the model by name" in n for n in named.json()["notices"]), named.out


# ---------------------------------------------------------------------------------------------- A9 probe (D-729)
def _probe_calls(home: Path) -> int:
    from agentprov.cli.live import envs

    project = envs.backend_project("agentdojo", repo_root())
    counter = envs.env_dir(project, home) / "probe_calls"
    return int(counter.read_text()) if counter.exists() else 0


@pytest.mark.parametrize(("mode", "code", "calls"), [
    ("ok", 0, 1),                  # accepted at once: one call
    ("probeflaky", 0, 2),          # unconfirmed, then accepted: the second call ends it
    ("probeunconfirmed", 4, 3),    # never evidenced: three calls, then the A9 refusal
    ("proberefused", 4, 1),        # a refusal is final at once
])
def test_the_preflight_probe_repeats_only_while_unconfirmed(home: Path, cli, script: str, mode: str, code: int,
                                                             calls: int) -> None:
    make_fake_env(home, mode)
    run = cli("run", "agentdojo", "--preflight-only", "--llm-script", script, "--json", "--progress", "off")
    assert run.code == code, run.out + run.err
    assert _probe_calls(home) == calls
    if code == 0:
        assert run.json()["counters"] == {"probes": calls}


def test_each_probe_call_is_charged_to_the_caps(home: Path, tmp_path: Path, cli, real_model, monkeypatch) -> None:
    """The campaign's probe goes through the D-729 loop and every call is charged (D-725)."""
    from agentprov.cli import run as run_mod

    replies = iter([{"reachable": True, "roles_accepted": False, "roles": "unconfirmed"},
                    {"reachable": True, "roles_accepted": True, "roles": "accepted", "tool_calls": "structured",
                     "params": {"not_transmitted": []}}])
    seen: list[int] = []

    def probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return next(replies)

    def stop(*args: Any, budget: Any = None, **kwargs: Any) -> Any:
        seen.append(budget.calls)
        raise run_mod.LiveRefused("execute reached (test stop)", code="cli.refused.test_stop")

    monkeypatch.setattr(run_mod, "_preflight", probe)
    monkeypatch.setattr(run_mod, "_execute", stop)
    make_fake_env(home, "ok")
    real_model["env"] = {"OPENROUTER_API_KEY": "placeholder-not-a-key"}
    run = _real(cli, tmp_path, "--model", "openrouter", "--model-id", "m", "--i-consent-to-api-costs", *CAPS)
    assert "execute reached" in run.err, run.err
    assert seen == [2]
