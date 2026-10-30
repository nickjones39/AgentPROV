"""The importer side of the GUI core prerequisites (regen-batch D-525): progress 0.2 stage events and unit kinds
(D-393), a drain at batch boundaries (D-394) and ``--skip-prov-conformance`` (G2c-5, D-432)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov import drain
from agentprov.adapters.runner.importer import IdentityRefusedError, LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.progress import ProgressEvent


class Events:
    def __init__(self, on_unit: Any = None) -> None:
        self.events: list[ProgressEvent] = []
        self._on_unit = on_unit

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)
        if event.kind == "unit_done" and self._on_unit is not None:
            self._on_unit(sum(1 for e in self.events if e.kind == "unit_done"))


def _run(tmp: Path, out: str, **kwargs: Any) -> Any:
    kwargs.setdefault("in_process", True)
    kwargs.setdefault("drain", True)  # D-394: the CLI import opts in (PR-6)
    tree = LocalTree(tmp / "in")
    with CorpusWriter(tmp / out) as corpus:
        return import_source("agentdojo", tree, corpus=corpus, part="2024-06", pin_check=support.vouch(tmp / "in"),
                             **kwargs)


def _bytes_under(root: Path, *dirs: str) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for d in dirs for p in sorted((root / d).rglob("*")) if p.is_file()}


@pytest.fixture(autouse=True)
def _fresh_drain() -> Any:
    drain.reset()
    yield
    drain.reset()


def test_stage_events_and_unit_kinds(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=3)
    events = Events()
    _run(tmp_path, "c", progress=events)
    stages = [(e.stage, e.fields.get("phase")) for e in events.events if e.kind == "stage"]
    assert ("discover", "begin") in stages and ("discover", "end") in stages and stages[-1] == ("map", "end")
    start = next(e for e in events.events if e.kind == "start")
    assert start.fields["unit_kind"] == "execution" and start.fields["candidates"] == 3 and start.total == 3
    done = [e for e in events.events if e.kind == "unit_done"]
    assert len(done) == 3 and {e.fields["unit_kind"] for e in done} == {"execution"}  # the pool's jobs are not units
    steps = {e.stage for e in events.events if e.kind == "step"}
    assert {"map", "prov", "validate"} <= steps
    assert any(e.kind == "trace" and str(e.stage).startswith("t1.") for e in events.events)


def test_a_drain_stops_at_a_batch_boundary_and_the_import_resumes_to_the_same_tree(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    report = _run(tmp_path, "c", batch_size=1, progress=Events(on_unit=lambda n: drain.request() if n == 1 else None))
    rows = (tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines()
    assert 1 <= len(rows) < 4 and any("drained" in n for n in report.notices)
    drain.reset()
    resumed = _run(tmp_path, "c")
    assert resumed.counters["skipped_resume"] == len(rows)
    _run(tmp_path, "w")
    a, b = support.tree_bytes(tmp_path / "c.partial"), support.tree_bytes(tmp_path / "w.partial")
    a.pop("corpus.json"), b.pop("corpus.json")
    assert a == b


def test_skipping_prov_conformance_marks_the_corpus_and_changes_no_output_byte(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=2)
    skipped = _run(tmp_path, "s", prov_conformance=False)
    _run(tmp_path, "f")
    s, f = tmp_path / "s.partial", tmp_path / "f.partial"
    assert _bytes_under(s, "aer", "sem", "prov") == _bytes_under(f, "aer", "sem", "prov")  # no output byte moves
    assert json.loads((s / "corpus.json").read_text())["validation"] == {"prov_conformance": "skipped"}
    assert "validation" not in json.loads((f / "corpus.json").read_text())  # an ordinary corpus is unchanged
    stage = next(x for x in json.loads((s / "derivation.json").read_text())["stages"] if x["stage"] == "validation")
    assert stage["skipped"] == ["tier4:agentprov-prov/0.1"] and not any(c.startswith("tier4:") for c in stage["checks"])
    results = [json.loads(line) for line in (s / "validation" / "results.jsonl").read_text().splitlines()]
    assert results and not any(k.startswith("pv.") for r in results for k in r["checks"])
    assert any("--skip-prov-conformance" in n for n in skipped.notices)


def test_a_skipped_working_corpus_is_never_resumed_with_tier_4_or_the_reverse(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=2)
    _run(tmp_path, "s", prov_conformance=False, limit=1)
    with pytest.raises(IdentityRefusedError):
        _run(tmp_path, "s")
