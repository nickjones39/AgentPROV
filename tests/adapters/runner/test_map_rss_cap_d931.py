"""D-931: ``[import] map_rss_bytes`` raises the memory cap of one source's ``map`` jobs (MCPHunt's large trace documents
pass the default cap's watchdog trigger). The key is raise-only, up to the worker ceiling, and changes no output byte."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import import_support as support
import pytest

import agentprov.adapters.runner.importer as importer
from agentprov.adapters.profiles import ProfileError, _check_import, load_profile
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.io.workers import RSS_CAP_CEILING, WorkerLimits, WorkerPool

GIB = 1 << 30
PLAIN = "runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_2.json"


@pytest.mark.parametrize("cap", [WorkerLimits().for_kind("map").rss_bytes, 4 * GIB, RSS_CAP_CEILING])
def test_a_cap_from_the_default_to_the_ceiling_is_accepted(cap: int) -> None:
    _check_import({"dialect": "d", "mapper": "m", "map_rss_bytes": cap}, "p", ["head"])


@pytest.mark.parametrize("cap", [GIB, RSS_CAP_CEILING + 1, True, "4 GiB", 4.0 * GIB])
def test_a_lower_larger_or_non_integer_cap_is_refused(cap: Any) -> None:
    with pytest.raises(ProfileError, match="map_rss_bytes"):
        _check_import({"dialect": "d", "mapper": "m", "map_rss_bytes": cap}, "p", ["head"])


def _import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cap: int | None) -> tuple[list[Any], bytes]:
    support.require_golden()
    profile = load_profile("agentdojo-upstream")
    if cap is not None:
        profile = dataclasses.replace(profile, data={**profile.data, "import": {**profile.data["import"], "map_rss_bytes": cap}})
    monkeypatch.setattr(importer, "load_profile", lambda *_a, **_k: profile)
    jobs: list[Any] = []
    run = WorkerPool.run

    def spy(self: WorkerPool, batch: Any, *a: Any, **k: Any) -> Any:
        batch = list(batch)
        jobs.extend(j for j in batch if j.kind == "map")
        return run(self, batch, *a, **k)

    monkeypatch.setattr(WorkerPool, "run", spy)
    root = tmp_path / f"in{cap}"
    support.agentdojo_tree(root, count=2)
    out = tmp_path / f"c{cap}"
    with CorpusWriter(out) as corpus:
        import_source("agentdojo", LocalTree(root), corpus=corpus, profile_id="agentdojo-upstream", part="2024-06",
                      until="aer", in_process=True, pin_check=support.vouch(root))
    aer = sorted(Path(str(out) + ".partial").glob("aer/*/*.aer.jsonl"))
    assert len(aer) == 2
    return jobs, b"".join(p.read_bytes() for p in aer)


def test_the_cap_rides_on_every_map_job_and_changes_no_byte(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_jobs, plain = _import(monkeypatch, tmp_path, None)
    assert plain_jobs and all(j.limits is None for j in plain_jobs)
    capped_jobs, capped = _import(monkeypatch, tmp_path, 4 * GIB)
    assert capped_jobs and all(j.limits is not None and j.limits.for_kind("map").rss_bytes == 4 * GIB for j in capped_jobs)
    assert all(j.limits.for_kind("prov").rss_bytes == WorkerLimits().for_kind("prov").rss_bytes for j in capped_jobs)
    assert capped == plain  # worker limits enter no digest


def test_mcphunt_declares_4_gib() -> None:
    assert load_profile("mcphunt").data["import"]["map_rss_bytes"] == 4 * GIB
