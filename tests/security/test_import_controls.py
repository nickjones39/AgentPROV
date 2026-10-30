"""Import-level security controls proved end to end on synthetic AgentDojo trees (no fixtures, no network).

- SEC-04 (G.3.9): an over-cap loose file is a ``register.jsonl`` row (stage ``ingest``) and keeps no bytes;
  probed at ``limit - 1``, ``limit`` and ``limit + 1`` (K.5.6).
- SEC-19 (HL H.7; T-17): the same bytes at two paths are one execution with two origins.
- SEC-22 (K.12.10; G.4.6): a ``map`` job stopped by a worker limit still ends in a sealed, degenerate AER with a
  register row, and the raw bytes are kept.
- SEC-26 (G.3.8): below the 3.14.8 floor, plain JSON imports are unaffected (no warning, no advisory).
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any

import agentdojo_support as ad
import pytest
from import_harness import run_import

from agentprov.ingest.limits import IngestLimits


def _doc_bytes(n: int = 1) -> tuple[str, bytes]:
    doc = ad.base_log(user_task_id=f"user_task_{n}")
    return ad.path_of(doc), ad.log_bytes(doc)


# ------------------------------------------------------------------------------------------------ SEC-04
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_sec04_an_over_cap_loose_file_is_registered_and_keeps_no_bytes(tmp_path: Path, delta: int) -> None:
    path, data = _doc_bytes()
    limits = IngestLimits().replace(max_artefact_bytes=len(data) - delta)  # data is limit+1, limit or limit-1
    imported = run_import(tmp_path, {path: data}, limits=limits)
    stored = {r["sha256"] for r in imported.rows("raw/origins.jsonl")}
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if delta == 1:
        rows = [r for r in imported.rows("register.jsonl") if r["code"] == "ingest.size.file"]
        assert len(rows) == 1 and rows[0]["stage"] == "ingest" and rows[0]["disposition"] == "not_imported"
        assert digest not in stored and imported.report.counters["mapped"] == 0
        assert not any(p.is_file() for p in (imported.partial / "raw" / "objects").rglob("*"))
    else:
        assert digest in stored and imported.report.counters["mapped"] == 1


# ------------------------------------------------------------------------------------------------ SEC-19
def test_sec19_the_same_bytes_at_two_paths_are_one_execution_with_two_origins(tmp_path: Path) -> None:
    path, data = _doc_bytes()
    copy = path.replace("injection_task_2.json", "copy.json")
    imported = run_import(tmp_path, {path: data, copy: data})
    rows = imported.rows("executions.jsonl")
    assert len(rows) == 1 and imported.report.counters["duplicates"] == 1
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    assert sum(1 for o in imported.rows("raw/origins.jsonl") if o["sha256"] == digest) == 2
    assert any(r["code"] == "dedup.collapsed" for r in imported.rows("register.jsonl"))
    assert rows[0]["n_origins"] == 2


# ------------------------------------------------------------------------------------------------ SEC-22
@pytest.mark.parametrize("limit", ["rss", "cpu", "wall", "output"])
def test_sec22_a_map_job_stopped_by_a_limit_is_registered_with_its_limit_code_and_keeps_the_raw_bytes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str) -> None:
    """The unit is never dropped silently. Since D-219 (``aer/0.2``, regen item 151) the AgentDojo family seals a
    degenerate AER whose task id is declared not captured (before, it could not, and the unit was registered failed);
    either way the limit that stopped the job must still appear (it was lost before phase 12a, when only
    ``map.adapter_defect`` was registered)."""
    from agentprov.io import workers

    real = workers.WorkerPool._run_in_process

    def limited(self: workers.WorkerPool, number: int, job: workers.Job, *args: Any) -> workers.JobResult:
        if job.kind != "map":
            return real(self, number, job, *args)  # D-414 passes the batch spool on
        return workers.JobResult(job.key, job.kind, number, error=workers.WorkerLimitError(limit), isolation="in-process")

    monkeypatch.setattr(workers.WorkerPool, "_run_in_process", limited)
    path, data = _doc_bytes()
    imported = run_import(tmp_path, {path: data})
    assert imported.report.counters["degenerate"] == 1 and imported.report.exit_code == 1
    rows = {r["code"]: r for r in imported.rows("register.jsonl")}
    assert rows[f"worker.limit.{limit}"]["stage"] == "map" and rows[f"worker.limit.{limit}"]["disposition"] == "failed"
    assert rows["map.adapter_defect"]["subject"] == rows[f"worker.limit.{limit}"]["subject"]
    assert "sha256:" + hashlib.sha256(data).hexdigest() in {r["sha256"] for r in imported.rows("raw/origins.jsonl")}


# ------------------------------------------------------------------------------------------------ SEC-26
def test_sec26_below_the_floor_a_plain_json_import_is_unaffected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov import envinfo

    monkeypatch.setattr("sys.version_info", (3, 14, 7, "final", 0))
    assert envinfo.interpreter_advisory() is not None  # the patch is seen
    path, data = _doc_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("error", envinfo.InterpreterUnpatchedWarning)
        imported = run_import(tmp_path, {path: data})
    assert imported.report.counters["mapped"] == 1
    manifest = json.loads((imported.partial / "corpus.json").read_text(encoding="utf-8"))
    assert manifest["producer"]["interpreter_advisory"] is None
    assert not any(r["code"] == "ingest.interpreter.unpatched" for r in imported.rows("register.jsonl"))


def test_sec26_requires_python_and_the_interpreter_pin_are_314() -> None:
    import tomllib

    root = Path(__file__).resolve().parents[2]
    assert tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"] == ">=3.14"
    assert (root / ".python-version").read_text(encoding="utf-8").strip() == "3.14.8"  # exact pin (orchestrator, user-approved 2026-10-28)
