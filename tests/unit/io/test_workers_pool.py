"""Pool behaviour with real ``python -I -B -m agentprov.worker`` processes (G.4.2, G.4.7, G.4.8; K RPR-6, RPR-8)."""

from __future__ import annotations

import hashlib
import random

import agentprov.io.workers as w

import pytest

from agentprov.io.workers import (
    Job,
    WorkerCrashError,
    WorkerJobError,
    WorkerLimits,
    WorkerPool,
    result_fingerprint,
)


def pool(**kwargs):
    kwargs.setdefault("test_kinds", True)
    return WorkerPool(**kwargs)


def echo_jobs(n: int = 12) -> list[Job]:
    jobs = []
    for i in range(n):
        key = f"job-{i:03d}"
        members = [{"label": f"m{j}", "text": f"{key}-{j}" * (j + 1)} for j in range(i % 3)]
        jobs.append(Job(key, "echo" if i % 2 else "sha256", params={"text": key, "members": members, "n": i}))
    return jobs


def test_protocol_round_trip_with_members():
    r = pool().run_one(
        Job("a", "echo", params={"x": [1, 2.5, "é"], "members": [{"label": "m", "text": "héllo"}]})
    )
    assert r.ok, r.error
    assert r.json == (
        {"echo": {"members": [{"label": "m", "text": "héllo"}], "x": [1, 2.5, "é"]}, "inputs": 0},
    )
    assert r.members[0].read_bytes() == "héllo".encode() and r.members[0].header["label"] == "m"
    assert r.counters == {"inputs": 0} and r.isolation == "worker" and r.worker_pid
    r.close()


def test_worker_result_equals_in_process_result():
    jobs = echo_jobs(6)
    in_proc = WorkerPool(in_process=True).run(jobs)
    worker = pool().run(jobs)
    assert result_fingerprint(in_proc) == result_fingerprint(worker)


def test_results_identical_for_worker_counts_1_2_4_and_any_submission_order():
    """G.4.8: byte-identical results regardless of worker count and ordering."""
    jobs = echo_jobs(12)
    shuffled = random.Random(7).sample(jobs, len(jobs))
    prints = []
    for count, batch in ((1, jobs), (2, shuffled), (4, list(reversed(jobs)))):
        results = pool(workers=count).run(batch)
        assert [r.key for r in results] == sorted(j.key for j in jobs)
        assert all(r.ok for r in results)
        prints.append(result_fingerprint(results))
    assert len(set(prints)) == 1


def test_results_identical_with_recycling_after_every_job_and_after_64():
    """RPR-8: worker recycling after every job versus after 64."""
    jobs = echo_jobs(8)
    a = result_fingerprint(pool(workers=2, jobs_per_worker=1).run(jobs))
    b = result_fingerprint(pool(workers=2, jobs_per_worker=64).run(jobs))
    assert a == b


def test_failed_jobs_do_not_change_other_results():
    jobs = echo_jobs(6)
    bad = Job("job-002b", "test.raise_error")
    with_bad = [r for r in pool(workers=2).run([*jobs, bad]) if r.key != bad.key]
    assert result_fingerprint(with_bad) == result_fingerprint(pool(workers=2).run(jobs))


def test_worker_is_reused_then_recycled_after_jobs_per_worker():
    results = pool(workers=1, jobs_per_worker=2).run([Job(f"j{i}", "test.info") for i in range(5)])
    pids = [r.worker_pid for r in results]
    assert pids[0] == pids[1] and pids[2] == pids[3] and pids[0] != pids[2] != pids[4]


def test_worker_is_replaced_after_a_failed_job():
    jobs = [Job("a", "test.info"), Job("b", "test.raise_error"), Job("c", "test.info")]
    a, b, c = pool(workers=1).run(jobs)
    assert a.ok and not b.ok and c.ok
    assert (
        len({a.worker_pid, b.worker_pid, c.worker_pid}) == 2 and a.worker_pid == b.worker_pid != c.worker_pid
    )


def test_job_exception_is_a_typed_failed_result():
    r = pool().run_one(Job("a", "test.raise_error", params={"message": "boom"}))
    assert isinstance(r.error, WorkerJobError) and r.error.code == "worker.job.error"
    assert "RuntimeError" in str(r.error) and "boom" in str(r.error)
    assert r.error.exit_code == 1


def test_worker_exit_without_a_frame_is_a_crash():
    r = pool().run_one(Job("a", "test.crash", params={"code": 3}))
    assert isinstance(r.error, WorkerCrashError) and "3" in str(r.error)
    assert r.error.code == "worker.crash"


def test_stray_stdout_cannot_corrupt_frames_and_stderr_is_kept():
    r = pool().run_one(Job("a", "test.chatter"))
    assert r.ok and r.json == ({"ok": True},)
    assert b"stray stdout line" in r.stderr_tail and b"stderr-marker" in r.stderr_tail  # fd 1 was redirected


def test_memory_error_in_a_job_maps_to_rss_limit_code():
    r = pool().run_one(Job("a", "test.memory_error"))
    assert r.error.code == "worker.limit.rss"  # type: ignore[union-attr]


def test_inputs_are_read_by_digest_inside_the_worker(tmp_path):
    data = b"stored bytes"
    sha = hashlib.sha256(data).hexdigest()
    (tmp_path / sha[:2]).mkdir()
    (tmp_path / sha[:2] / f"{sha}.bin").write_bytes(data)
    r = pool(store_root=tmp_path).run_one(Job("a", "sha256", inputs=({"sha256": sha, "role": "primary"},)))
    assert r.ok and r.json[0] == {"index": 0, "sha256": sha, "size": len(data), "source": "input"}
    (tmp_path / sha[:2] / f"{sha}.bin").write_bytes(b"tampered")
    r = pool(store_root=tmp_path).run_one(Job("b", "sha256", inputs=({"sha256": sha, "role": "primary"},)))
    assert r.error.code == "worker.input.digest_mismatch"  # type: ignore[union-attr]


def test_per_job_limits_override_pool_limits():
    tight = WorkerLimits(max_frame_bytes=128)
    r = pool().run_one(Job("a", "echo", params={"pad": "x" * 400}, limits=tight))
    assert r.error.code == "worker.limit.output"  # type: ignore[union-attr]


def test_job_directories_are_removed(tmp_path):
    pool(workers=2, work_dir=tmp_path).run(echo_jobs(4))
    assert list(tmp_path.iterdir()) == []


def test_empty_batch():
    assert pool().run([]) == []


@pytest.mark.slow
def test_many_small_jobs_across_workers_and_recycling():
    jobs = [Job(f"k{i:04d}", "sha256", params={"text": str(i)}) for i in range(200)]
    results = pool(workers=4, jobs_per_worker=16).run(jobs)
    assert all(r.ok for r in results)
    assert [r.json[0]["sha256"] for r in results] == [
        hashlib.sha256(str(i).encode()).hexdigest() for i in range(200)
    ]


def test_a_successful_job_keeps_stderr_the_drain_thread_reads_late(monkeypatch):
    """The stderr tail of a result is snapshotted when its DONE frame arrives; stderr is a separate pipe drained by its
    own thread, which may lag (seen at -n 10 under heavy load). The worker's last result gets the complete tail when the
    worker is retired (D-414 branch, pool fix)."""
    import time

    real = w._Tail.add

    def late(self, chunk):  # type: ignore[no-untyped-def]
        time.sleep(0.5)  # the drain thread records each chunk only after the job's DONE has been collected
        real(self, chunk)

    monkeypatch.setattr(w._Tail, "add", late)
    r = pool().run_one(Job("a", "test.chatter"))
    assert r.ok and b"stray stdout line" in r.stderr_tail and b"stderr-marker" in r.stderr_tail


def _big_echo(nbytes: int) -> Job:
    return Job("big", "echo", params={"rows": [{"label": f"m{i}", "pad": "x" * 300} for i in range(nbytes // 320)]})


def test_a_request_over_the_old_4_mib_line_runs_in_a_worker_as_in_process() -> None:
    """Pre-round review D #11: a container-mode map request of about 15,000 member rows (over 4 MiB) failed in a worker
    as worker.protocol ("DONE/FAIL frame does not match the running job") and passed in process."""
    job = _big_echo(5 << 20)
    worker_results = WorkerPool(workers=1, test_kinds=True).run([job])
    local_results = WorkerPool(workers=1, test_kinds=True, in_process=True).run([job])
    try:
        assert worker_results[0].error is None, worker_results[0].error
        assert local_results[0].error is None
        assert result_fingerprint(worker_results) == result_fingerprint(local_results)
    finally:
        for r in (*worker_results, *local_results):
            r.close()


def test_a_request_over_the_limit_is_refused_alike_in_both_modes_and_never_sent(monkeypatch) -> None:
    from agentprov.io import workers as workers_module

    monkeypatch.setattr(workers_module, "MAX_REQUEST_BYTES", 1 << 20)
    job = _big_echo(2 << 20)
    for in_process in (False, True):
        results = WorkerPool(workers=1, test_kinds=True, in_process=in_process).run([job, Job("small", "echo", params={})])
        try:
            by_key = {r.key: r for r in results}
            assert by_key["big"].error is not None and by_key["big"].error.code == "worker.request.too_large"
            assert by_key["small"].error is None  # the worker was not disturbed
        finally:
            for r in results:
                r.close()
