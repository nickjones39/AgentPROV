"""D-218: a mapper carves a string of its primary artefact into a blob; the runner stores it with a ``carved`` origin
before the AER that references it is validated, and ``recompute`` and ``verify`` reproduce it.

FooBench's mapper is wrapped (in process) so that it carves the first string of the trace's first line and puts the
``$blob`` reference in its first ``artefact`` record's ``content`` (a Json position, C.11.5). Fixture bytes are read by
the test, never printed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import import_support as support
from agentprov.adapters.foobench.mapper import FooMapper
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter

REPO = Path(__file__).resolve().parents[3]
FOO = REPO / "tests" / "fixtures" / "foobench"
FOO_FILES = ("trace-001.jsonl", "sub-trace-001.jsonl", "screenshot-0.png")


def _first_string(value: Any, at: str = "") -> str | None:
    if isinstance(value, str):
        return at
    if isinstance(value, dict):
        for key in sorted(value):
            found = _first_string(value[key], f"{at}/{key.replace('~', '~0').replace('/', '~1')}")
            if found is not None:
                return found
    if isinstance(value, list):
        for i, element in enumerate(value):
            found = _first_string(element, f"{at}/{i}")
            if found is not None:
                return found
    return None


@pytest.fixture
def carving(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    original = FooMapper.map

    def map_(self: Any, unit: Any, ctx: Any) -> list[dict[str, Any]]:
        records = [dict(r) for r in original(self, unit, ctx)]
        first = json.loads((FOO / "trace-001.jsonl").read_bytes().split(b"\n", 1)[0])
        pointer = _first_string(first)
        assert pointer is not None
        ref = ctx.carve({"line": 0, "p": pointer}, "utf8")
        artefact = next(r for r in records if r.get("k") == "artefact" and "content" in r)
        artefact["content"] = ref
        seen.update(ref=ref, pointer=pointer, value=first)
        return records

    monkeypatch.setattr(FooMapper, "map", map_)
    return seen


def _import(tmp: Path) -> tuple[Any, Path]:
    root = tmp / "in"
    root.mkdir()
    for name in FOO_FILES:
        (root / name).write_bytes((FOO / name).read_bytes())
    check = support.vouch(root, repo="https://github.com/nickjones39/AgentPROV", commit="a" * 40)
    with CorpusWriter(tmp / "c") as writer:
        report = import_source("foobench", LocalTree(root), corpus=writer, profile_id="foobench", part="fixture",
                               in_process=True, pin_check=check)
    return report, tmp / "c.partial"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def test_a_carved_blob_is_stored_with_its_origin_and_referenced_by_the_aer(tmp_path, carving):
    report, partial = _import(tmp_path)
    assert report.counters["mapped"] == 1 and not [f for f in report.failures if f["code"] == "validate.failed"]
    sha = carving["ref"]["$blob"].removeprefix("sha256:")
    trace_sha = hashlib.sha256((FOO / "trace-001.jsonl").read_bytes()).hexdigest()
    origins = {(o["sha256"], json.dumps(o["origin"], sort_keys=True)) for o in _jsonl(partial / "raw" / "origins.jsonl")}
    assert ("sha256:" + sha, json.dumps({"from": trace_sha, "kind": "carved", "loc": {"line": 0, "p": carving["pointer"]},
                                         "transform": "utf8"}, sort_keys=True)) in origins
    stored = next(partial.glob(f"raw/objects/{sha[:2]}/{sha}.*")).read_bytes()
    assert hashlib.sha256(stored).hexdigest() == sha and carving["ref"]["bytes"] == len(stored)
    (row,) = _jsonl(partial / "executions.jsonl")
    seal = json.loads((partial / row["paths"]["aer"]).read_bytes().splitlines()[-1])
    assert "sha256:" + sha in seal["blobs"]


def test_recompute_and_verify_reproduce_the_carved_blob(tmp_path, carving, monkeypatch, capsys):
    from agentprov.cli.main import main
    from agentprov.corpus.verify import verify_corpus

    _report, partial = _import(tmp_path)
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(partial), "--dry-run", "--no-reuse", "--in-process", "--json",
                 "--progress", "off"])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0 and summary["counters"]["identical"] == summary["counters"]["selected"] == 1, summary
    result = verify_corpus(partial, level="chain", in_process=True)
    assert result.counters.get("carved_checked") == 1
    assert not [f for f in result.findings if f.status == "failed"], result.findings


def test_a_carved_member_that_does_not_check_fails_the_unit(tmp_path, monkeypatch, carving):
    from agentprov.adapters.runner import CarvedBlob

    real = CarvedBlob.header

    def lying(self: CarvedBlob) -> dict[str, Any]:
        return {**real(self), "from": "0" * 64}  # names a source the job was not given

    monkeypatch.setattr(CarvedBlob, "header", lying)
    report, partial = _import(tmp_path)
    # the job is failed: the unit falls back to the degenerate path (a degenerate AER since D-219, its task id not
    # captured), registered map.adapter_defect, and nothing of the carved member is stored
    assert report.counters["degenerate"] == 1 and "map.adapter_defect" in [e["code"] for e in report.register]
    assert not any(o["origin"].get("kind") == "carved" for o in _jsonl(partial / "raw" / "origins.jsonl"))


def test_a_unit_whose_records_the_writer_refuses_stores_nothing_it_carved(tmp_path, monkeypatch, carving):
    """D-218 check-and-hold: the carved blob is held, not stored, until a written AER cites it. A unit whose records the
    write gate rejects falls back (FooBench's toy degenerate header then fails too: a registered map.adapter_defect), so
    no AER cites the blob and no carved object is stored."""
    wrapped = FooMapper.map

    def broken(self: Any, unit: Any, ctx: Any) -> list[dict[str, Any]]:
        records = wrapped(self, unit, ctx)
        records[1] = {**records[1], "not_a_member": True}  # the write gate refuses the record (aer.schema.additional)
        return records

    monkeypatch.setattr(FooMapper, "map", broken)
    report, partial = _import(tmp_path)
    assert report.counters["mapped"] == 0 or any(e["code"] == "validate.failed" for e in report.register)
    assert not any(o["origin"].get("kind") == "carved" for o in _jsonl(partial / "raw" / "origins.jsonl"))
    sha = carving["ref"]["$blob"].removeprefix("sha256:")
    assert not list(partial.glob(f"raw/objects/{sha[:2]}/{sha}.*"))


def test_no_carved_member_stays_held_after_its_result_is_closed(tmp_path, monkeypatch, carving):
    from agentprov.adapters.runner.importer import _Pipeline

    pipelines: list[Any] = []
    carved = _Pipeline._carved

    def spy(self: Any, result: Any, sources: Any) -> Any:
        pipelines.append(self)
        return carved(self, result, sources)

    monkeypatch.setattr(_Pipeline, "_carved", spy)
    report, _partial = _import(tmp_path)
    assert report.counters["mapped"] == 1 and pipelines
    assert all(p._held == {} for p in pipelines)  # the members died with their result (closed spools)
