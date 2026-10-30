"""SEC-22 / K.12.10: T1 worker isolation (docs/architecture G.4; A3).

Runs on Linux, macOS and Windows, on x86_64 and arm64. Behaviour that depends on the host is selected by the probed
capabilities of ``agentprov.host`` (``skipif`` on capabilities, never on the operating-system name): a host without
a hard memory cap is bounded by the parent's RSS watchdog; one that enforces ``RLIMIT_AS`` or has a Job Object also
has a kernel-level cap.
"""

from __future__ import annotations

import os
import re
import time

import pytest

from agentprov.host import AS_STARTUP_HEADROOM, constants_for, detect_host
from agentprov.io.workers import (
    ENV_ALLOWLIST,
    ENV_ALLOWLIST_LOADER,
    MIB,
    PROTOCOL,
    Job,
    WorkerLimits,
    WorkerPool,
)

SCRUB = re.compile(r"(?i)(api_key|token|secret|base_url|openrouter|anthropic|openai|gemini|hf_)")
SENTINEL = "sentinel-secret-value-7c1f"
HOST = detect_host()
CAPS = HOST.caps
# The OS may add variables to every exec'd process; they are not inherited from the parent.
SYSTEM_ADDED = {"__CF_USER_TEXT_ENCODING"}
LOADER_VARS = ENV_ALLOWLIST_LOADER if "SYSTEMROOT" in os.environ else frozenset()

needs_memory_control = pytest.mark.skipif(
    not CAPS.rss_sampler and not CAPS.hard_memory_cap,
    reason="neither an RSS sampler nor a hard memory cap on this host",
)
needs_posix_permissions = pytest.mark.skipif(
    not CAPS.posix_permissions, reason="chmod bits do not read back on this host (access is governed by ACLs)"
)
needs_cpu_limit = pytest.mark.skipif(not CAPS.cpu_limit, reason="no RLIMIT_CPU on this host")
needs_fsize_limit = pytest.mark.skipif(
    "fsize" not in CAPS.rlimits.value, reason="no RLIMIT_FSIZE on this host"
)
needs_tree_session = pytest.mark.skipif(not hasattr(os, "killpg"), reason="no process groups on this host")
needs_fork = pytest.mark.skipif(not hasattr(os, "fork"), reason="no os.fork on this host")


def pool(**kwargs) -> WorkerPool:
    kwargs.setdefault("test_kinds", True)
    return WorkerPool(**kwargs)


def run(kind: str, limits: WorkerLimits | None = None, **params):
    return pool(limits=limits).run_one(Job("a", kind, params=params))


def process_group_alive(pgid: int | None) -> bool:
    """Whether the worker's process group still exists (only checkable where process groups exist)."""
    if pgid is None or not hasattr(os, "killpg"):
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@pytest.fixture
def info() -> dict:
    result = run("test.info")
    assert result.ok, result.error
    return result.json[0]


# ---- spawn, environment, directory (G.4.2) ----------------------------------------------------------------------


def test_worker_runs_isolated_without_bytecode_in_its_own_session(info):
    assert info["isolated"] == 1 and info["dont_write_bytecode"] == 1
    argv = info["orig_argv"]
    assert argv[1:4] == ["-I", "-B", "-m"] and argv[4] == "agentprov.worker"
    assert argv[argv.index("--protocol") + 1] == PROTOCOL
    assert info["pid"] != os.getpid()


@needs_tree_session
def test_worker_leads_its_own_session_so_killpg_reaches_the_group(info):
    assert info["pgid"] == info["pid"] == info["sid"]


def test_environment_is_scrubbed(info, monkeypatch):
    leaked = {
        "OPENAI_API_KEY": SENTINEL,
        "ANTHROPIC_API_KEY": SENTINEL,
        "GITHUB_TOKEN": SENTINEL,
        "ZENODO_TOKEN": SENTINEL,
        "HF_TOKEN": SENTINEL,
        "UV_CACHE_DIR": "/nonexistent",
        "UV_PROJECT_ENVIRONMENT": "/nonexistent",
        "AGENTPROV_HOME": "/nonexistent",
        "PYTHONPATH": "/nonexistent",
        "PYTHONHASHSEED": "0",
        "SSH_AUTH_SOCK": "/nonexistent",
    }
    for name, value in leaked.items():
        monkeypatch.setenv(name, value)
    env = run("test.info").json[0]["env"]
    assert set(env) <= ENV_ALLOWLIST | LOADER_VARS | SYSTEM_ADDED
    assert ENV_ALLOWLIST <= set(env)
    assert not [n for n in env if SCRUB.search(n) or n.startswith(("UV_", "PYTHON", "AGENTPROV"))]
    assert SENTINEL not in env.values() and not any("/nonexistent" in v for v in env.values())
    assert env["TZ"] == "UTC" and env["LC_ALL"] == "C.UTF-8"


def test_home_and_tmpdir_are_the_private_empty_job_directory(info):
    assert info["env"]["HOME"] == info["env"]["TMPDIR"]
    assert os.path.realpath(info["env"]["HOME"]) == os.path.realpath(info["cwd"])
    assert info["env"]["HOME"] != os.path.expanduser("~")
    assert info["home_listing"] == []


@needs_posix_permissions
def test_the_job_directory_is_private_where_chmod_bits_exist(info):
    assert info["cwd_mode"] == 0o700


def test_no_forbidden_module_is_loaded_in_a_worker(info):
    assert info["forbidden_loaded"] == []


def test_job_directories_are_removed_after_the_run(tmp_path):
    pool(work_dir=tmp_path).run([Job("a", "test.info"), Job("b", "test.raise_error")])
    assert list(tmp_path.iterdir()) == []


# ---- kernel limits (G.4.3) --------------------------------------------------------------------------------------


def test_rlimits_are_applied_before_any_job(info):
    """Every rlimit that exists on the host is applied; ``RLIMIT_AS`` only where the probe showed it is enforced."""
    r = info["rlimits"]
    assert sorted(r) == sorted(CAPS.rlimits.value)
    if "core" in r:
        assert r["core"] == [0, 0]
    if "fsize" in r:
        assert r["fsize"] == [0, 0]
    if "nofile" in r:
        assert r["nofile"] == [64, 64]
    if "cpu" in r:
        soft, hard = r["cpu"]
        assert 300 < soft <= 300 + 5 and hard == 540 * 64 + 60  # soft = CPU used so far + the 300 s budget
    if CAPS.hard_memory_cap.value == "rlimit_as":
        assert r["as"] == [4 << 30, 4 << 30]
    elif "as" in r:
        assert r["as"][0] != 4 << 30  # not applied where the kernel does not enforce it


@needs_fsize_limit
def test_file_writes_fail_with_efbig_while_the_pipe_still_works():
    r = run("test.write")  # obs-G5: no kill, EFBIG, frames still flow
    assert r.ok and r.json[0]["errno"] == r.json[0]["efbig"]


@needs_cpu_limit
@pytest.mark.slow
def test_cpu_loop_is_killed_by_sigxcpu():
    limits = WorkerLimits(cpu_s=1, cpu_s_max=3, wall_s=30)
    r = pool(limits=limits).run_one(Job("a", "test.spin"))
    assert r.error is not None and r.error.code == "worker.limit.cpu"
    assert r.elapsed_s < 15 and not process_group_alive(r.worker_pid)


@needs_cpu_limit
def test_cpu_budget_is_rearmed_per_job_not_cumulative():
    limits = WorkerLimits(cpu_s=2, cpu_s_max=6, wall_s=30)
    jobs = [Job(f"j{i}", "test.spin", params={"seconds": 0.6}) for i in range(4)]  # 2.4 s CPU in one worker
    results = pool(workers=1, limits=limits).run(jobs)
    assert all(r.ok for r in results) and len({r.worker_pid for r in results}) == 1


# ---- parent-enforced limits (G.4.3, G.4.11) ----------------------------------------------------------------------


@needs_memory_control
@pytest.mark.slow
def test_memory_hog_is_killed_before_it_holds_its_allocation():
    limits = WorkerLimits(rss_bytes=150 * MIB, wall_s=60, as_bytes=1 << 30)
    p = pool(limits=limits)
    started = time.monotonic()
    r = p.run_one(Job("a", "test.hog", params={"mb": 2000}))
    assert r.error is not None and r.error.code == "worker.limit.rss"
    assert time.monotonic() - started < 20  # killed while allocating, not after the 30 s hold
    if r.peak_rss_bytes is not None and "watchdog" in str(r.error):  # the sampler decided: the kill came at ``cap - margin``
        assert r.peak_rss_bytes > p.constants.trigger_for(limits.rss_bytes)  # else a kernel-level cap stopped it first
    assert not process_group_alive(r.worker_pid)


@needs_memory_control
@pytest.mark.slow
def test_sec22_a_job_kind_with_a_declared_cap_runs_past_the_default_cap_and_is_still_bounded():
    """D-55: the per-kind cap is what a job is watched against. The same 400 MiB allocation is killed under the 150 MiB
    default and completes when its kind declares 1 GiB; a 1.5 GiB allocation under that 1 GiB kind cap is killed.

    The two hogs that must be killed hold their peak until they are killed (the job's 30 s hold, inside the 60 s wall),
    so a watchdog sample delayed by load still finds them there: with ``hold_s=0`` a hog could finish between two
    samples (observed under load at -n 2 and -n 10, 2026-10-22), and a 1 s hold left the same race to a busier host
    (-n 24 on the Mac Studio). A kill by the wall clock is a different error code, so it still fails the test."""
    small = WorkerLimits(rss_bytes=150 * MIB, wall_s=60, kind_rss_bytes={})
    declared = WorkerLimits(rss_bytes=150 * MIB, wall_s=60, kind_rss_bytes={"test.hog": 1 << 30})
    p = pool(limits=small)
    killed = p.run_one(Job("a", "test.hog", params={"mb": 400}))
    assert killed.error is not None and killed.error.code == "worker.limit.rss"
    fits = pool(limits=declared).run_one(Job("a", "test.hog", params={"mb": 400, "hold_s": 0}))
    assert fits.ok, fits.error
    assert fits.counters == {"held": 50}  # every 8 MiB step was allocated
    if fits.peak_rss_bytes is not None:  # it ran past the default cap, not under it
        assert fits.peak_rss_bytes > 150 * MIB
    p = pool(limits=declared)
    over = p.run_one(Job("a", "test.hog", params={"mb": 1536}))
    assert over.error is not None and over.error.code == "worker.limit.rss"
    if over.peak_rss_bytes is not None and "watchdog" in str(over.error):  # killed at the 1 GiB kind cap's trigger
        assert over.peak_rss_bytes > p.constants.trigger_for(1 << 30)


@pytest.mark.slow
def test_wall_timeout_kills_the_process_group():
    limits = WorkerLimits(wall_s=1.5)
    started = time.monotonic()
    r = pool(limits=limits).run_one(Job("a", "test.sleep", params={"seconds": 60}))
    assert r.error is not None and r.error.code == "worker.limit.wall"
    assert time.monotonic() - started < 15 and not process_group_alive(r.worker_pid)


AS_ENFORCED = pytest.mark.skipif(
    CAPS.hard_memory_cap.value != "rlimit_as", reason="RLIMIT_AS is not enforced on this host"
)


@pytest.mark.slow
@AS_ENFORCED
def test_address_space_limit_where_the_kernel_enforces_it():
    # The limit is derived from the probed start-up footprint of a worker on THIS host (a fixed constant can sit below
    # what the interpreter needs to start, e.g. 1 GiB on arm64 Linux), then exceeded on purpose.
    floor = constants_for(HOST).as_floor_bytes
    as_bytes = floor if floor else 1 << 30
    limits = WorkerLimits(as_bytes=as_bytes, rss_bytes=8 << 30, wall_s=60)
    r = pool(limits=limits).run_one(Job("a", "test.hog", params={"mb": as_bytes // MIB + 1024, "pause": 0}))
    assert r.error is not None and r.error.code == "worker.limit.rss"  # MemoryError, mapped


@pytest.mark.skipif(not constants_for(HOST).as_floor_bytes, reason="no start-up footprint measured on this host")
def test_a_requested_address_space_below_the_startup_footprint_is_raised_to_the_floor():
    c = constants_for(HOST)
    assert c.as_floor_bytes == c.startup_vm_bytes + AS_STARTUP_HEADROOM
    r = pool(limits=WorkerLimits(as_bytes=64 * MIB)).run_one(Job("a", "echo"))
    assert r.ok, r.error  # a 64 MiB cap would have killed the interpreter before it replied


def test_a_limit_event_replaces_the_worker_and_the_next_job_runs():
    limits = WorkerLimits(wall_s=1.0)
    # the follow-up job's wall clock includes the replacement worker's start-up, which can pass 1 s on a loaded host
    results = pool(workers=1, limits=limits).run(
        [Job("a", "test.sleep", params={"seconds": 30}), Job("b", "echo", limits=WorkerLimits(wall_s=60.0))]
    )
    assert results[0].error.code == "worker.limit.wall"  # type: ignore[union-attr]
    assert results[1].ok and results[1].worker_pid != results[0].worker_pid


# ---- output frame caps (G.4.6) -----------------------------------------------------------------------------------


def test_oversize_json_frame_is_rejected_as_output_limit():
    limits = WorkerLimits(max_frame_bytes=4096)
    r = run("test.oversize_json", limits, bytes=64 * 1024)
    assert r.error is not None and r.error.code == "worker.limit.output"
    assert not process_group_alive(r.worker_pid)


def test_declared_frame_length_is_checked_before_allocation():
    r = run("test.bad_frame", mode="huge_length")  # header says 1 TiB; the parent must not try to read it
    assert r.error is not None and r.error.code == "worker.limit.output"


def test_json_output_over_the_per_job_cap_is_rejected():
    limits = WorkerLimits(max_frame_bytes=4096, max_json_job_bytes=20000)
    r = run("test.oversize_total", limits, frames=50, bytes=1000)
    assert r.error is not None and r.error.code == "worker.limit.output"


def test_data_bytes_beyond_the_declared_member_size_are_rejected():
    r = run("test.data_overflow", size=4, sent=10)
    assert r.error is not None and r.error.code == "worker.protocol"


def test_member_over_max_member_bytes_and_job_total_are_rejected():
    limits = WorkerLimits(max_member_bytes=16, max_total_bytes=64)
    r = run("echo", limits, members=[{"label": "m", "text": "x" * 17}])
    assert r.error.code == "worker.limit.output"  # type: ignore[union-attr]
    r = run("echo", limits, members=[{"label": f"m{i}", "text": "x" * 16} for i in range(5)])
    assert r.error.code == "worker.limit.output"  # type: ignore[union-attr]
    assert run("echo", limits, members=[{"label": "m", "text": "x" * 16}]).ok


@pytest.mark.parametrize(
    "mode", ["unknown_tag", "data_no_member", "bad_json", "dup_keys", "nan", "not_object", "wrong_job"]
)
def test_protocol_violations_are_fatal_for_the_worker(mode):
    r = run("test.bad_frame", mode=mode)
    assert r.error is not None and r.error.code == "worker.protocol"
    assert not process_group_alive(r.worker_pid)


def test_truncated_frame_is_a_crash():
    r = run("test.bad_frame", mode="truncated")
    assert r.error is not None and r.error.code == "worker.crash"


# ---- audit hook (G.4.4; defence in depth) ---------------------------------------------------------------------------


@pytest.mark.parametrize("event", ["connect", "bind", "getaddrinfo", "sendto"])
def test_audit_hook_blocks_network_events_in_the_worker(event):
    r = run("test.net", event=event)
    assert r.error is not None and r.error.code == "worker.audit.blocked", r.error
    assert "AuditBlockedError" in str(r.error)


@pytest.mark.parametrize("event", ["popen", "system", pytest.param("fork", marks=needs_fork), "exec",
                                   pytest.param("fork_exec", marks=needs_fork), pytest.param("fork_exec_bound", marks=needs_fork),
                                   pytest.param("fork_exec_reimport", marks=needs_fork)])
def test_audit_hook_blocks_subprocess_events_in_the_worker(event):
    r = run("test.spawn", event=event)
    assert r.error is not None and r.error.code == "worker.audit.blocked", r.error


def test_audit_hook_is_not_installed_in_the_parent_process():
    """``--in-process`` shares the CLI process: the hook must exist only inside real workers."""
    r = WorkerPool(in_process=True, test_kinds=True).run_one(Job("a", "test.net", params={"event": "bind"}))
    assert r.ok  # a loopback bind succeeds in the parent


def test_worker_survives_a_blocked_event_only_as_a_failed_unit():
    a, b = pool(workers=1).run([Job("a", "test.net", params={"event": "connect"}), Job("b", "echo")])
    assert not a.ok and b.ok and a.worker_pid != b.worker_pid


# ---- R-40: member DATA is not counted against the JSON cap (SEC-07 "more than 256 MiB of selected members") ----------
def _frames(members: list[int], *, extra_json: bytes = b"") -> bytes:
    import io as _io
    import json as _json

    from agentprov.io.workers import TAG_DATA, TAG_DONE, TAG_JSON, FrameWriter

    out = _io.BytesIO()
    writer = FrameWriter(out)
    if extra_json:
        writer.write(TAG_JSON, extra_json)
    for n, size in enumerate(members):
        writer.write(TAG_JSON, _json.dumps({"$member": {"label": f"m{n}", "size": size}}).encode())
        for start in range(0, size, 4096):
            writer.write(TAG_DATA, b"x" * min(4096, size - start))
    writer.write(TAG_DONE, b'{"job": 7, "counters": {}}')
    writer.flush()
    return out.getvalue()


def test_sec07_member_data_beyond_the_json_job_cap_is_accepted_and_the_total_cap_still_holds():
    import io as _io

    from agentprov.io.workers import MemberOutput, WorkerLimitError, _collect

    limits = WorkerLimits(max_json_job_bytes=4096, max_member_bytes=64 * 1024, max_total_bytes=128 * 1024)
    collected = _collect(_io.BytesIO(_frames([64 * 1024, 64 * 1024])), 7, limits)  # 128 KiB of DATA, 32x the JSON cap
    members = [o for o in collected.outputs if isinstance(o, MemberOutput)]
    assert [m.size for m in members] == [64 * 1024, 64 * 1024]
    for m in members:
        m.close()
    with pytest.raises(WorkerLimitError) as total:  # one byte over the per-job DATA total
        _collect(_io.BytesIO(_frames([64 * 1024, 64 * 1024, 1])), 7, limits)
    assert total.value.code == "worker.limit.output"
    with pytest.raises(WorkerLimitError):  # while JSON output is still held to its own cap
        _collect(_io.BytesIO(_frames([], extra_json=b'{"pad": "' + b"y" * 4096 + b'"}')), 7, limits)
