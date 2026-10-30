"""The job manager, followers and batches against a fake CLI (design §4, §5, §14; D-392)."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest
from agentprov.jobs.follow import LogRecord, LogRing, ProgressState, Rates, TailReader, eta_text

from agentprov_gui.jobs import batch as batch_client
from agentprov_gui.jobs.batch import Batch
from agentprov_gui.jobs.commands import FORMS, FormError, JobSpec, build_spec, tier_of_argv
from agentprov_gui.jobs.manager import CliLocator, JobManager, SpawnRefused, atomic_write_json, read_json

FAKE = Path(__file__).parent / "fake" / "fake_cli.py"
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX signals")


def manager(home: Path) -> JobManager:
    return JobManager(home, CliLocator(None, (sys.executable, str(FAKE))))


def spec(*argv: str, writes: tuple[str, ...] = (), slot: str | None = None, tier: str = "R1") -> JobSpec:
    return JobSpec("import", ("import", *argv), tier, "test", writes=writes, slot=slot)


def wait_end(m: JobManager, job_id: str, timeout: float = 20) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if m.jobs[job_id].state != "running" and m.refresh():
            return
        m.refresh()
        time.sleep(0.05)
    raise AssertionError("job did not end")


# ----------------------------------------------------------------------------------------------- forms and tiers
def test_tiers_come_from_the_final_argv() -> None:
    assert tier_of_argv(["verify", "--corpus", "x"], "R0") == "R0"
    assert tier_of_argv(["verify", "--against-pins", "--allow-network"], "R0") == "R2"
    assert tier_of_argv(["import", "x", "--dry-run"], "R1") == "R0"
    assert tier_of_argv(["import", "x", "--fetch", "--dry-run"], "R1") == "R2"
    s = build_spec(FORMS["verify"], {"corpus": "/c", "against_pins": True, "allow_network": True})
    assert s.tier == "R2"
    s = build_spec(FORMS["validate"], {"corpus": "/c"}, extra="--allow-network")  # not a validate field (GR-47)
    assert s.tier == "R2"


@pytest.mark.parametrize("bad", ["--show-content", "--env-file x", "--log-content", "--progress-file=x", "--json"])
def test_refused_options(bad: str) -> None:
    with pytest.raises(FormError):
        build_spec(FORMS["validate"], {"corpus": "/c"}, extra=bad)


_DD = "-" * 2  # GR-1: hostile flags are built from fragments at runtime


@pytest.mark.parametrize(("form", "values"), [
    ("import", {"source": _DD + "log-content", "corpus": "/c"}),
    ("render", {"corpus": "/c", "ex": "ex_1 " + _DD + "log-content"}),
    ("render", {"corpus": "/c", "ex": ["ex_1", _DD + "log-file", "/tmp/x"]}),
    ("info", {"source": _DD + "show-content"}),
    ("validate", {"corpus": _DD + "json"}),
])
def test_field_values_cannot_become_options(form: str, values: dict[str, object]) -> None:
    """GR-1: a text, path, positional or list value that starts with "-" would be parsed as a flag (a refused one)."""
    with pytest.raises(FormError, match="must not start with"):
        build_spec(FORMS[form], values)


def test_refused_options_are_named_wherever_they_are_typed() -> None:
    """GR-1: a refused option in "Additional options" is refused even when the positional moved there too."""
    with pytest.raises(FormError, match=_DD + "log-content"):
        build_spec(FORMS["info"], {}, extra="agentdojo " + _DD + "log-content=1")
    ok = build_spec(FORMS["render"], {"corpus": "/c", "ex": "ex_1 ex_2"})
    assert ok.argv.count("ex_1") == 1 and "ex_2" in ok.argv
    s = build_spec(FORMS["import"], {"source": "agentdojo", "corpus": "/c"}, conformance=False,
                   conformance_option="--skip-prov-conformance")
    assert "--skip-prov-conformance" in s.argv


def test_release_forbids_filters_and_purge_needs_a_digest() -> None:
    with pytest.raises(FormError):
        build_spec(FORMS["import"], {"source": "s", "corpus": "/c", "release": True, "limit": 3})
    with pytest.raises(FormError):
        build_spec(FORMS["purge"], {"object": "abc", "reason": "secret", "corpus": "/c"})
    ok = build_spec(FORMS["purge"], {"object": "sha256:" + "a" * 64, "reason": "secret", "corpus": "/c"})
    assert ok.destructive and ok.argv[-1].startswith("sha256:") and ok.writes == ("/c",)


@pytest.mark.parametrize("extra", [
    _DD + "skip-prov-conformance", _DD + "skip-prov-conformance=1", _DD + "control-file /x.json",
    _DD + "control-file=/x.json"])
@pytest.mark.parametrize("form", ["import", "derive"])
def test_conformance_and_control_options_are_refused_in_additional_options(form: str, extra: str) -> None:
    """GR-2: the D-432 box is the only route to the conformance skip; the job manager owns the control file."""
    values = {"source": "s", "corpus": "/c"} if form == "import" else {"corpus": "/c", "out": "/n"}
    with pytest.raises(FormError, match="not allowed"):
        build_spec(FORMS[form], values, extra=extra, conformance_option=_DD + "skip-prov-conformance")
    with pytest.raises(FormError):
        build_spec(FORMS[form], {**values, "release": True}, extra=extra)


@pytest.mark.parametrize("extra", [_DD + "limit=5", _DD + "select=suite=x", _DD + "sample=3", _DD + "in-process",
                                   _DD + "limit 5"])
def test_release_forbids_filters_given_with_an_equals_sign(extra: str) -> None:
    """GR-2: the release filter check compares option names, so ``--limit=5`` is refused like ``--limit 5``. A filter
    the form has as a field is refused as one (GR-47)."""
    with pytest.raises(FormError, match=r"Release mode forbids|is a form field"):
        build_spec(FORMS["import"], {"source": "s", "corpus": "/c", "release": True}, extra=extra)


def test_conformance_box_needs_the_cli_option() -> None:
    with pytest.raises(FormError):
        build_spec(FORMS["import"], {"source": "s", "corpus": "/c"}, conformance=False)
    s = build_spec(FORMS["import"], {"source": "s", "corpus": "/c"}, conformance=False,
                   conformance_option="--skip-prov-conformance")
    assert "--skip-prov-conformance" in s.argv and s.conformance_skipped and s.notes


def test_recompute_dry_run_writes_nothing() -> None:
    s = build_spec(FORMS["recompute"], {"corpus": "/c"})
    assert "--dry-run" in s.argv and s.writes == () and s.tier == "R0"
    s2 = build_spec(FORMS["recompute"], {"corpus": "/c", "dry_run": False, "out": "/n"})
    assert s2.writes == ("/n",) and s2.tier == "R1"


def test_every_form_option_exists_in_the_cli() -> None:
    """The form table stays honest: each option appears in ``agentprov <words> --help`` of this checkout."""
    from agentprov_gui.about import default_checkout
    from agentprov_gui.jobs.commands import form_options
    from agentprov_gui.jobs.manager import cli_options

    cli = CliLocator.for_checkout(default_checkout())
    if not cli.available:
        pytest.skip("no checkout CLI")
    for form in FORMS.values():
        if form.tool is not None:
            import subprocess

            assert cli.checkout is not None
            help_text = subprocess.run([sys.executable, str(cli.checkout / form.tool), "--help"], capture_output=True,
                                       text=True, check=False).stdout
            assert all(o in help_text for o in form_options(form)), form.name
            continue
        known = cli_options(cli, form.words)
        assert known, form.name
        pending = {f.option for f in form.fields if f.pending}  # e.g. D-656's --max-tokens, until its CLI lands
        missing = [o for o in form_options(form) if o not in known and o not in pending]
        assert not missing, (form.name, missing)


# ----------------------------------------------------------------------------------------------- spawn and re-attach
def test_spawn_is_detached_and_files_are_written(tmp_path: Path) -> None:
    m = manager(tmp_path / "home")
    job = m.spawn(spec("--units", "3", "--sleep", "0.3"))
    rec = read_json(job.file("job.json"))
    assert rec is not None and rec["pid"] == job.pid and rec["pid_create_time"]
    assert "--progress-file" in rec["argv"] and "--no-colour" in rec["argv"]
    assert set(rec["env_names"]) <= {"PATH", "HOME", "LANG", "TZ", "AGENTPROV_HOME", "TMPDIR", "AGENTPROV_UPSTREAM_CACHE",
                                     "AGENTPROV_BASELINE_CORPUS", "AGENTPROV_JOB_ID", "AGENTPROV_NO_KEYCHAIN"}
    if os.name == "posix":
        assert os.getsid(job.pid) == rec["supervisor_pid"]  # D-704: its supervisor's own session
        assert (job.directory.stat().st_mode & 0o777) == 0o700
    wait_end(m, job.job_id)
    assert m.jobs[job.job_id].exit_code == 0 and m.jobs[job.job_id].outcome == "ok"
    assert read_json(job.file("ended.json"))["how"] == "waited"


def test_environment_never_carries_keys(tmp_path: Path) -> None:
    m = JobManager(tmp_path / "home", CliLocator(None, (sys.executable, str(FAKE))),
                   environ={"PATH": "/bin", "OPENAI_API_KEY": "k" * 12, "UV_INDEX_URL": "x", "HOME": "/h"})
    env = m.child_env()
    assert "OPENAI_API_KEY" not in env and "UV_INDEX_URL" not in env and env["PATH"] == "/bin"


@posix_only
def test_reattach_after_the_gui_is_gone(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first = manager(home)
    job = first.spawn(spec("--units", "40", "--sleep", "0.05"))
    del first  # the GUI "dies"; the child keeps running in its own session
    second = manager(home)
    jobs = second.load_all()
    assert [j.job_id for j in jobs] == [job.job_id] and jobs[0].state == "running"
    end = time.monotonic() + 30
    while second.refresh()[0].state == "running" and time.monotonic() < end:
        time.sleep(0.1)
    j = second.jobs[job.job_id]
    assert j.state == "ended" and j.exit_code == 0 and j.ended_how == "waited"  # D-704: the supervisor waited


def test_pid_reuse_is_not_mistaken_for_the_job(tmp_path: Path) -> None:
    home = tmp_path / "home"
    d = home / "jobs" / "019a0000-0000-7000-8000-000000000000"
    d.mkdir(parents=True)
    me = psutil.Process()
    atomic_write_json(d / "job.json", {"format": "agentprov-job-record/0.1", "job_id": d.name, "pid": me.pid,
                                       "pid_create_time": me.create_time() - 1000.0, "supervisor_pid": me.pid,
                                       "supervisor_create_time": me.create_time() - 1000.0, "argv": [],
                                       "command": "import", "writes": []})
    jobs = manager(home).load_all()
    assert jobs[0].state == "unobserved"  # same pid, different create time: not our job


def test_stale_lock_is_reported(tmp_path: Path) -> None:
    home = tmp_path / "home"
    corpus = tmp_path / "corpora" / "c"
    (corpus.with_name("c.partial")).mkdir(parents=True)
    d = home / "jobs" / "019a0000-0000-7000-8000-000000000001"
    d.mkdir(parents=True)
    atomic_write_json(d / "job.json", {"format": "agentprov-job-record/0.1", "job_id": d.name, "pid": 999_999,
                                       "pid_create_time": 1.0, "argv": [], "command": "import", "writes": [str(corpus)]})
    (corpus.with_name("c.partial") / ".agentprov.lock").write_text(json.dumps(
        {"pid": 999_999, "host": platform.node(), "command": "import", "started": "2026-10-15T10:00:05Z"}))
    job = manager(home).load_all()[0]
    assert job.state == "unobserved" and job.stale_lock == str(corpus)
    assert (corpus.with_name("c.partial") / ".agentprov.lock").exists()  # never removed by the GUI


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


@pytest.mark.parametrize(("lock_host", "lock_alive", "started", "reported"), [
    ("this", False, "2026-10-15T10:00:05Z", True),   # queued or uv-run job: the CLI's pid is not the job's
    ("this", False, "2026-10-15T10:00:00Z", True),   # the same second as the record
    ("this", True, "2026-10-15T10:00:05Z", False),   # a live writer is not stale
    ("this", False, "2026-10-15T09:59:59Z", False),  # older than the job: not this job's lock
    ("other", False, "2026-10-15T10:00:05Z", False),  # another host cannot be checked
    ("this", False, "not a time", False),
])
def test_stale_lock_of_a_child_cli_is_reported(tmp_path: Path, lock_host: str, lock_alive: bool, started: str,
                                               reported: bool) -> None:
    home = tmp_path / "home"
    corpus = tmp_path / "corpora" / "c"
    (corpus.with_name("c.partial")).mkdir(parents=True)
    d = home / "jobs" / "019a0000-0000-7000-8000-000000000002"
    d.mkdir(parents=True)
    atomic_write_json(d / "job.json", {"format": "agentprov-job-record/0.1", "job_id": d.name, "pid": _dead_pid(),
                                       "pid_create_time": 1.0, "created": "2026-10-15T10:00:00Z", "argv": [],
                                       "command": "import", "writes": [str(corpus)]})
    host = platform.node() if lock_host == "this" else platform.node() + "-elsewhere"
    lock = corpus.with_name("c.partial") / ".agentprov.lock"
    lock.write_text(json.dumps({"pid": os.getpid() if lock_alive else _dead_pid(), "host": host,
                                "command": "import", "started": started}))
    job = manager(home).load_all()[0]
    assert job.state == "unobserved" and job.stale_lock == (str(corpus) if reported else None)
    assert lock.exists()  # never removed by the GUI


@pytest.mark.parametrize(("job_pid", "lock_pid"), [
    ("dead", -1), ("dead", 0), ("dead", 2**31), ("dead", 2**70), (-1, -1), (0, 0), (2**70, 2**70), (-1, "dead"),
])
def test_impossible_pids_are_unknown_and_never_raise(tmp_path: Path, job_pid: object, lock_pid: object) -> None:
    """GR-41: a pid no process can have (in job.json or a lock) is not this job's and never aborts a load."""
    home = tmp_path / "home"
    corpus = tmp_path / "corpora" / "c"
    (corpus.with_name("c.partial")).mkdir(parents=True)
    d = home / "jobs" / "019a0000-0000-7000-8000-000000000003"
    d.mkdir(parents=True)
    atomic_write_json(d / "job.json", {"format": "agentprov-job-record/0.1", "job_id": d.name,
                                       "pid": _dead_pid() if job_pid == "dead" else job_pid, "pid_create_time": 1.0,
                                       "created": "2026-10-15T10:00:00Z", "argv": [], "command": "import",
                                       "writes": [str(corpus)]})
    lock = corpus.with_name("c.partial") / ".agentprov.lock"
    lock.write_text(json.dumps({"pid": _dead_pid() if lock_pid == "dead" else lock_pid, "host": platform.node(),
                                "command": "import", "started": "2026-10-15T10:00:05Z"}))
    m = manager(home)
    job = m.load_all()[0]
    impossible = lock_pid != "dead"
    assert job.state == "unobserved" and job.stale_lock == (None if impossible else str(corpus))
    assert lock.exists()  # D-704: the GUI reads; it writes no ended.json
    assert m.refresh()[0].state == "unobserved"
    assert not m.stop(job) and not m.kill(job)  # no identity: nothing is signalled


@posix_only
def test_stop_sends_one_sigterm_and_the_cli_ends_interrupted(tmp_path: Path) -> None:
    m = manager(tmp_path / "home")
    job = m.spawn(spec("--units", "200", "--sleep", "0.05"))
    time.sleep(0.5)
    assert m.stop(job)
    wait_end(m, job.job_id)
    assert m.jobs[job.job_id].exit_code == 130 and m.jobs[job.job_id].outcome == "interrupted"


@posix_only
def test_kill_needs_the_identity(tmp_path: Path) -> None:
    """The identity check is the CLI's (``agentprov jobs kill``): a supervisor whose recorded create time no longer
    matches is not this job's, so nothing is signalled."""
    m = manager(tmp_path / "home")
    job = m.spawn(spec("--units", "200", "--sleep", "0.05"))
    record = read_json(job.file("job.json"))
    assert record is not None
    good = record["supervisor_create_time"]
    atomic_write_json(job.file("job.json"), {**record, "supervisor_create_time": 1.0})
    assert not m.kill(job) and not m.stop(job)
    atomic_write_json(job.file("job.json"), {**record, "supervisor_create_time": good})
    assert m.kill(job)
    wait_end(m, job.job_id)
    assert m.jobs[job.job_id].outcome == "killed"


def test_single_writer_and_slots(tmp_path: Path) -> None:
    m = manager(tmp_path / "home")
    target = str(tmp_path / "corpora" / "c")
    a = m.spawn(spec("--units", "100", "--sleep", "0.05", writes=(target,)))
    with pytest.raises(SpawnRefused) as busy:
        m.spawn(spec(writes=(target + ".partial",)))
    assert busy.value.code == "jobs.writer.busy"
    n = m.spawn(spec("--units", "100", "--sleep", "0.05", slot="network"))
    with pytest.raises(SpawnRefused) as slot:
        m.spawn(spec(slot="network"))
    assert slot.value.code == "jobs.slot.busy"
    for j in (a, n):
        m.kill(j) if os.name == "posix" else None
    lock_dir = tmp_path / "corpora" / "d"
    (lock_dir.with_name("d.partial")).mkdir(parents=True)
    (lock_dir.with_name("d.partial") / ".agentprov.lock").write_text("{}")
    with pytest.raises(SpawnRefused) as locked:
        m.spawn(spec(writes=(str(lock_dir),)))
    assert locked.value.code == "jobs.writer.locked"


def test_no_cli_refuses(tmp_path: Path) -> None:
    with pytest.raises(SpawnRefused):
        JobManager(tmp_path, CliLocator(None, ())).spawn(spec())


# ----------------------------------------------------------------------------------------------- followers
def test_tail_reader_partial_lines_long_lines_and_rotation(tmp_path: Path) -> None:
    path = tmp_path / "p.jsonl"
    path.write_bytes(b'{"a":1}\n{"a":')
    r = TailReader(path, line_cap=100)
    assert r.read() == [{"a": 1}]
    with open(path, "ab") as fh:
        fh.write(b'2}\n' + b'{"x":"' + b"y" * 200 + b'"}\n' + b"not json\n")
    assert r.read() == [{"a": 2}] and r.skipped_long == 1 and r.skipped_bad == 1
    path.rename(tmp_path / "p.jsonl.1")
    path.write_bytes(b'{"b":1}\n')
    assert r.read() == [{"b": 1}] and r.rotations == 1


def test_tail_reader_reads_at_most_the_cap(tmp_path: Path) -> None:
    path = tmp_path / "big.jsonl"
    path.write_bytes(b'{"n":1}\n' * 50_000)
    r = TailReader(path, read_cap=64 * 1024)
    first = r.read()
    assert 0 < len(first) < 50_000 and r.lagging_bytes > 0
    total = len(first)
    while (more := r.read()):
        total += len(more)
    assert total == 50_000


def test_progress_fold_and_end(tmp_path: Path) -> None:
    st = ProgressState()
    st.apply({"v": "agentprov-progress/0.1", "event": "start", "total": 4})
    for i in range(3):
        st.apply({"event": "unit_start", "unit": f"u{i}"})
        st.apply({"event": "unit_done", "status": "sealed", "codes": ["c.a"]})
    st.apply({"event": "mystery", "x": 1})  # unknown events are ignored
    assert st.done == 3 and st.total == 4 and st.fraction == 0.75 and st.codes["c.a"] == 3
    st.apply({"event": "heartbeat", "counts": {"sealed": 10, "failed": 1}, "issues_top": {"x": 2},
              "stages": {"map": {"done": 11, "total": 20}}, "workers": {"busy": 3, "configured": 4}})
    assert st.done == 11 and st.stages["map"]["total"] == 20 and st.workers["busy"] == 3
    st.apply({"event": "end", "exit_code": 0, "units_done": 12, "counts": {"sealed": 12}, "issues": {}})
    assert st.ended and st.exit_code == 0 and st.done == 12


def test_rates_and_eta() -> None:
    r = Rates()
    r.update(0, 0)
    for t in range(1, 121):
        r.update(float(t), t * 2)
    assert r.short() is not None and abs(r.short() - 2.0) < 0.2
    eta = r.eta(120.0, 240, 480)
    assert eta is not None and 100 < eta[0] <= eta[1] < 140
    assert "ETA after" in eta_text(None) and "≈" in eta_text(eta)
    assert Rates().eta(10.0, 5, 100) is None


def test_log_ring_evicts_and_counts() -> None:
    ring = LogRing(10_000)
    ring.extend([LogRecord.plain(str(i)) for i in range(10_500)])
    assert len(ring) == 10_000 and ring.evicted == 500
    rec = LogRecord.from_json({"ts": "t", "level": "INFO", "logger": "l", "msg": "m", "ex": "ex_1", "x": 3})
    assert rec.ex == "ex_1" and rec.code is None


# ----------------------------------------------------------------------------------------------- batches
def _until_batch_ends(home: Path, batch_id: str, timeout: float = 60) -> Batch:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        batch = next(b for b in Batch.load_all(home) if b.batch_id == batch_id)
        if batch.finished:
            return batch
        time.sleep(0.1)
    raise AssertionError("the batch did not finish")


def test_batch_runs_as_its_own_job_in_order(tmp_path: Path) -> None:
    """D-704: ``batch create --stdin`` then ``batch start``; the driver job advances it without the GUI."""
    home = tmp_path / "home"
    m = manager(home)
    bid = batch_client.create(m, "round", [spec("--units", "1"), spec("--units", "1")])
    driver = batch_client.start(m, bid, confirm_r2=False)
    batch = _until_batch_ends(home, bid)
    assert [s.state for s in batch.steps] == ["done", "done"] and batch.driver_job_id == driver
    assert {j.job_id for j in m.refresh()} >= {driver, *(s.job_id for s in batch.steps if s.job_id)}


def test_batch_blocks_after_exit_4(tmp_path: Path) -> None:
    home = tmp_path / "home"
    m = manager(home)
    bid = batch_client.create(m, "b", [spec("--units", "0", "--exit", "4"), spec()])
    batch_client.start(m, bid, confirm_r2=False)
    assert [s.state for s in _until_batch_ends(home, bid).steps] == ["failed", "blocked"]
