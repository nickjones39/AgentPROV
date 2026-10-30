"""End to end with the real backend environment (DoD Q.4; K.8.5, K.12.16; MN N.2.1, N.2.10).

``agentprov backends build agentdojo`` builds the environment once per test session into a temporary
``$AGENTPROV_HOME`` (offline from the uv cache; ``AGENTPROV_TEST_BUILD_NETWORK=1`` lets uv download, as the CI job
``live-run`` does), and ``agentprov run agentdojo --llm-script`` runs real AgentDojo v1.2.2 banking cells in the spawned
worker with the scripted transport: no network, no key. The assertions are Q.4's: sealed raw evidence -> AER -> SEM ->
PROV, valid at every tier, the session declared ``test_only``, the corpus synthetic; re-mapping the stored session gives
the same AER bytes (RPR-10); a second invocation resumes and executes nothing.

Marker ``backend_agentdojo`` (the core CI job deselects it; it needs the backend project's packages). Without the uv
cache and without the network flag the build fails and every test here skips with the reason.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters" / "agentdojo"))

from live_fake import repo_root  # noqa: E402

pytestmark = [pytest.mark.backend_agentdojo, pytest.mark.slow,
              pytest.mark.skipif(os.name == "nt", reason="the backend environment is POSIX-only in v0.1")]

#: The benign_banking_single_pass scenario of agentprov_backend.testing.scenarios: one tool call, one answer.
SCRIPT = [
    {"reply": "tool_calls", "calls": [{"name": "get_most_recent_transactions", "args": {"n": 100}, "id": "call_1"}]},
    {"reply": "text", "content": "You spent 1050 in March 2022."},
]


def _main(*argv: str) -> tuple[int, str, str]:
    import contextlib
    import io

    from agentprov.cli.main import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="session")
def live_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    home = tmp_path_factory.mktemp("live-home")
    with pytest.MonkeyPatch.context() as mp:  # for the build only; _live_env sets it again for each test
        mp.setenv("AGENTPROV_HOME", str(home))
        mp.delenv("AGENTPROV_PROGRESS", raising=False)
        mp.chdir(repo_root())
        argv = ["backends", "build", "agentdojo", "--progress", "off"]
        if os.environ.get("AGENTPROV_TEST_BUILD_NETWORK") == "1":
            argv.append("--allow-network")
        code, _out, err = _main(*argv)
    if code != 0:
        pytest.skip(f"the backend environment could not be built (exit {code}): {err.strip().splitlines()[-1:]}")
    return home


@pytest.fixture(autouse=True)
def _live_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that uses ``live_home`` runs with it as ``$AGENTPROV_HOME``, set for that test only: set in the session
    fixture, it outlived the module and every later test on the worker kept it (bug pass BF-34)."""
    if "live_home" in request.fixturenames:
        monkeypatch.setenv("AGENTPROV_HOME", str(request.getfixturevalue("live_home")))
        monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


@pytest.fixture
def in_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo_root())


def _marker(home: Path) -> dict[str, Any]:
    (env,) = list((home / "envs").iterdir())
    return json.loads((env / "AGENTPROV_ENV.json").read_text())


def test_the_build_records_its_marker_and_passes_the_offline_check(live_home: Path, in_repo: None) -> None:
    from agentprov.cli.live import envs, sandbox

    project = envs.backend_project("agentdojo", repo_root())
    marker = _marker(live_home)
    assert marker["status"] == "complete" and marker["backend"] == "agentdojo" and marker["commit"] is None
    assert marker["env_name"] == f"agentdojo-{project.lock_sha256[:8]}" and marker["commit8_source"] == "lock_sha256"
    assert marker["lock_sha256"] == project.lock_sha256 and marker["python"].startswith("3.12.")
    assert marker["lock_wheel"]["version"] == "0.1.35" and len(marker["lock_wheel"]["wheel_sha256"]) == 64
    assert marker["t0_identity"]["distributions"]["agentdojo"]["source"] == {"kind": "pypi"}
    assert marker["hello_identity"]["record_digest"] == marker["t0_identity"]["distributions"]["agentdojo"]["record_sha256"]
    assert "--no-config" in marker["uv"]["argv"] and "--locked" in marker["uv"]["argv"]
    assert marker["sandbox_probe"]["profile_sha256"] == sandbox.PROFILE_SHA256
    assert marker["sandbox_status"] in ("passed", "failed", "not_applicable")
    code, _out, err = _main("backends", "build", "agentdojo", "--offline-check", "--progress", "off")
    assert code == 0, err


def test_a_scripted_run_seals_and_derives_valid_executions(live_home: Path, in_repo: None, tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text(json.dumps(SCRIPT))
    corpus = tmp_path / "corpus"
    argv = ("run", "agentdojo", "--corpus", str(corpus), "--campaign", "q4", "--suite", "banking",
            "--user-tasks", "user_task_1", "--attack", "important_instructions", "--injection-tasks", "injection_task_0",
            "--model-display-name", "Scripted Model", "--llm-script", str(script), "--keep-staging", "--json",
            "--progress", "off")  # fmt: skip
    code, out, err = _main(*argv)
    summary = json.loads(out)
    assert code == 0, (err, summary["failures"])
    c = summary["counters"]
    assert c["cells_planned"] == 2 and c["attempted"] == 2 and c["conclusive"] == 2 and c["derived"] == 2 and c["failed"] == 0
    partial = Path(str(corpus) + ".partial")
    manifest = json.loads((partial / "corpus.json").read_text())
    assert manifest["mode"] == "live" and manifest["synthetic"] is True and manifest["live"]["test_only"] is True
    assert manifest["formats"]["capture"] == "capture/0.1" and manifest["producer"]["sandbox"] is None
    assert "agentdojo.transport_scripted@1" in manifest["live"]["instrumentation"]
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    status_of = {r["ex"]: r["status"] for r in rows}  # the ledger names each index row's status (phase 9b; was null)
    assert {e["ex"]: e["index_status"] for e in manifest["live"]["sessions"]} == status_of
    for row in rows:
        assert row["mode"] == "live" and row["attempt"] == 0 and row["status"] in ("ok", "ok_with_issues")
        assert row["stages"]["validation"] == "ok" and row["stages"]["prov"] == {"agentprov-prov/0.1": "ok"}
        assert row["stages"]["sem"] == {"agentdojo.suites@2": "ok"}  # D-31 and item 1
        assert {r["role"] for r in row["raw"]} == {"capture_log", "native_log"}
        header = json.loads((partial / row["paths"]["aer"]).read_text().splitlines()[0])
        kinds = {i["kind"] for i in header["instrumentation"]}
        assert "test_only" in kinds
    results = [json.loads(line) for line in (partial / "validation" / "results.jsonl").read_text().splitlines()]
    assert all(r["verdict"] == "pass" for r in results)
    # RPR-10: the stored AER is what an in-process re-mapping of the kept staging directory gives, byte for byte
    from capture_support import map_staged_session

    for row in rows:
        session = row["ex"][3:]
        again = map_staged_session(live_home / "staging" / session)
        assert again.data == (partial / row["paths"]["aer"]).read_bytes()
    # a second invocation resumes from the sealed evidence and executes nothing
    code, out, _err = _main(*argv)
    assert code == 0 and json.loads(out)["counters"]["attempted"] == 0
    assert json.loads(out)["counters"]["cells_done_before"] == 2


POISON_SENTINEL = "sk-agentprov-poison-sentinel-3b9e2d"


def test_a_poisoned_capture_log_from_the_real_worker_never_reaches_the_corpus(
    live_home: Path, in_repo: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poisoned-log path end to end (phase-8 follow-up; D-290). A scripted run passes no key to T2, so a test seam
    adds a sentinel to the worker's environment (and to T0's, as a key T0 read would be). The scripted model sends a
    tool call whose argument keys are the sentinel and the redaction marker: the response blob is redacted, but the
    ``tool.dispatch`` event's keys would collide once redacted, so the worker's scan fails, the log is poisoned and
    sealed ``errored`` with the constant ``capture.redact`` error. T0 quarantines the session: nothing is stored."""
    from agentprov_capture.redact import MARKER

    from agentprov.cli.live import worker as live_worker

    real = live_worker.worker_environment

    def with_sentinel(**kwargs: Any) -> dict[str, str]:
        return {**real(**kwargs), "FAKE_PROVIDER_API_KEY": POISON_SENTINEL}

    monkeypatch.setattr(live_worker, "worker_environment", with_sentinel)
    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", POISON_SENTINEL)
    arguments = json.dumps({POISON_SENTINEL: 1, MARKER: 2})
    script = tmp_path / "script.json"
    script.write_text(json.dumps([{"reply": "tool_calls", "calls": [
        {"name": "get_most_recent_transactions", "arguments": arguments, "id": "call_1"}]}]))
    corpus = tmp_path / "corpus"
    code, out, err = _main("run", "agentdojo", "--corpus", str(corpus), "--campaign", "poison", "--suite", "banking",
                           "--user-tasks", "user_task_1", "--benign", "only", "--llm-script", str(script),
                           "--max-attempts", "1", "--json", "--progress", "off")
    assert code == 1, err
    summary = json.loads(out)
    assert summary["counters"]["quarantined"] == 1 and summary["counters"]["derived"] == 0
    partial = Path(str(corpus) + ".partial")
    assert not list((partial / "raw").rglob("objects/**/*.*")) and (partial / "executions.jsonl").read_text() == ""
    (row,) = [json.loads(line) for line in (partial / "register.jsonl").read_text().splitlines()]
    assert row["code"] == "capture.quarantined" and "redaction scan failed" in row["detail"]
    (entry,) = json.loads((partial / "corpus.json").read_text())["live"]["sessions"]
    assert entry["status"] == "quarantined"
    staged = live_home / "staging" / entry["session"]
    (log,) = staged.glob("raw/capture/*.capture.jsonl")
    events = [json.loads(line) for line in log.read_bytes().splitlines()]
    assert [e["type"] for e in events[-2:]] == ["error", "session.end"]
    assert events[-2]["data"] == {"where": "capture.redact", "fatal": True, "exception": {
        "type": "RedactionError", "message": "redaction failed; the event or blob was not written"}}
    assert events[-1]["data"]["status"] == "errored"
    assert not [e for e in events if e["type"] == "tool.dispatch"]  # the failed event was not written
    assert POISON_SENTINEL.encode() not in log.read_bytes()  # the poisoned log holds no content of the failed event
    for blob in staged.glob("raw/blobs/sha256/*/*"):
        assert POISON_SENTINEL.encode() not in blob.read_bytes()  # the response blob was redacted
    corpus_bytes = b"".join(p.read_bytes() for p in partial.rglob("*") if p.is_file())
    for surface in (out.encode(), err.encode(), corpus_bytes):
        assert POISON_SENTINEL.encode() not in surface


def test_dry_run_with_the_real_worker_expands_the_plan(live_home: Path, in_repo: None, tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text(json.dumps(SCRIPT))
    code, out, err = _main("run", "agentdojo", "--corpus", str(tmp_path / "c"), "--campaign", "dry", "--suite", "banking",
                           "--user-tasks", "0-2", "--llm-script", str(script), "--dry-run", "--json", "--progress", "off")
    assert code == 0, err
    assert json.loads(out)["counters"] == {"cells_done_before": 0, "cells_planned": 3}
    assert not (tmp_path / "c.partial").exists()


def test_preflight_probe_through_the_real_worker(live_home: Path, in_repo: None, tmp_path: Path) -> None:
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps([{"reply": "tool_calls", "calls": [{"name": "get_probe_value",
                                                                     "args": {"key": "q7f3-probe"}}]}]))
    code, _out, err = _main("run", "agentdojo", "--preflight-only", "--llm-script", str(probe), "--progress", "off")
    assert code == 0, err
    assert "tool_calls=structured" in err and "roles=accepted (instruction_followed)" in err


@pytest.mark.parametrize(("step", "shown"), [
    ({"reply": "text", "content": "Probe received."}, "no evidence that the system message reached the model "
                                                      "(instruction_not_evidenced)"),
    ({"fail": "no_choices", "error": {"message": "role 'developer' is not supported"}},
     "rejected the stock message roles (error_object)"),
])
def test_preflight_refuses_a_2xx_that_does_not_show_the_roles_were_accepted(live_home: Path, in_repo: None,
                                                                           tmp_path: Path, step: Any, shown: str) -> None:
    """D-291 through the real worker: a 2xx reply is not enough for A9; the run refuses with exit 4."""
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps([step]))
    code, _out, err = _main("run", "agentdojo", "--preflight-only", "--llm-script", str(probe), "--progress", "off")
    assert code == 4, err
    assert "preflight (A9)" in err and shown in err
