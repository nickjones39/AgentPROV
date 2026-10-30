"""``agentprov run`` against a fake backend environment: the T0 controls of live runs (K.8.4(1, 5, 7), K.12.16, SEC-14,
SEC-25; MN N.2.1, N.2.1b; D.11.3 rules 1-4; G.3.6, G.6.3, G.6.4).

The fake environment (``live_fake.make_fake_env``) is a venv of the running interpreter with fake dist-info and a
fake ``agentprov_backend.worker`` whose behaviour is baked in; no benchmark package is installed or imported, and no test
uses the network or a key. Each test gets its own ``$AGENTPROV_HOME``.
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

from live_fake import SENTINEL, WORKER_ONLY_SECRET, make_fake_env, repo_root  # noqa: E402

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


def _run(cli: Callable[..., Run], tmp_path: Path, script: str, *extra: str) -> Run:
    return cli("run", "agentdojo", "--corpus", str(tmp_path / "corpus"), "--campaign", "t", "--suite", "banking",
               "--llm-script", script, "--max-attempts", "1", "--json", "--progress", "off", *extra)


def _manifest(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "corpus.partial" / "corpus.json").read_text())


def _register(tmp_path: Path) -> list[dict[str, Any]]:
    data = (tmp_path / "corpus.partial" / "register.jsonl").read_text().splitlines()
    return [json.loads(line) for line in data]


def _objects(tmp_path: Path) -> list[bytes]:
    root = tmp_path / "corpus.partial" / "raw" / "objects"
    return [p.read_bytes() for p in root.rglob("*") if p.is_file()] if root.is_dir() else []


def _all_corpus_bytes(tmp_path: Path) -> bytes:
    root = tmp_path / "corpus.partial"
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file()) if root.is_dir() else b""


# ---------------------------------------------------------------------------------------------- honest worker
def test_a_session_is_stored_with_a_capture_origin_and_ledgered(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    run = _run(cli, tmp_path, script)
    assert run.code in (0, 1), run.err
    live = _manifest(tmp_path)["live"]
    (entry,) = live["sessions"]
    assert entry["cell_key"] == "banking/user_task_1/none/none" and entry["attempt"] == 0 and entry["status"] == "complete"
    assert live["test_only"] is True and _manifest(tmp_path)["synthetic"] is True
    origins = [json.loads(line) for line in (tmp_path / "corpus.partial" / "raw" / "origins.jsonl").read_text().splitlines()]
    assert origins and all(o["origin"] == {"kind": "capture", "session": entry["session"]} for o in origins)
    # the ledger entry names the index row's status (phase-8 behaviour was null: the row was still queued, phase 9b)
    rows = [json.loads(line) for line in (tmp_path / "corpus.partial" / "executions.jsonl").read_text().splitlines()]
    (row,) = [r for r in rows if r["ex"] == entry["ex"]]
    assert entry["index_status"] == row["status"] and entry["index_status"] is not None
    # the staging directory of a cleanly ingested session is removed; the T2 home stays empty and is removed
    assert not (home / "staging" / entry["session"]).exists()
    assert not any((home / "t2home").iterdir())


def test_a_relative_agentprov_home_runs_like_the_absolute_one(home: Path, tmp_path: Path, cli, script: str,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """CC-12: ``$AGENTPROV_HOME`` given relative to the current directory is made absolute, so the worker's interpreter
    and session directories do not resolve against the worker's own staging cwd."""
    make_fake_env(home, "ok")
    monkeypatch.setenv("AGENTPROV_HOME", os.path.relpath(home, Path.cwd()))
    run = _run(cli, tmp_path, script)
    assert run.code in (0, 1), run.err
    assert run.json()["counters"]["conclusive"] == 1


def test_resume_skips_nothing_until_a_conclusive_attempt_and_counts_attempts_across_invocations(
    home: Path, tmp_path: Path, cli, script: str
) -> None:
    make_fake_env(home, "hang")
    first = _run(cli, tmp_path, script, "--cell-timeout", "3", "--max-attempts", "2")
    assert first.code == 1 and first.json()["counters"]["attempted"] == 2
    again = _run(cli, tmp_path, script, "--cell-timeout", "3", "--max-attempts", "2")
    assert again.json()["counters"]["attempted"] == 0  # --max-attempts is counted across invocations (N.1.8(4))
    assert [e["attempt"] for e in _manifest(tmp_path)["live"]["sessions"]] == [0, 1]


def test_dry_run_prints_the_plan_and_writes_nothing(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    before = sorted(str(p) for p in home.rglob("*"))
    run = _run(cli, tmp_path, script, "--dry-run")
    assert run.code == 0, run.err
    assert run.json()["counters"] == {"cells_done_before": 0, "cells_planned": 1}
    assert "banking/user_task_1/none/none" in run.err
    assert sorted(str(p) for p in home.rglob("*")) == before
    assert not (tmp_path / "corpus.partial").exists()


# ---------------------------------------------------------------------------------------------- hostile worker (K.8.4(7))
@pytest.mark.parametrize(("mode", "code"), [
    ("dotdot", "ingest.archive.traversal"),
    ("absolute", "ingest.archive.traversal"),  # an absolute name is a traversal form (G.3.6)
    ("symlink", "ingest.path.symlink"),
    ("hardlink", "ingest.path.hardlink"),
])
def test_hostile_reports_are_rejected_with_their_ingest_code(home: Path, tmp_path: Path, cli, script: str, mode: str,
                                                             code: str) -> None:
    make_fake_env(home, mode)
    run = _run(cli, tmp_path, script)
    assert run.code == 1
    assert any(r["code"] == code and r["stage"] == "ingest" and r["disposition"] == "not_imported" for r in _register(tmp_path))
    assert run.json()["counters"]["rejected_files"] >= 1
    stored = _objects(tmp_path)
    assert b"outside" not in stored and b"private" not in stored  # nothing outside staging reached the corpus
    (entry,) = _manifest(tmp_path)["live"]["sessions"]
    assert (home / "staging" / entry["session"]).is_dir()  # kept for inspection


def test_unreported_files_are_ignored_and_reported(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "unreported")
    run = _run(cli, tmp_path, script)
    assert run.json()["counters"]["unreported_files"] == 1
    assert any("unreported" in n for n in run.json()["notices"])
    assert b"planted" not in _objects(tmp_path)


def test_a_reported_digest_that_does_not_verify_is_a_capture_error_and_the_attempt_is_not_conclusive(
    home: Path, tmp_path: Path, cli, script: str
) -> None:
    make_fake_env(home, "mismatch")
    run = _run(cli, tmp_path, script)
    assert run.code == 1
    (entry,) = _manifest(tmp_path)["live"]["sessions"]
    assert entry["capture_error"] is True
    assert any(r["code"] == "map.capture_error" and "does not verify" in r["detail"] for r in _register(tmp_path))
    assert run.json()["counters"]["inconclusive"] == 1
    assert _objects(tmp_path)  # the files were ingested under their actual digests (D.11.3 rule 2)


def test_a_secret_in_a_staged_file_quarantines_the_session(home: Path, tmp_path: Path, cli, script: str,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", SENTINEL)  # a secret T0 holds (never passed to T2)
    make_fake_env(home, "secret")
    run = _run(cli, tmp_path, script)
    assert run.code == 1
    assert run.json()["counters"]["quarantined"] == 1
    assert _objects(tmp_path) == []  # nothing from the session is stored
    (row,) = [r for r in _register(tmp_path) if r["code"] == "capture.quarantined"]
    assert row["stage"] == "capture" and row["disposition"] == "not_imported"
    (entry,) = _manifest(tmp_path)["live"]["sessions"]
    assert entry["status"] == "quarantined" and (home / "staging" / entry["session"]).is_dir()
    for surface in (run.out, run.err, _all_corpus_bytes(tmp_path).decode("utf-8", "replace")):
        assert SENTINEL not in surface


def test_a_secret_in_a_reported_file_the_directory_walk_skips_still_quarantines(
    home: Path, tmp_path: Path, cli, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CC-2: T0 scans the bytes it stores. A reported ``._*`` file holds the key; the directory walk of the re-scan skips
    such names, but the collected bytes are scanned too, so the session is quarantined and nothing is stored."""
    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", SENTINEL)
    make_fake_env(home, "junksecret")
    run = _run(cli, tmp_path, script)
    assert run.json()["counters"]["quarantined"] == 1
    assert _objects(tmp_path) == []
    for surface in (run.out, run.err, _all_corpus_bytes(tmp_path).decode("utf-8", "replace")):
        assert SENTINEL not in surface


def test_a_poisoned_capture_log_reported_with_another_role_is_still_quarantined(
    home: Path, tmp_path: Path, cli, script: str
) -> None:
    """CC-3: the role of ``raw/capture/<session>.capture.jsonl`` follows its label, not the worker's report, so a
    poisoned log reported as ``supporting`` still quarantines the session (D-290; D.11.3)."""
    make_fake_env(home, "poisoned_mislabelled")
    run = _run(cli, tmp_path, script)
    assert run.json()["counters"]["quarantined"] == 1
    assert _objects(tmp_path) == []
    assert (tmp_path / "corpus.partial" / "executions.jsonl").read_text() == ""


def test_a_poisoned_capture_log_quarantines_the_session_and_never_reaches_the_corpus(
    home: Path, tmp_path: Path, cli, script: str
) -> None:
    """D-290: the worker's redaction scan failed and sealed the log ``errored`` with the constant ``capture.redact``
    error. No staged file holds a value T0 knows, so only the poisoned log quarantines the session: nothing stored."""
    make_fake_env(home, "poisoned")
    run = _run(cli, tmp_path, script)
    assert run.code == 1
    assert run.json()["counters"]["quarantined"] == 1 and run.json()["counters"]["derived"] == 0
    assert _objects(tmp_path) == []
    assert (tmp_path / "corpus.partial" / "executions.jsonl").read_text() == ""
    (row,) = [r for r in _register(tmp_path) if r["code"] == "capture.quarantined"]
    assert row["stage"] == "capture" and row["disposition"] == "not_imported"
    assert "redaction scan failed" in row["detail"] and "literal secret" not in row["detail"]
    (entry,) = _manifest(tmp_path)["live"]["sessions"]
    assert entry["status"] == "quarantined" and entry["index_status"] is None
    staged = home / "staging" / entry["session"]
    assert staged.is_dir()  # kept for the user
    (log,) = staged.glob("raw/capture/*.capture.jsonl")
    events = [json.loads(line) for line in log.read_bytes().splitlines()]
    assert [e["type"] for e in events[-2:]] == ["error", "session.end"]
    assert events[-2]["data"]["where"] == "capture.redact" and events[-1]["data"]["status"] == "errored"
    assert "quarantined: the worker's redaction scan failed" in " ".join(run.json()["notices"])
    for surface in (run.out, run.err, _all_corpus_bytes(tmp_path).decode("utf-8", "replace"),
                    log.read_text("utf-8")):
        assert WORKER_ONLY_SECRET not in surface
    again = _run(cli, tmp_path, script)  # a quarantined attempt counts and is not re-attempted (--max-attempts 1)
    assert again.json()["counters"]["attempted"] == 0


def test_a_killed_worker_leaves_a_parent_sealed_aborted_session(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "hang")
    run = _run(cli, tmp_path, script, "--cell-timeout", "3")
    assert run.code == 1
    (entry,) = _manifest(tmp_path)["live"]["sessions"]
    assert entry["status"] == "aborted" and entry["parent_appended"] is True and entry["parent_note"] == "timeout"
    logs = [o for o in _objects(tmp_path) if b'"session.start"' in o]
    (log,) = logs
    last = json.loads(log.splitlines()[-1])
    assert last["type"] == "session.end" and last["data"]["appended_by"] == "parent" and last["data"]["status"] == "aborted"
    from agentprov_capture.verify import verify_chain

    from agentprov.ingest.loaders import strict_json_loads

    lines = log.splitlines(keepends=True)
    report = verify_chain(lines, [strict_json_loads(line[:-1]) for line in lines])
    assert report.sealed and report.appended_by == "parent"
    assert run.json()["counters"]["inconclusive"] == 1


def test_the_worker_environment_is_the_allowlist(home: Path, tmp_path: Path, cli, script: str,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UV_INDEX_URL", "https://example.invalid/simple")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "uvcache"))
    monkeypatch.setenv("UNRELATED_SERVICE_TOKEN", "tok-unrelated-1234567890")
    make_fake_env(home, "envdump")
    _run(cli, tmp_path, script)
    dumps = [json.loads(o) for o in _objects(tmp_path) if o.startswith(b'{"environ"')]
    (dump,) = dumps
    environ = dump["environ"]
    # __CF_USER_TEXT_ENCODING is added by macOS CoreFoundation inside the child itself; the parent never passes it
    allowed = {"PATH", "HOME", "LANG", "TZ", "AGENTPROV_BLOCK_NETWORK", "SYSTEMROOT", "__CF_USER_TEXT_ENCODING"}
    assert set(environ) <= allowed, sorted(environ)
    assert environ["AGENTPROV_BLOCK_NETWORK"] == "1"
    assert Path(environ["HOME"]).parent == home / "t2home" and environ["HOME"] != str(Path.home())
    assert not any(k.startswith("UV_") for k in environ)
    assert "tok-unrelated-1234567890" not in json.dumps(dump)
    assert dump["home_entries"] == []


# ---------------------------------------------------------------------------------------------- identity (K.8.4(1, 5))
def test_no_built_environment_exits_3(home: Path, tmp_path: Path, cli, script: str) -> None:
    run = _run(cli, tmp_path, script)
    assert run.code == 3 and not (tmp_path / "corpus.partial").exists()


@pytest.mark.parametrize("tamper", ["guarded_source", "record", "marker_lock", "marker_status"])
def test_a_tampered_environment_exits_3_and_runs_nothing(home: Path, tmp_path: Path, cli, script: str, tamper: str) -> None:
    from agentprov.cli.live import envs

    env = make_fake_env(home, "ok")
    sp = envs.site_packages(env)
    if tamper == "guarded_source":
        (sp / "agentdojo" / "benchmark.py").write_text("# changed\n")
    elif tamper == "record":
        record = next(sp.glob("agentdojo-*.dist-info")) / "RECORD"
        record.write_text(record.read_text() + "agentdojo/extra.py,,\n")
    else:
        marker = json.loads((env / envs.ENV_MARKER).read_text())
        if tamper == "marker_lock":
            marker["lock_sha256"] = "0" * 64
        else:
            marker["status"] = "building"
        (env / envs.ENV_MARKER).write_text(json.dumps(marker))
    run = _run(cli, tmp_path, script)
    assert run.code == 3, run.err
    assert not (tmp_path / "corpus.partial").exists()
    assert not (home / "staging").exists() or not any((home / "staging").iterdir())


def test_a_hello_identity_mismatch_exits_3_before_any_cell(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "badhello")
    run = _run(cli, tmp_path, script)
    assert run.code == 3 and "IdentityMismatch" in run.err
    assert not (tmp_path / "corpus.partial").exists()


def test_a_capture_identity_mismatch_aborts_the_campaign_with_exit_3(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "badcapture")
    run = _run(cli, tmp_path, script)
    assert run.code == 3 and "identity_digests" in run.err
    sessions = [p for p in (home / "staging").iterdir() if not p.name.startswith("worker-")]
    assert sessions  # the session stays in staging for inspection; nothing of it was stored
    assert _objects(tmp_path) == []


def test_preflight_only_with_a_script_runs_the_probe(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--preflight-only", "--llm-script", script, "--json", "--progress", "off")
    assert run.code == 0, run.err
    assert "preflight: reachable=True" in run.err and run.json()["counters"] == {"probes": 1}


def test_two_workers_run_repeats_concurrently_and_each_attempt_is_its_own_session(
    home: Path, tmp_path: Path, cli, script: str
) -> None:
    make_fake_env(home, "ok")
    run = _run(cli, tmp_path, script, "--jobs", "2", "--repeats", "2", "--start-stagger", "0.2")
    assert run.json()["counters"]["attempted"] == 2 and run.json()["counters"]["cells_planned"] == 2
    live = _manifest(tmp_path)["live"]
    assert sorted(e["repeat"] for e in live["sessions"]) == [0, 1] and live["jobs"] == 2
    assert len({e["session"] for e in live["sessions"]}) == 2


# ---------------------------------------------------------------------------------------------- consent (N.1.11(3))
#: An API endpoint campaign states both caps (D-725); test_run_policy.py covers their refusals.
API_CAPS = ("--max-calls", "100", "--max-cost-usd", "1", "--price-in", "1", "--price-out", "1")


@pytest.fixture
def real_model(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A real-model run against the fake environment, with no key, no network and no paid call: the planned-status gate
    admits it as if scripted, ``.env`` is a canned mapping with a placeholder value, and the probe is recorded instead of
    run. Returns the order in which consent and the probe were reached."""
    from agentprov.cli import run as run_mod

    calls: list[str] = []
    gate = run_mod._live_capability
    monkeypatch.setattr(run_mod, "_live_capability", lambda source, result, *, scripted: gate(source, result, scripted=True))
    monkeypatch.setattr(run_mod, "_read_env_file", lambda args, root: {"DEEPSEEK_API_KEY": "placeholder-not-a-key",
                                                                       "DEEPSEEK_MODEL": "placeholder-model"})
    consent = run_mod._consent

    def record_consent(*args: Any, **kwargs: Any) -> None:
        calls.append("consent")
        consent(*args, **kwargs)

    def record_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("preflight")
        raise run_mod.LiveRefused("probe reached (test stop)", code="cli.refused.test_stop")

    monkeypatch.setattr(run_mod, "_consent", record_consent)
    monkeypatch.setattr(run_mod, "_preflight", record_probe)
    return calls


def test_a_real_model_run_without_consent_makes_no_preflight_call(home: Path, tmp_path: Path, cli, real_model) -> None:
    """CLI robustness item 2: the preflight probe is a paid call, so it never runs before consent."""
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--model", "deepseek", "--containment", "vm", "--corpus", str(tmp_path / "corpus"),
              "--campaign", "t", "--suite", "banking", *API_CAPS, "--progress", "off")
    assert run.code == 4 and "needs consent" in run.err, run.err
    assert "up to 3 preflight probe call(s), then up to" in run.err  # D-729
    assert real_model == ["consent"]


def test_consent_comes_before_the_preflight_probe(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--model", "deepseek", "--containment", "vm", "--corpus", str(tmp_path / "corpus"),
              "--campaign", "t", "--suite", "banking", "--i-consent-to-api-costs", *API_CAPS, "--progress", "off")
    assert run.code == 4 and "probe reached" in run.err, run.err
    assert real_model == ["consent", "preflight"]


def test_preflight_only_with_a_real_model_needs_consent(home: Path, tmp_path: Path, cli, real_model) -> None:
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--preflight-only", "--model", "deepseek", "--containment", "vm", "--progress", "off")
    assert run.code == 4 and "needs consent" in run.err and "--preflight-only; no cells" in run.err, run.err
    assert real_model == ["consent"]
    run = cli("run", "agentdojo", "--preflight-only", "--model", "deepseek", "--containment", "vm",
              "--i-consent-to-api-costs", "--progress", "off")
    assert real_model == ["consent", "consent", "preflight"]


# ---------------------------------------------------------------------------------------------- shared state (G6a)
def test_a_run_refuses_while_its_environment_is_being_built(home: Path, tmp_path: Path, cli, script: str) -> None:
    """CLI robustness item 3: a run never starts on an environment a build is replacing; it registers as a user
    otherwise, and the registration is gone when the run ends."""
    import platform
    import subprocess

    from agentprov.cli.live import envs

    make_fake_env(home, "ok")
    name = envs.backend_project("agentdojo", repo_root()).env_name
    lock = home / "locks" / "envs" / f"{name}.lock"
    lock.parent.mkdir(parents=True)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        lock.write_text(json.dumps({"command": "backends build", "host": platform.node(), "pid": child.pid,
                                    "started": "2026-10-14T10:00:00Z"}))
        refused = _run(cli, tmp_path, script)
    finally:
        child.kill()
        child.wait()
    assert refused.code == 4 and "being built" in refused.err, refused.err
    assert not (tmp_path / "corpus.partial").exists()
    ran = _run(cli, tmp_path, script)  # the builder is gone: its lock is stale and ignored
    assert ran.code in (0, 1), ran.err
    assert not any((home / "locks" / "envs" / f"{name}.users").iterdir())
    assert not any((home / "locks" / "staging").iterdir())


# ---------------------------------------------------------------------------------------------- core review C fixes
def test_preflight_only_with_dry_run_is_a_usage_error(home: Path, cli, script: str) -> None:
    """CC-25: the combination spawned the probe worker (a model call for a real endpoint) and left staging behind."""
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--preflight-only", "--llm-script", script, "--dry-run", "--progress", "off")
    assert run.code == 2 and "--preflight-only and --dry-run are exclusive" in run.err
    assert not (home / "staging").exists() or not any((home / "staging").iterdir())


def test_the_hello_and_plan_worker_gets_no_key_and_no_network(home: Path, tmp_path: Path, cli, real_model,
                                                             monkeypatch) -> None:
    """CC-29: op_plan needs neither the API key nor the network, also for a real-model --dry-run."""
    from agentprov.cli import run as run_mod

    seen: list[dict[str, str]] = []

    def capture(argv: Any, env: dict[str, str], *a: Any, **k: Any) -> Any:
        seen.append(env)
        raise run_mod.LiveRefused("plan reached (test stop)", code="cli.refused.test_stop")

    monkeypatch.setattr(run_mod, "_hello_and_plan", capture)
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--model", "deepseek", "--containment", "vm", "--corpus", str(tmp_path / "corpus"),
              "--campaign", "t", "--suite", "banking", "--dry-run", *API_CAPS, "--progress", "off")
    assert run.code == 4 and "plan reached" in run.err, run.err
    (env,) = seen
    assert "DEEPSEEK_API_KEY" not in env and env["AGENTPROV_BLOCK_NETWORK"] == "1"
    assert "placeholder-not-a-key" not in json.dumps(env)


def test_the_dry_run_counts_resume_state_like_the_real_run(home: Path, tmp_path: Path, cli, script: str) -> None:
    """CC-26: the dry run counted a ledger entry as done although its capture log was no longer stored; the real run
    re-attempts such a unit. Both now use the campaign's rule."""
    make_fake_env(home, "ok")
    first = _run(cli, tmp_path, script)
    assert first.code in (0, 1), first.err
    (entry,) = _manifest(tmp_path)["live"]["sessions"]
    dry = _run(cli, tmp_path, script, "--dry-run")
    assert dry.json()["counters"]["cells_done_before"] == 1
    sha = entry["capture_sha256"]
    for obj in (tmp_path / "corpus.partial" / "raw" / "objects").rglob(f"{sha}.*"):
        obj.chmod(0o600)
        obj.unlink()
    dry = _run(cli, tmp_path, script, "--dry-run")
    real = _run(cli, tmp_path, script)
    assert dry.json()["counters"]["cells_done_before"] == real.json()["counters"]["cells_done_before"] == 0


# ---------------------------------------------------------------------------------------------- --env-stdin (D-395)
class _Stdin:
    def __init__(self, data: bytes) -> None:
        import io

        self.buffer = io.BytesIO(data)

    def isatty(self) -> bool:
        return False


@pytest.fixture
def stdin_run(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[dict[str, str]]]:
    """A real-model run fed by ``--env-stdin``: the planned gate admits it as if scripted, ``.env`` must never be read,
    and the probe records the T2 environment it would get instead of making a call."""
    from agentprov.cli import run as run_mod

    gate = run_mod._live_capability
    monkeypatch.setattr(run_mod, "_live_capability", lambda source, result, *, scripted: gate(source, result, scripted=True))

    def no_dotenv(*a: Any, **k: Any) -> None:
        raise AssertionError(".env was read although --env-stdin was given")

    monkeypatch.setattr(run_mod, "_read_env_file", no_dotenv)
    seen: list[dict[str, str]] = []

    def probe(argv: Any, env_for: Any, *a: Any, **k: Any) -> dict[str, Any]:
        seen.append(env_for(Path("/nonexistent-t2home")))
        raise run_mod.LiveRefused("probe reached (test stop)", code="cli.refused.test_stop")

    monkeypatch.setattr(run_mod, "_preflight", probe)

    def feed(data: bytes) -> list[dict[str, str]]:
        monkeypatch.setattr(sys, "stdin", _Stdin(data))
        return seen

    return feed


ENV_STDIN_KEY = "placeholder-stdin-key-0123456789"
STDIN_ARGS = ("run", "agentdojo", "--preflight-only", "--model", "deepseek", "--containment", "vm", "--env-stdin",
              "--i-consent-to-api-costs", "--progress", "off")


def test_env_stdin_hands_the_key_to_the_worker_only_and_never_reads_dotenv(home: Path, cli, stdin_run) -> None:
    make_fake_env(home, "ok")
    seen = stdin_run(json.dumps({"DEEPSEEK_API_KEY": ENV_STDIN_KEY, "DEEPSEEK_MODEL": "placeholder-model"}).encode())
    run = cli(*STDIN_ARGS, "--json")
    assert run.code == 4 and "probe reached" in run.err, run.err
    (env,) = seen
    assert env["DEEPSEEK_API_KEY"] == ENV_STDIN_KEY
    assert ENV_STDIN_KEY not in run.out + run.err and "env_stdin" in run.json()["options"]
    assert ENV_STDIN_KEY not in json.dumps(run.json())


@pytest.mark.parametrize("data, message", [
    (b"x" * (64 * 1024 + 1), "larger than 64 KiB"),
    (b'{"DEEPSEEK_API_KEY": "a", "DEEPSEEK_API_KEY": "b"}', "not one strict JSON object"),
    (b"[]", "not one strict JSON object"),
    (b'{"DEEPSEEK_API_KEY": 7}', "is not a string"),
    (b'{"HOME_SECRET_TOKEN": "' + ENV_STDIN_KEY.encode() + b'"}', "is not a variable of endpoints.toml"),
], ids=["oversize", "duplicate-key", "not-object", "not-string", "unknown-name"])
def test_env_stdin_refuses_anything_but_one_small_object_of_known_names(home: Path, cli, stdin_run, data: bytes,
                                                                       message: str) -> None:
    make_fake_env(home, "ok")
    stdin_run(data)
    run = cli(*STDIN_ARGS)
    assert run.code == 2 and message in run.err, run.err
    assert ENV_STDIN_KEY not in run.err


def test_env_stdin_is_exclusive_with_env_file_and_with_a_script(home: Path, cli, stdin_run, tmp_path: Path,
                                                                script: str) -> None:
    stdin_run(b"{}")
    assert "exclusive" in cli(*STDIN_ARGS, "--env-file", str(tmp_path / "e")).err
    run = cli("run", "agentdojo", "--preflight-only", "--llm-script", script, "--env-stdin", "--progress", "off")
    assert run.code == 2 and "scripted run needs none" in run.err


# ---------------------------------------------------------------------------------------------- D-525 live pieces
def test_run_skip_prov_conformance_marks_the_live_corpus(home: Path, tmp_path: Path, cli, script: str) -> None:
    """G2c-5 for generated corpora: the same mark as an import's, only when the flag is used."""
    make_fake_env(home, "ok")
    run = _run(cli, tmp_path, script, "--skip-prov-conformance")
    assert run.code in (0, 1), run.err
    assert _manifest(tmp_path)["validation"] == {"prov_conformance": "skipped"}
    assert any("--skip-prov-conformance" in n for n in run.json()["notices"])
    stage = next(s for s in json.loads((tmp_path / "corpus.partial" / "derivation.json").read_text())["stages"]
                 if s["stage"] == "validation")
    assert stage["skipped"] == ["tier4:agentprov-prov/0.1"]


def test_a_drained_campaign_starts_no_new_attempt(home: Path, tmp_path: Path, cli, script: str, monkeypatch) -> None:
    """D-394 for run: a drain accepted before scheduling leaves nothing started, and says so; resumable."""
    from agentprov import drain

    make_fake_env(home, "ok")
    with monkeypatch.context() as patched:
        patched.setattr(drain, "draining", lambda: True)
        run = _run(cli, tmp_path, script)
    assert run.json()["counters"]["attempted"] == 0
    assert any(n.startswith("drained (--control-file)") for n in run.json()["notices"])
    drain.reset()
    again = _run(cli, tmp_path, script)
    assert again.json()["counters"].get("attempted") == 1, again.err
