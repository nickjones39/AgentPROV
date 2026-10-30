"""``inspect.eval`` reader: sniffing, the per-container plan, the band and the archive limits (D.9.1, D.9.4; G.3.5).

Synthetic logs only (built in code). Failures print codes, labels and counts, never log content (R-42).
"""

from __future__ import annotations

import io
import json
import zipfile


import inspect_support as support
from agentprov.adapters.inspect.dialect import FLAG_CONTAINER, FLAG_MESSAGE_POOL, InspectEvalReader, classify_label
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import ArtefactRef, Origin
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def test_sniff_container_by_magic_and_member_by_keys():
    reader = InspectEvalReader()
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": support.basic_sample()})
    sniff = reader.sniff(data, label="x.eval", limits=LIMITS)
    assert sniff.match and FLAG_CONTAINER in sniff.flags and sniff.variant is None
    member = json.dumps(support.basic_sample()).encode()
    sniff = reader.sniff(member, label="samples/s1_epoch_1.json", limits=LIMITS)
    assert sniff.match and sniff.variant == "v2" and sniff.flags == frozenset()
    for foreign in (json.dumps(support.synthetic_header()).encode(), b"[1, 2]", b"not json", b'{"id": 1, "a": 1, "a": 2}'):
        assert not reader.sniff(foreign, label="x", limits=LIMITS).match  # total: never raises for foreign input


def test_parse_yields_one_item_at_the_json_root():
    reader = InspectEvalReader()
    member = json.dumps(support.basic_sample()).encode()
    ref = ArtefactRef("a0", support.sha256(member), len(member), "application/json",
                      Origin.member("0" * 64, "samples/s1_epoch_1.json", 93, "00000000", len(member)))
    items = list(reader.parse(member, ref, limits=LIMITS))
    assert len(items) == 1 and items[0].locator.key() == {"p": ""} and items[0].dialect == "inspect.eval"


def test_labels_are_classified_without_opening_anything():
    assert classify_label("header.json") == "header"
    assert classify_label("samples/42-1_epoch_1.json") == "sample"
    assert classify_label("samples/42-1_epoch_1/events/0.json") == "chunked"
    assert classify_label("_journal/start.json") == "other" and classify_label("summaries.json") == "other"


def test_members_outside_the_profile_patterns_are_not_selected(tmp_path):
    extra = {"_journal/start.json": b"{}", "summaries.json": b"[]", "reductions.json": b"[]"}
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": support.basic_sample()}, extra=extra)
    imported = support.import_log(data, tmp_path / "raw")
    dispositions = {r.label: r.disposition for r in imported.member_rows}
    assert dispositions == {"header.json": "selected", "samples/s1_epoch_1.json": "selected",
                            "_journal/start.json": "not_selected", "summaries.json": "not_selected",
                            "reductions.json": "not_selected"}
    assert len(imported.units) == 1 and all(r.method == 93 for r in imported.member_rows)


def test_out_of_band_producer_is_registered_dialect_planned(tmp_path):
    for header in (support.synthetic_header(producer="0.3.170"), support.synthetic_header(producer="0.3.200"),
                   support.synthetic_header(version=3)):
        data = support.build_eval(header, {"s1_epoch_1.json": support.basic_sample()})
        imported = support.import_log(data, tmp_path / f"raw-{len(list(tmp_path.iterdir()))}")
        assert imported.units == []
        assert [r["code"] for r in imported.register] == ["select.dialect_planned"]


def test_missing_header_is_registered_dialect_planned(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("samples/s1_epoch_1.json", json.dumps(support.basic_sample()))
    profile = load_profile("survey-agentharm")
    reader = InspectEvalReader()
    plan = reader.plan([], lambda sha: b"", profile)
    assert plan.units == [] and plan.register[0]["code"] == "select.dialect_planned"
    imported = support.import_log(buf.getvalue(), tmp_path / "raw")
    assert imported.units == [] and imported.register[0]["code"] == "select.dialect_planned"


def test_chunked_sample_shape_is_registered_dialect_planned(tmp_path):
    profile = load_profile("survey-agentharm")
    patterns = profile.data["family"]["inspect"]["members"]  # the shipped profile selects only the classic shape
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": support.basic_sample()},
                              extra={"samples/s2_epoch_1/events/0.json": b"{}"})
    imported = support.import_log(data, tmp_path / "raw")
    assert "samples/*_epoch_*.json" in patterns
    chunked = [r for r in imported.member_rows if r.label == "samples/s2_epoch_1/events/0.json"]
    assert chunked[0].disposition == "not_selected" and len(imported.units) == 1
    reader = InspectEvalReader()
    from agentprov.adapters.inspect.dialect import MemberObject

    header = json.dumps(support.synthetic_header()).encode()
    members = [MemberObject("header.json", support.sha256(header), len(header),
                            Origin.member("0" * 64, "header.json", 93, "00000000", len(header))),
               MemberObject("samples/s2_epoch_1/events/0.json", support.sha256(b"{}"), 2,
                            Origin.member("0" * 64, "samples/s2_epoch_1/events/0.json", 93, "00000000", 2))]
    store = {support.sha256(header): header, support.sha256(b"{}"): b"{}"}
    plan = reader.plan(members, store.__getitem__, profile)
    assert plan.units == [] and [r["code"] for r in plan.register] == ["select.dialect_planned"]


def test_message_pool_shape_gives_unsupported_variant(tmp_path):
    sample = support.basic_sample()
    sample["message_pool"] = sample.pop("events_data")["messages"]
    sniff = InspectEvalReader().sniff(json.dumps(sample).encode(), label="m", limits=LIMITS)
    assert sniff.match and FLAG_MESSAGE_POOL in sniff.flags
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": sample})
    imported = support.import_log(data, tmp_path / "raw")
    unit = imported.units[0]
    assert unit.outcome.degenerate and unit.issue_codes() == ["unsupported_variant"]
    assert [r["k"] for r in unit.records] == ["execution", "scope", "seal"]
    assert imported.validate(unit).ok


def test_unparseable_sample_member_gives_a_degenerate_aer(tmp_path):
    data = support.build_eval(support.synthetic_header(), {}, extra={"samples/s1_epoch_1.json": b'{"id": "s1", "epoch": 1}'})
    imported = support.import_log(data, tmp_path / "raw")
    unit = imported.units[0]
    assert unit.outcome.degenerate and unit.issue_codes() == ["unparseable_artefact"]
    assert imported.validate(unit).ok


# ------------------------------------------------------------------------------------------------ method 93 limits
def test_method_93_members_decompress_only_through_the_gate(tmp_path):
    """A Zstandard member over the ratio limit is rejected by the G.3.5 gate before decompression; nothing is mapped."""
    sample = support.basic_sample()
    sample["padding"] = "0" * (4 * 1024 * 1024)  # ~4 MiB of one byte: compresses far beyond max_ratio
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": sample})
    imported = support.import_log(data, tmp_path / "raw")
    row = next(r for r in imported.member_rows if r.label == "samples/s1_epoch_1.json")
    assert (row.disposition, row.code, row.method) == ("rejected", "ingest.archive.ratio", 93)
    assert imported.units == [] and [e.code for e in imported.events] == ["ingest.archive.ratio"]
    # the same member passes with an explicit, recorded override of the ratio limit
    relaxed = LIMITS.replace(max_ratio=100_000)
    imported = support.import_log(data, tmp_path / "raw2", limits=relaxed)
    assert len(imported.units) == 1 and next(r for r in imported.member_rows
                                             if r.label == "samples/s1_epoch_1.json").disposition == "selected"


def test_member_size_limit_rejects_the_member(tmp_path):
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": support.basic_sample()})
    sample_size = len(json.dumps(support.basic_sample()).encode())
    imported = support.import_log(data, tmp_path / "raw", limits=LIMITS.replace(max_member_bytes=sample_size - 1))
    row = next(r for r in imported.member_rows if r.label == "samples/s1_epoch_1.json")
    assert (row.disposition, row.code) == ("rejected", "ingest.archive.size") and imported.units == []


def test_deflate_members_are_accepted_too(tmp_path):
    data = support.build_eval(support.synthetic_header(), {"s1_epoch_1.json": support.basic_sample()},
                              method=zipfile.ZIP_DEFLATED)
    imported = support.import_log(data, tmp_path / "raw")
    assert len(imported.units) == 1 and {r.method for r in imported.member_rows} == {8}


def test_reader_iterates_profile_includes_only():
    class Tree:
        def walk(self):
            for label in ("agentharm/results/a/x.eval", "agentharm/results/timing_summary.csv", "agentdojo/results/r.json",
                          "agentharm/results/a/._x.eval"):
                yield support_candidate(label)

        def open(self, label, *, max_bytes):  # pragma: no cover - discovery reads nothing
            raise AssertionError("discovery must not read contents")

    labels = [c.label for c in InspectEvalReader().iter_artefacts(Tree(), load_profile("survey-agentharm"))]
    assert labels == ["agentharm/results/a/x.eval"]


def support_candidate(label: str):
    from agentprov.adapters.types import CandidateArtefact

    return CandidateArtefact(label, 1, Origin.member("0" * 64, label, 0, "00000000", 1))
