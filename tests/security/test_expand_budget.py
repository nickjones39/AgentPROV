"""SEC-07 / R-40: an archive with more than 256 MiB of selected members is expanded inside its budgets, streaming.

D-47 items 1 and 3, D-58, D-60. The archive is generated at test time from a fixed seed (stored random members, so the
ratio limit is not involved, and deflated text members), written to the test's temporary directory only. The ``expand``
job runs in a real T1 worker exactly as ``expand_containers`` submits it. Calibration on the same shape and on the
cached survey ``artifact.zip``: ``docs/reports/hardening/expand-calibration.md``.
"""

from __future__ import annotations

import random
import resource
import zipfile
from dataclasses import replace

import pytest

from agentprov.io.workers import MIB, Job, WorkerPool
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.members import JOB_KIND, ContainerSpec, Selection, expand_containers
from agentprov.raw.store import RawObjectStore

SEED = 20261012


def _archive(path, *, stored: int, deflated: int, size: int) -> int:
    rng = random.Random(SEED)
    words = [rng.randbytes(rng.randint(3, 9)).hex().encode() + b" " for _ in range(2048)]
    total = 0
    with zipfile.ZipFile(path, "w") as z:
        for i in range(stored):
            data = rng.randbytes(size)
            z.writestr(zipfile.ZipInfo(f"runs/stored/{i:03d}.bin", (2026, 1, 1, 0, 0, 0)), data, zipfile.ZIP_STORED)
            total += len(data)
        for i in range(deflated):
            data = b"".join(words[rng.randrange(2048)] for _ in range(size // 8))[:size]
            z.writestr(zipfile.ZipInfo(f"runs/deflated/{i:03d}.json", (2026, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
            total += len(data)
    return total


@pytest.mark.slow
def test_sec07_more_than_256_mib_of_selected_members_expand_within_budget_and_without_holding_the_container(tmp_path):
    container = tmp_path / "seeded.zip"
    selected = _archive(container, stored=12, deflated=6, size=16 * MIB)  # 288 MiB selected, ~200 MB stored + text
    assert selected > 256 * MIB
    store = RawObjectStore(tmp_path / "raw")
    with container.open("rb") as fp:
        sha = store.put_stream(fp, ext="zip", max_bytes=1 << 31).sha256
    limits = IngestLimits()
    pool = WorkerPool(workers=1, jobs_per_worker=1, store_root=store.objects_dir)
    job_limits = replace(pool.limits, max_member_bytes=limits.max_member_bytes,
                         max_total_bytes=limits.max_total_bytes).with_expand_scaling(limits.max_total_bytes)
    job = Job("000000001", JOB_KIND, inputs=({"sha256": sha, "role": "container"},),
              params={"limits": limits.to_json(), "include": ["**"], "nested": [], "depth": 1, "release": False},
              limits=job_limits)  # fmt: skip
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    (result,) = pool.run([job])
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        assert result.ok, result.error
        assert len(result.members) == 18 and sum(m.size for m in result.members) == selected
        cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
        assert cpu < job_limits.cpu_s / 10 and result.elapsed_s < job_limits.wall_s / 10  # >= 10x headroom (D-60)
        if result.peak_rss_bytes is not None:  # the container (~200 MB) is never held whole: one member at a time
            assert result.peak_rss_bytes < container.stat().st_size, (result.peak_rss_bytes, container.stat().st_size)
    finally:
        result.close()


@pytest.mark.slow
def test_sec07_the_large_archive_is_stored_member_by_member_through_expand_containers(tmp_path):
    container = tmp_path / "seeded.zip"
    selected = _archive(container, stored=17, deflated=0, size=16 * MIB)  # 272 MiB
    store = RawObjectStore(tmp_path / "raw")
    with container.open("rb") as fp:
        sha = store.put_stream(fp, ext="zip", max_bytes=1 << 31).sha256
    pool = WorkerPool(workers=1, store_root=store.objects_dir)
    out = expand_containers(store, [ContainerSpec(sha, "snap", "seeded.zip", (Selection(include=("**",)),))], pool=pool)
    assert out.events == [] and sum(r.size or 0 for r in out.rows if r.disposition == "selected") == selected
    assert all(store.has(r.sha256) for r in out.rows if r.sha256)
