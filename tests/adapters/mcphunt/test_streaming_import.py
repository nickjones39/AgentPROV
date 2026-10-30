"""The MCPHunt import path after D-323 (docs/reports/phase10m/routing.md RB-1..RB-3; D_adapters D.21).

* RB-1: the reader declares ``multi_execution`` and streams, so a trace document maps as one execution per element of
  ``/traces`` (key locator ``{"p": "/traces/<i>"}``, the element's byte range kept beside it);
* RB-2: the profile's ``[import] limits`` raise ``max_json_element_bytes`` to the calibrated 64 MiB, which an import
  applies and records in ``corpus.json``;
* RB-3: a tool result over 1 MiB is carved (D-218) from the trace's own byte range and referenced by ``$blob``.

Inputs are the committed canary-free fixtures, or copies changed in memory with synthetic padding; nothing here carries
a planted value, and nothing prints fixture content.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import mcphunt_support as support

from agentprov.adapters.runner import map_artefact_units
from agentprov.adapters.types import Origin

MIB = 2**20
BIG = "x" * (MIB + 7)  # synthetic: one string just over the 1 MiB inline limit (C.2.1(6))


def _origin(path: str) -> Origin:
    return Origin.from_json({"kind": "hf", "repo": "lihaonan0716/mcphunt-agent-traces", "revision": support.REVISION,
                             "path": path})


def _doc(criterion: str) -> dict[str, Any]:
    spec = support.F()[criterion]
    doc: dict[str, Any] = json.loads((support.FIXTURES / spec["fixture_file"]).read_bytes())
    return doc


def _one_trace(criterion: str) -> dict[str, Any]:
    doc = _doc(criterion)
    doc["traces"] = [doc["traces"][support.F()[criterion]["index"]]]
    return doc


def _bytes(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def _big_result(doc: dict[str, Any]) -> tuple[int, int]:
    """Give the first event and the first tool message of the document's only trace the same synthetic large result."""
    trace = doc["traces"][0]
    i = next(n for n, m in enumerate(trace["messages"]) if m.get("role") == "tool")
    trace["messages"][i]["content"] = BIG
    trace["events"][0]["result_full"] = BIG
    return 0, i


def test_a_document_maps_one_execution_per_trace():
    spec = support.F()["main_turn_cap"]  # a fixture document holding more than one trace
    data = (support.FIXTURES / spec["fixture_file"]).read_bytes()
    results = map_artefact_units(data, _origin(spec["fixture_file"].removeprefix("docs/")), profile_id=support.PROFILE,
                                 limits=support.limits())
    assert len(results) == len(support.items(spec["fixture_file"])) > 1
    assert [unit.primary.locator.key() for _o, unit in results] == [{"p": f"/traces/{n}"} for n in range(len(results))]
    assert not any(outcome.degenerate for outcome, _unit in results)


def test_each_item_carries_its_element_byte_range():
    spec = support.F()["main_turn_cap"]
    data = (support.FIXTURES / spec["fixture_file"]).read_bytes()
    for item in support.items(spec["fixture_file"]):
        start, end = item.locator.bytes or (0, 0)
        assert json.loads(data[start:end]) == item.value["trace"]  # the range is exactly the element's JSON text
        assert item.locator.key() == {"p": item.locator.p}  # the range never enters the source key (C.4.1)


def test_a_trace_over_16_mib_maps_under_the_profile_limit():
    doc = _one_trace("main_benign_success")
    doc["traces"][0]["padding"] = "x" * (17 * MIB)  # synthetic: an extra member the mapper ignores
    data = _bytes(doc)
    default = map_artefact_units(data, _origin("main/synthetic.json"), profile_id=support.PROFILE)
    assert [o.degenerate for o, _u in default] == [True]  # the G.3.2 default refuses the element
    ((outcome, _unit),) = map_artefact_units(data, _origin("main/synthetic.json"), profile_id=support.PROFILE,
                                             limits=support.limits())
    assert not outcome.degenerate


def test_a_tool_result_over_1_mib_is_carved_from_the_trace_byte_range():
    doc = _one_trace("main_benign_success")
    j, i = _big_result(doc)
    data = _bytes(doc)
    ((outcome, unit),) = map_artefact_units(data, _origin("main/synthetic.json"), profile_id=support.PROFILE,
                                            limits=support.limits())
    assert not outcome.degenerate
    digest = hashlib.sha256(BIG.encode()).hexdigest()
    ref = {"$blob": f"sha256:{digest}", "bytes": len(BIG), "media": "text/plain; charset=utf-8"}
    span = unit.primary.locator.bytes
    assert span is not None
    execution = next(r for r in outcome.records if r["k"] == "tool_execution"
                     and {"a": "a0", "bytes": list(span), "p": f"/events/{j}"} in r["src"])
    assert execution["returned"] == ref
    message = next(r for r in outcome.records if r["k"] == "message"
                   and {"a": "a0", "bytes": list(span), "p": f"/messages/{i}"} in r["src"])
    assert message["parts"] == [{**message["parts"][0], "value": ref}] and "text" not in message["parts"][0]
    (blob,) = outcome.carved  # one string, one blob: the message and the execution cite the same bytes
    assert blob.sha256 == digest and blob.data == BIG.encode() and blob.transform == "utf8"
    assert dict(blob.loc) == {"bytes": [span[0], span[1]], "p": f"/events/{j}/result_full"}


def test_a_small_tool_result_stays_inline():
    m = support.map_trace("main_benign_success")
    assert m.outcome.carved == [] and "blobs" not in m.doc.seal


# ------------------------------------------------------------------------------------------------ end to end
def _deposit(base: Path, members: dict[str, bytes]) -> tuple[Path, dict[str, Any]]:
    """A test deposit (its own pin, never the real one) holding trace documents at their dataset labels."""
    path = base / "deposit.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for label, data in sorted(members.items()):
            info = zipfile.ZipInfo(label, (2026, 10, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED  # the synthetic padding would trip the archive ratio limit
            zf.writestr(info, data)
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "deposit", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def _import(base: Path, members: dict[str, bytes]) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    path, pin = _deposit(base, members)
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(base / "c") as writer:
        return import_source(support.PROFILE, tree, corpus=writer, profile_id=support.PROFILE, part="head", pin=pin,
                             snapshot_id="head", mode="release", workers=1)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def test_an_import_streams_every_trace_raises_the_limit_and_stores_the_carved_result(tmp_path):
    spec = support.F()["main_turn_cap"]
    big = _one_trace("main_benign_success")
    j, _i = _big_result(big)
    report = _import(tmp_path, {"main/" + spec["fixture_file"].rsplit("/", 1)[-1]:
                                (support.FIXTURES / spec["fixture_file"]).read_bytes(),
                                "mitigation/synthetic.json": _bytes(big)})
    assert report.exit_code == 0, (report.counters, report.failures[:3])
    n = len(support.items(spec["fixture_file"]))
    assert report.counters["mapped"] == n + 1 and report.counters["degenerate"] == 0, report.counters
    assert report.limits["max_json_element_bytes"] == 64 * MIB
    root = tmp_path / "c.partial"
    manifest = json.loads((root / "corpus.json").read_text())
    assert manifest["limits"]["overrides"] == {"max_json_element_bytes": 64 * MIB}
    keys = sorted(r["source_key"].split("#", 1)[1] for r in _jsonl(root / "executions.jsonl"))
    assert keys == sorted([*(f'{{"p":"/traces/{k}"}}' for k in range(n)), '{"p":"/traces/0"}'])
    carved = [o for o in _jsonl(root / "raw" / "origins.jsonl") if o["origin"]["kind"] == "carved"]
    assert len(carved) == 1
    assert carved[0]["origin"]["loc"]["p"] == f"/events/{j}/result_full" and "bytes" in carved[0]["origin"]["loc"]


def test_every_locator_resolves_from_a_slice_never_the_whole_document():
    """Regen item 149: every src locator is a C.9.1 byte range (a trace's element, or an envelope member's own value),
    so an AER of a document over max_json_bytes (64 MiB) still resolves; each resolves against the stored bytes."""
    from agentprov.aer.locators import LocatorResolver
    from agentprov.ingest.loaders import strict_json_loads

    spec = support.F()["main_turn_cap"]
    data = (support.FIXTURES / spec["fixture_file"]).read_bytes()

    class Store:
        def read_bytes(self, sha256: str) -> bytes:
            assert sha256 == hashlib.sha256(data).hexdigest()
            return data

    def sliced(raw: bytes) -> Any:  # resolution parses a slice, never the whole stored document
        assert len(raw) < len(data)
        return strict_json_loads(raw)

    for item in support.items(spec["fixture_file"]):
        m = support.map_item(item)
        resolver = LocatorResolver(m.header, Store(), loads=sliced)
        locs = [loc for r in m.records for loc in r.get("src", []) if "a" in loc and "o" not in loc]
        assert locs and all("bytes" in loc for loc in locs)
        for loc in locs:
            resolver.resolve(loc)  # LocatorError on a dangling locator
        judge = m.get("judge")
        (envelope_loc,) = judge["src"]
        assert set(envelope_loc) == {"a", "bytes"}
        start, end = envelope_loc["bytes"]
        assert json.loads(data[start:end]) == judge["version"]
