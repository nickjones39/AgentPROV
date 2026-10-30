"""D-530 item 6: runner item R3 pinned objects for a reader without per-unit inputs (MCPHunt's LFS documents).

Before D-530 the pinned objects were placed beside their pointers only inside the per-unit discovery (readers with
``auxiliary_for``), so a reader without it never saw them. The FooBench reader has no per-unit inputs; here its trace is
an LFS pointer in the input tree and the object is pinned. Inputs: the committed FooBench fixture (loaded, never printed).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import import_support as support

from agentprov.adapters.runner.importer import LocalTree, PinnedObject, import_source
from agentprov.adapters.types import Origin
from agentprov.corpus.writer import CorpusWriter

FOO = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "foobench"
POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:%s\nsize %d\n"


def test_a_pinned_object_is_mapped_for_a_reader_without_per_unit_inputs(tmp_path):
    trace = (FOO / "trace-001.jsonl").read_bytes()
    root = tmp_path / "in" / "deposit" / "traces"
    root.mkdir(parents=True)
    (root / "trace-001.jsonl").write_bytes(POINTER % (hashlib.sha256(trace).hexdigest().encode(), len(trace)))
    for name in ("sub-trace-001.jsonl", "screenshot-0.png"):
        (root / name).write_bytes((FOO / name).read_bytes())
    (tmp_path / "object.jsonl").write_bytes(trace)
    label = "deposit/traces/trace-001.jsonl"
    origin = Origin.hf("example/traces", "c" * 40, label)
    obj = PinnedObject(label, origin, str(tmp_path / "object.jsonl"), hashlib.sha256(trace).hexdigest(), len(trace))
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("foobench", LocalTree(tmp_path / "in"), corpus=writer, profile_id="foobench", part="fixture",
                               pin_check=support.vouch(tmp_path / "in"), pinned_objects=[obj], in_process=True, until="aer")
    # the overlay object maps; the tree's other JSONL file is not valid FooBench JSON and seals degenerate (D-219)
    assert report.counters["mapped"] - report.counters["degenerate"] == 1
    partial = tmp_path / "c.partial"
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    headers = [json.loads((partial / r["paths"]["aer"]).read_bytes().split(b"\n", 1)[0]) for r in rows]
    (header,) = [h for h in headers if h["artifacts"][0]["origin"]["kind"] == "hf"]
    assert header["artifacts"][0]["origin"] == origin.to_json()
