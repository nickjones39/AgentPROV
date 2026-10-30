"""Profile-driven selection in the import pipeline (docs/architecture D.2.8 case 4, D.4.2 ``[import]``, D.6.12 item 6).

``[import] exclude`` entries register every walked file they match with their ``select.*`` code (and the owner of a
``select.owned_elsewhere`` entry); ``variant_labels`` send a variant of another part to ``select.dialect_planned``;
``context_artefacts`` are stored with their pinned origins and handed to a mapper that consumes them. The profiles are the
shipped one with textual edits (dev-only variants), injected where the pipeline loads profiles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import import_support as support
import pytest

import agentprov.adapters.runner as runner_pkg
import agentprov.adapters.runner.importer as importer
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentdojo"))
import agentdojo_support  # noqa: E402


def _with(monkeypatch: pytest.MonkeyPatch, replace: dict[str, str]) -> Any:
    profile = agentdojo_support.profile_with(replace)
    monkeypatch.setattr(importer, "load_profile", lambda _pid: profile)
    monkeypatch.setattr(runner_pkg, "load_profile", lambda _pid: profile)
    return profile


def _run(tree_root: Path, out: Path, part: str = "2024-06", **kwargs: Any) -> Any:
    kwargs.setdefault("pin_check", support.vouch(tree_root))
    with CorpusWriter(out) as corpus:
        return import_source("agentdojo", LocalTree(tree_root), corpus=corpus, in_process=True, part=part, until="aer",
                             **kwargs)


def _register(out: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (out.with_name(out.name + ".partial") / "register.jsonl").read_text().splitlines()]


def _write(root: Path, rel: str, data: bytes) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


EXCLUDE = '  { glob = "**/._*", code = "select.not_execution_artefact" },\n'


def test_excluded_files_are_registered_with_their_code_and_owner(tmp_path, monkeypatch):
    _with(monkeypatch, {EXCLUDE: EXCLUDE
                        + '  { glob = "vendor/**", code = "select.owned_elsewhere", owner = "agentdojo" },\n'
                        + '  { glob = "agentlab/**", code = "select.owned_elsewhere", owner = "ext:agentlab" },\n'
                        + '  { glob = "runs/cells.json", code = "select.not_execution_artefact" },\n'})
    support.agentdojo_tree(tmp_path / "in", count=1)
    _write(tmp_path / "in", "vendor/runs/x.json", b"{}")
    _write(tmp_path / "in", "agentlab/res/y.json", b"{}")
    _write(tmp_path / "in", "runs/cells.json", b"[]")
    _write(tmp_path / "in", "README.md", b"neither selected nor excluded\n")
    report = _run(tmp_path / "in", tmp_path / "c")
    assert report.exit_code == 0 and report.counters["mapped"] == 1 and report.counters["excluded"] == 3
    rows = {r["subject"]["path"]: r for r in _register(tmp_path / "c") if r["stage"] == "select"}
    assert set(rows) == {"vendor/runs/x.json", "agentlab/res/y.json", "runs/cells.json"}
    assert rows["vendor/runs/x.json"]["owner"] == {"corpus_id": "agentdojo-upstream", "source_id": "agentdojo"}
    assert rows["agentlab/res/y.json"]["owner"] == {"corpus_id": "ext:agentlab", "source_id": "ext:agentlab"}
    assert rows["runs/cells.json"]["code"] == "select.not_execution_artefact" and rows["runs/cells.json"]["owner"] is None
    assert all(r["disposition"] == "not_imported" for r in rows.values())


def test_out_of_scope_executions_are_registered_not_dropped_d191(tmp_path, monkeypatch):
    _with(monkeypatch, {EXCLUDE: EXCLUDE
                        + '  { glob = "clean/**", code = "select.out_of_scope", note = "D-143" },\n'})
    support.agentdojo_tree(tmp_path / "in", count=1)
    _write(tmp_path / "in", "clean/runs/a.json", b"{}")
    _write(tmp_path / "in", "clean/runs/b.json", b"{}")
    report = _run(tmp_path / "in", tmp_path / "c")
    assert report.exit_code == 0 and report.counters["mapped"] == 1 and report.counters["excluded"] == 2
    rows = [r for r in _register(tmp_path / "c") if r["stage"] == "select"]
    assert {r["subject"]["path"] for r in rows} == {"clean/runs/a.json", "clean/runs/b.json"}
    assert all(r["code"] == "select.out_of_scope" and r["owner"] is None and r["disposition"] == "not_imported"
               for r in rows)


def test_a_variant_of_another_part_is_registered_dialect_planned(tmp_path, monkeypatch):
    _with(monkeypatch, {'variants = ["v0.k11", "v1.k14", "v1.k14.incomplete"]':
                        'variants = ["v0.k11", "v1.k14", "v1.k14.incomplete"]\n'
                        'variant_labels = { "v0.k11" = "2024-06", "v1.k14" = "head" }'})
    support.agentdojo_tree(tmp_path / "in", count=1)
    v1 = agentdojo_support.base_log(benchmark_version="v1.2.1", evaluation_timestamp="2025-07-01 10:00:00",
                                    agentdojo_package_version="unknown")
    _write(tmp_path / "in", "runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_2.json",
           agentdojo_support.log_bytes(v1))
    report = _run(tmp_path / "in", tmp_path / "c", part="2024-06")
    assert report.counters["mapped"] == 1 and report.counters["registered"] == 1
    planned = [r for r in _register(tmp_path / "c") if r["code"] == "select.dialect_planned"]
    assert len(planned) == 1 and "belongs to part head" in planned[0]["detail"]
    other = _run(tmp_path / "in", tmp_path / "d", part="head")  # and the other way round
    assert other.counters["mapped"] == 1 and other.counters["registered"] == 1


def test_context_artefacts_are_stored_with_their_pinned_origin(tmp_path, monkeypatch):
    _with(monkeypatch, {"layout_depth = 5": 'layout_depth = 5\ncontext_artefacts = ["notes/*.txt"]'})
    support.agentdojo_tree(tmp_path / "in", count=1)
    _write(tmp_path / "in", "notes/cells.txt", b"cells\n")
    report = _run(tmp_path / "in", tmp_path / "c")
    assert report.exit_code == 0 and report.counters["mapped"] == 1 and report.counters["excluded"] == 0
    partial = tmp_path / "c.partial"
    origins = [json.loads(line) for line in (partial / "raw" / "origins.jsonl").read_text().splitlines()]
    paths = {o["origin"].get("path") for o in origins}
    assert "notes/cells.txt" in paths and all(o["origin"]["kind"] == "git" for o in origins)
    assert not [r for r in _register(tmp_path / "c") if r["subject"].get("path") == "notes/cells.txt"]
