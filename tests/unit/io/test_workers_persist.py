"""D-1068 P1 and P2: workers that live across ``WorkerPool.run`` calls, and what a worker loads before its audit hook.

P1: a worker that may still serve jobs is parked at the end of a batch and the next batch takes it; outputs do not
depend on it (G.4.7, G.4.8), a parked worker refuses what a fresh one refuses (G.4.4), its recycling count and the D-554
memory bound carry over, and ``close`` (or the pool's collection) stops it and removes its job directory.
P2: a worker loads only the semantics profiles its batch names (``--preload-semantics``), and a job is never run on a
worker that lacks one it names.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

import agentprov.io.workers as w
from agentprov.io.workers import FULL_PRELOAD, Job, Preload, WorkerPool, preload_for, result_fingerprint


def process_group_alive(pgid: int | None) -> bool:
    """Whether the worker's process group (POSIX: the worker leads its own session) is alive; on a host without process
    groups (Windows, where a Job Object holds the tree) whether the worker process itself is."""
    if pgid is None:
        return False
    if not hasattr(os, "killpg"):
        from agentprov.io.atomic import pid_alive

        return pid_alive(pgid)  # undecided counts as alive, so a "stopped" assertion never passes on a guess
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pool(**kwargs):  # type: ignore[no-untyped-def]
    kwargs.setdefault("test_kinds", True)
    return WorkerPool(**kwargs)


def echo_jobs(prefix: str, n: int = 6) -> list[Job]:
    return [Job(f"{prefix}-{i:03d}", "echo" if i % 2 else "sha256",
                params={"text": f"{prefix}{i}", "members": [{"label": "m", "text": f"{prefix}-{i}" * (i + 1)}]})
            for i in range(n)]


def _argv(result) -> list[str]:  # type: ignore[no-untyped-def]
    return list(result.json[0]["orig_argv"])


# ------------------------------------------------------------------------------------------------------------ P1
def test_a_worker_serves_the_next_batch_and_close_stops_it(tmp_path):
    p = pool(workers=1, work_dir=tmp_path)
    (a,) = p.run([Job("a", "test.info")])
    (b,) = p.run([Job("b", "test.info")])
    assert a.ok and b.ok and a.worker_pid == b.worker_pid  # one start for two batches
    assert len(list(tmp_path.iterdir())) == 1 and process_group_alive(a.worker_pid)  # parked: its directory stays
    p.close()
    assert list(tmp_path.iterdir()) == [] and not process_group_alive(a.worker_pid)
    (c,) = p.run([Job("c", "test.info")])  # a closed pool still runs; it parks nothing
    assert c.ok and c.worker_pid != a.worker_pid and list(tmp_path.iterdir()) == []


def test_a_pool_that_is_collected_stops_its_parked_workers(tmp_path):
    (r,) = pool(workers=1, work_dir=tmp_path).run([Job("a", "test.info")])
    assert r.ok and list(tmp_path.iterdir()) == [] and not process_group_alive(r.worker_pid)


def test_with_block_closes_the_pool(tmp_path):
    with pool(workers=2, work_dir=tmp_path) as p:
        assert all(r.ok for r in p.run(echo_jobs("x", 4)))
        assert list(tmp_path.iterdir())
    assert list(tmp_path.iterdir()) == []


def test_outputs_do_not_depend_on_parked_workers():
    """G.4.7/G.4.8 and RPR-8: one long-lived pool over three batches gives the bytes of a fresh pool per batch."""
    batches = [echo_jobs(p, 7) for p in ("a", "b", "c")]
    with pool(workers=3) as long_lived:
        kept = [result_fingerprint(long_lived.run(b)) for b in batches]
    fresh = [result_fingerprint(pool(workers=3).run(b)) for b in batches]
    in_process = [result_fingerprint(WorkerPool(in_process=True, test_kinds=True).run(b)) for b in batches]
    assert kept == fresh == in_process


@pytest.mark.parametrize(("kind", "event"), [("test.net", "connect"), ("test.net", "getaddrinfo"),
                                             ("test.spawn", "popen"), ("test.spawn", "system")])
def test_a_parked_worker_refuses_what_a_fresh_one_refuses(kind, event):
    """G.4.4: the audit hook is installed once, before the first job; a worker that served an earlier batch is the
    same process and refuses the same events, with the same code."""
    with pool(workers=1) as p:
        (first,) = p.run([Job("warm", "echo", params={"x": 1})])
        (late,) = p.run([Job("probe", kind, params={"event": event})])
    (fresh,) = pool(workers=1).run([Job("probe", kind, params={"event": event})])
    assert first.ok and late.worker_pid == first.worker_pid  # the long-lived worker ran it
    assert late.error is not None and fresh.error is not None
    assert late.error.code == fresh.error.code == "worker.audit.blocked"


def test_the_recycling_count_carries_across_batches():
    """G.4.7: ``jobs_per_worker`` counts a worker's jobs over its whole life, not per batch."""
    with pool(workers=1, jobs_per_worker=2) as p:
        pids = [p.run([Job(f"j{i}", "test.info")])[0].worker_pid for i in range(4)]
    assert pids[0] == pids[1] != pids[2] == pids[3]


def test_a_worker_over_the_retirement_peak_is_not_parked(monkeypatch):
    """D-554: a worker whose lifetime peak passed ADMISSION_RETIRE_PEAK gives its heap back at the end of the batch
    rather than waiting idle; so idle memory stays at most ``workers`` x the bound."""
    monkeypatch.setattr(w, "ADMISSION_RETIRE_PEAK", 0)
    with pool(workers=1) as p:
        (a,) = p.run([Job("a", "test.info")])
        (b,) = p.run([Job("b", "test.info")])
    assert a.worker_pid != b.worker_pid and not process_group_alive(a.worker_pid)


def test_at_most_workers_are_parked():
    p = pool(workers=2)
    p.run(echo_jobs("a", 8))
    assert 1 <= len(p._idle.workers) <= 2  # noqa: SLF001
    p.close()
    assert p._idle.workers == []  # noqa: SLF001


def test_a_failed_worker_is_never_parked():
    with pool(workers=1) as p:
        (bad,) = p.run([Job("a", "test.raise_error")])
        (good,) = p.run([Job("b", "test.info")])
    assert not bad.ok and good.ok and good.worker_pid != bad.worker_pid


def test_a_parked_workers_last_result_gets_its_complete_stderr_tail():
    with pool(workers=1) as p:
        (r,) = p.run([Job("a", "test.chatter")])
    assert b"stray stdout line" in r.stderr_tail and b"stderr-marker" in r.stderr_tail


# ------------------------------------------------------------------------------------------------------------ P2
def test_preload_for_names_only_grammar_refs_and_the_cache_flag():
    jobs = [Job("a", "prov", params={"semantics": ["agentdojo.suites@1", "x.y@2"]}),
            Job("b", "validate", params={"semantics": ["../evil@1", "a.b@01", "A.b@1", 7], "fidelity": {"hint": False}}),
            Job("c", "map", params={"profile": "p"})]
    assert preload_for(jobs) == Preload(frozenset({"agentdojo.suites@1", "x.y@2"}), True)
    assert preload_for(jobs[2:]) == Preload(frozenset(), False)
    many = [Job(f"k{i}", "prov", params={"semantics": [f"a.b@{i + 1}"]}) for i in range(w.PRELOAD_MAX_REFS + 1)]
    assert preload_for(many) == FULL_PRELOAD


def test_covers():
    small, big = Preload(frozenset({"a.b@1"}), False), Preload(frozenset({"a.b@1", "c.d@2"}), True)
    assert big.covers(small) and not small.covers(big) and FULL_PRELOAD.covers(big)
    assert not big.covers(FULL_PRELOAD) and not small.covers(Preload(frozenset(), True))
    assert big.argv() == ["--preload-semantics", "a.b@1,c.d@2", "--preload-fidelity"] and FULL_PRELOAD.argv() == []


def test_a_job_never_runs_on_a_worker_that_lacks_a_profile_it_names():
    """A worker started for a batch that names no profile is replaced before a job that names one (and the new worker's
    argv names it); a worker that loaded more serves a job that names less."""
    with pool(workers=1) as p:
        (plain,) = p.run([Job("a", "test.info")])
        (named,) = p.run([Job("b", "test.info", params={"semantics": ["agentdojo.suites@1"], "fidelity": {}})])
        (again,) = p.run([Job("c", "test.info")])
    assert _argv(plain)[-2:] == ["--preload-semantics", ""]
    assert named.worker_pid != plain.worker_pid
    assert _argv(named)[-3:] == ["--preload-semantics", "agentdojo.suites@1", "--preload-fidelity"]
    assert again.worker_pid == named.worker_pid


_SHOW = """
import sys
from agentprov.io.workers import Preload, set_worker_preload
set_worker_preload(Preload(frozenset(sys.argv[1:]), False))
from agentprov.adapters.runner import provjob
from agentprov.corpus import validation_job
from agentprov.validate import cache
print(sorted(provjob.PROFILES), sorted(validation_job._PROFILES), cache.context_digest.cache_info().currsize)
"""


def test_a_worker_loads_only_the_named_shipped_profiles():
    """The job modules load what the preload names (a ref that is not shipped is skipped, as it is absent from the
    full mapping) and, without ``fidelity``, do not compute the cache context."""
    done = subprocess.run([sys.executable, "-I", "-c", _SHOW, "agentdojo.suites@1", "nothere.at@9"],
                          capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "['agentdojo.suites@1'] ['agentdojo.suites@1'] 0"


def test_the_named_profiles_are_the_full_mappings_entries():
    from agentprov.adapters.semantics_profiles import load_all_semantics_profiles, load_named_semantics_profiles

    full = load_all_semantics_profiles()
    picked = sorted(full)[::7]
    named = load_named_semantics_profiles([*picked, "not.shipped@1", "agentdojo.suites@01"])
    assert sorted(named) == picked
    assert all((named[r].id, named[r].version, named[r].sha256) == (full[r].id, full[r].version, full[r].sha256)
               for r in picked)
