"""D-704: ``agentprov jobs`` (start, list, show, follow, stop, kill, drain, resume, prune) against real detached jobs in
a temporary home (MN N.2.17)."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import NamedTuple

import pytest

from agentprov.cli.main import main

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX signals and sessions")


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Run]:
    from agentprov.jobs import manager

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    root = tmp_path / "checkout"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "sleeper.py").write_text("import signal, sys, time\n"
                                               "signal.signal(signal.SIGTERM, lambda *a: sys.exit(130))\n"
                                               "print('started', flush=True)\ntime.sleep(60)\n")
    monkeypatch.setattr(manager, "checkout_root", lambda: root)

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv[:2], "--progress", "off", *argv[2:]] if argv[:1] == ("jobs",) else list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _until_ended(cli: Callable[..., Run], job_id: str) -> dict[str, object]:
    end = time.monotonic() + 30
    while time.monotonic() < end:
        doc = json.loads(cli("jobs", "show", job_id, "--format", "json").out)
        if doc["state"] != "running":
            return doc
        time.sleep(0.1)
    raise AssertionError("not ended")


def test_start_list_show_and_the_exit_code(cli: Callable[..., Run]) -> None:
    started = cli("jobs", "start", "--label", "smoke", "--format", "json", "--", "info")
    assert started.code == 0, started.err
    job = json.loads(started.out)
    done = _until_ended(cli, job["job_id"][:12])  # a unique prefix
    assert done["exit_code"] == 0 and done["outcome"] == "ok" and done["label"] == "smoke"
    listed = json.loads(cli("jobs", "list", "--format", "json").out)
    assert listed["format"] == "agentprov-jobs-list/0.1" and [j["job_id"] for j in listed["jobs"]] == [job["job_id"]]
    assert json.loads(cli("jobs", "list", "--state", "running", "--format", "json").out)["jobs"] == []


def test_stop_kill_and_their_refusals(cli: Callable[..., Run]) -> None:
    job = json.loads(cli("jobs", "start", "--tool", "tools/sleeper.py", "--format", "json", "--", "x").out)
    time.sleep(1)
    assert cli("jobs", "drain", job["job_id"]).code == 4  # no control file
    assert cli("jobs", "kill", job["job_id"]).code == 2  # no --yes
    assert cli("jobs", "stop", job["job_id"]).code == 0
    assert _until_ended(cli, job["job_id"])["exit_code"] == 130
    assert cli("jobs", "stop", job["job_id"]).code == 2  # not running
    other = json.loads(cli("jobs", "start", "--tool", "tools/sleeper.py", "--format", "json", "--", "x").out)
    assert cli("jobs", "kill", other["job_id"], "--yes").code == 0
    assert _until_ended(cli, other["job_id"])["outcome"] == "killed"
    resumed = cli("jobs", "resume", other["job_id"], "--format", "json")
    assert resumed.code == 0 and json.loads(resumed.out)["subcommand_argv"] == ["x"]
    cli("jobs", "kill", json.loads(resumed.out)["job_id"], "--yes")


def test_usage_errors_and_refusals(cli: Callable[..., Run]) -> None:
    assert cli("jobs", "show", "nosuchjob").code == 2
    assert cli("jobs", "start", "--tool", "tools/../../etc/passwd.py", "--", "x").code == 4
    assert cli("jobs", "start", "--", "jobs", "list").code == 4  # a job never starts jobs
    assert cli("jobs", "start").code == 4  # nothing to run
    assert cli("jobs", "start", "--queue-cpu", "0", "--", "info").code == 2


def test_prune_lists_without_yes(cli: Callable[..., Run]) -> None:
    for _ in range(2):
        _until_ended(cli, json.loads(cli("jobs", "start", "--format", "json", "--", "info").out)["job_id"])
    listing = cli("jobs", "prune", "--keep", "0")
    assert listing.code == 0 and len(json.loads(cli("jobs", "list", "--format", "json").out)["jobs"]) == 2
    assert cli("jobs", "prune", "--keep", "0", "--yes").code == 0
    assert json.loads(cli("jobs", "list", "--format", "json").out)["jobs"] == []


def test_follow_prints_progress_until_the_end(cli: Callable[..., Run]) -> None:
    job = json.loads(cli("jobs", "start", "--format", "json", "--", "info").out)
    followed = cli("jobs", "follow", job["job_id"], "--timeout", "30")
    assert followed.code == 0
    events = [json.loads(line) for line in followed.out.splitlines() if line.strip()]
    assert events and events[-1].get("event") == "end"
    logged = cli("jobs", "follow", job["job_id"], "--log", "--timeout", "30")  # D-700: the Logs page's records
    records = [json.loads(line) for line in logged.out.splitlines() if line.strip()]
    assert logged.code == 0 and records and all("level" in r and "event" not in r for r in records)


def test_meta_is_recorded_as_scalars(cli: Callable[..., Run]) -> None:
    job = json.loads(cli("jobs", "start", "--meta", "call_cap=5", "--meta", "backend=autodojo", "--meta",
                         "devrun=true", "--format", "json", "--", "info").out)
    assert job["meta"] == {"call_cap": 5, "backend": "autodojo", "devrun": True}
    assert cli("jobs", "start", "--meta", "Bad Key=1", "--", "info").code == 2
    _until_ended(cli, job["job_id"])
    pruned = json.loads(cli("jobs", "prune", "--keep", "0", "--format", "json").out)
    assert [j["job_id"] for j in pruned["jobs"]] == [job["job_id"]] and pruned["deleted"] is False


# ---------------------------------------------------------------------------------------------- F-14 (D-704)
@pytest.mark.parametrize(("argv", "expected"), [
    (["validate", "--corpus", "corpora/x"], ["validate", "--corpus", "{cwd}/corpora/x"]),
    (["validate", "--corpus=corpora/x"], ["validate", "--corpus={cwd}/corpora/x"]),
    (["render", "--corpus", "c", "--out", "../out"], ["render", "--corpus", "{cwd}/c", "--out", "{parent}/out"]),
    (["stats", "--corpus", "a", "--corpus", "/abs/b"], ["stats", "--corpus", "{cwd}/a", "--corpus", "/abs/b"]),
    (["validate", "--corpus", "c", "--select", "unit=x"], ["validate", "--corpus", "{cwd}/c", "--select", "unit=x"]),
    (["info", "--format", "json"], ["info", "--format", "json"]),
])
def test_relative_path_options_are_resolved_against_the_callers_cwd(argv: list[str], expected: list[str],
                                                                     tmp_path: Path) -> None:
    """F-14: a job runs in its own folder, so ``jobs start`` makes relative path options absolute (the caller's cwd)."""
    from agentprov.cli.jobs import absolute_argv

    cwd = str(tmp_path / "work")
    want = [e.format(cwd=cwd, parent=str(tmp_path)) for e in expected]
    assert absolute_argv(argv, cwd) == want


def test_jobs_start_records_absolute_paths(cli: Callable[..., Run], tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    job = json.loads(cli("jobs", "start", "--writes", "out", "--format", "json", "--", "validate", "--corpus",
                         "corpora/mini").out)
    assert job["subcommand_argv"] == ["validate", "--corpus", str(work / "corpora" / "mini")]
    assert job["writes"] == [str(work / "out")]
    _until_ended(cli, job["job_id"])


@pytest.mark.parametrize(("argv", "expected"), [
    (["validate", "rel/aer.jsonl"], ["validate", "{cwd}/rel/aer.jsonl"]),
    (["validate", "--release", "a.jsonl", "b.jsonl"], ["validate", "--release", "{cwd}/a.jsonl", "{cwd}/b.jsonl"]),
    (["validate", "--tiers", "aer", "a.jsonl"], ["validate", "--tiers", "aer", "{cwd}/a.jsonl"]),
    (["inspect", "rel/target"], ["inspect", "{cwd}/rel/target"]),
    (["inspect", "./x.aer.jsonl"], ["inspect", "{cwd}/x.aer.jsonl"]),
    (["inspect", "ex_0123456789abc", "--corpus", "c"], ["inspect", "ex_0123456789abc", "--corpus", "{cwd}/c"]),
    (["inspect", "mycorpus"], ["inspect", "{cwd}/mycorpus"]),  # exists under the cwd: a path
    (["inspect", "/abs/t"], ["inspect", "/abs/t"]),
])
def test_relative_positional_paths_are_resolved_too(argv: list[str], expected: list[str], tmp_path: Path) -> None:
    """F-14 follow-up: path-kind positionals (``validate FILE…``; ``inspect TARGET`` when it is a path, never an
    execution id) are made absolute from the parser's own metadata, as options are."""
    from agentprov.cli.jobs import absolute_argv

    cwd = tmp_path / "work"
    (cwd / "mycorpus").mkdir(parents=True)
    assert absolute_argv(argv, str(cwd)) == [e.format(cwd=cwd) for e in expected]


def test_a_tools_arguments_are_left_alone(cli: Callable[..., Run], tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``--tool``'s own arguments are its own business (it runs in the checkout): never rewritten."""
    from agentprov.jobs.manager import JobManager, SpawnRefused

    seen: list[tuple[str, ...]] = []

    def spawn(self: JobManager, req: Any, **_kw: Any) -> Any:
        seen.append(req.argv)
        raise SpawnRefused("captured", "test.captured")

    monkeypatch.setattr(JobManager, "spawn", spawn)
    monkeypatch.chdir(tmp_path)
    cli("jobs", "start", "--tool", "tools/check_unicode.py", "--", "rel/x", "--corpus", "c")
    cli("jobs", "start", "--", "validate", "rel/x")
    assert seen == [("rel/x", "--corpus", "c"), ("validate", str(tmp_path / "rel" / "x"))]
