"""C.2.1, C.8 / AER-V01..V03, V09: file framing, record order, ``after`` edges, cycles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aer_support import codes_of, edit, example_records, example_store, make_registry, seal_record

from agentprov.aer.canon import dumps_line
from agentprov.aer.validate import AerValidator, validate_file, validate_records


def lines(records: list[dict[str, Any]]) -> list[bytes]:
    return [dumps_line(r) for r in [*records, seal_record(records)]]


def feed_all(raw: list[bytes], **kw: Any) -> list[str]:
    v = AerValidator(store=example_store(), catalogues=make_registry(), mode="release", **kw)
    for line in raw:
        v.feed(line)
    return [f.code for f in v.finish().errors]


def test_a_correct_file_has_no_findings() -> None:
    assert feed_all(lines(example_records())) == []


def test_missing_final_newline_crlf_blank_and_bom() -> None:
    good = lines(example_records())
    assert "ingest.jsonl.no_final_newline" in feed_all([*good[:-1], good[-1][:-1]])
    crlf = [*good]
    crlf[3] = crlf[3][:-1] + b"\r\n"
    assert "ingest.jsonl.crlf" in feed_all(crlf)
    assert "ingest.jsonl.blank" in feed_all([*good[:3], b"\n", *good[3:]])
    assert "ingest.json.bom" in feed_all([b"\xef\xbb\xbf" + good[0], *good[1:]])
    assert "ingest.jsonl.nul" in feed_all([*good[:3], b'{"k":"actor"\x00}\n', *good[3:]])


def test_oversize_lines_are_reported_without_holding_them() -> None:
    v = AerValidator(store=None, catalogues=make_registry())
    v.feed(b"x" * 64, oversize=True)
    assert "ingest.jsonl.line_too_long" in [f.code for f in v.finish().errors]


def test_every_line_must_be_canonical_jcs() -> None:
    good = lines(example_records())
    spaced = [*good]
    spaced[1] = spaced[1].replace(b'"id":', b'"id": ', 1)
    assert "aer.jcs.noncanonical" in feed_all(spaced)
    unsorted = [*good]
    unsorted[1] = b'{"k":"actor","id":"agent","kind":"llm_agent","ev":"D","rule":["tst.d@1"],"name":"agent-under-test"}\n'
    assert "aer.jcs.noncanonical" in feed_all(unsorted)
    assert "aer.jcs.noncanonical" in feed_all([*good[:2], b'{"k":"actor","id":"x","ev":"D","params":1.0}\n', *good[3:]])


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b'{"k":"actor","k":"actor"}\n', "ingest.json.duplicate_key"),
        (b'{"a":NaN}\n', "ingest.number.nonfinite"),
        (b"[1,2]\n", "aer.schema.pattern"),
        (b"{\n", "ingest.json.syntax"),
    ],
)
def test_strict_parse_findings_keep_ingest_codes(data: bytes, code: str) -> None:
    good = lines(example_records())
    assert code in feed_all([*good[:2], data, *good[2:]])


def test_first_line_is_the_header_and_last_the_seal() -> None:
    good = lines(example_records())
    assert "aer.order.envelope" in feed_all(good[1:])  # no header
    assert "aer.order.envelope" in feed_all(good[:-1])  # no seal
    assert "aer.order.envelope" in feed_all([good[0], good[-1], *good[1:-1]])  # seal not last
    assert "aer.order.envelope" in feed_all([*good[:2], good[0], *good[2:]])  # a second header
    assert "aer.order.envelope" in feed_all([good[0]])  # fewer than two lines
    assert "aer.order.envelope" in feed_all([])
    assert "aer.order.envelope" in feed_all([*good[:-1], good[-1], good[-1]])  # two seals


def test_a_validator_cannot_be_reused_after_finish() -> None:
    v = AerValidator(store=None, catalogues=make_registry())
    v.finish()
    with pytest.raises(RuntimeError, match="finished"):
        v.feed(b"{}\n")
    with pytest.raises(RuntimeError, match="finished"):
        v.finish()


def test_after_edges_must_be_acyclic() -> None:
    base = example_records()
    self_edge = edit(base, "m1", after=[{"id": "m1", "b": "causal"}], evf={"/after": "D"}, rule=["tst.d@1#/after"])
    assert "aer.order.cycle" in codes_of(validate_records([*self_edge, seal_record(self_edge)], store=None, catalogues=make_registry()))
    # a two-record cycle needs a forward edge, which is reported as such, and the cycle is found at the end
    cyc = edit(base, "m1", after=[{"id": "te0", "b": "causal"}], evf={"/after": "D"}, rule=["tst.d@1#/after"])
    cyc = edit(cyc, "te0", after=[{"id": "m1", "b": "causal"}], evf={"/after": "D"}, rule=["tst.d@1", "tst.d@1#/after"])
    found = codes_of(validate_records([*cyc, seal_record(cyc)], store=None, catalogues=make_registry()))
    assert "aer.order.cycle" in found and "aer.ref.forward" in found


def test_serialisation_order_is_not_an_occurrence_claim() -> None:
    # m1 may precede m0 in the file (C.16.3) as long as every reference is backward; no `after` edge is implied.
    recs = example_records()
    swapped = [r for r in recs if r["id"] not in ("m0", "mc0")]
    index = next(i for i, r in enumerate(swapped) if r["id"] == "m1")
    reordered = [*swapped[:index], *[r for r in recs if r["id"] in ("m0", "mc0")], *swapped[index:]]
    assert codes_of(validate_records([*reordered, seal_record(reordered)], store=None, catalogues=make_registry())) == []


def test_validate_file_reads_binary_and_reports_line_numbers(tmp_path: Path) -> None:
    good = lines(example_records())
    path = tmp_path / "x.aer.jsonl"
    path.write_bytes(b"".join(good))
    assert validate_file(path, store=example_store(), catalogues=make_registry()).ok
    broken = [*good]
    broken[2] = broken[2].replace(b"tool_runtime", b"tool_runtimx")
    path.write_bytes(b"".join(broken))
    report = validate_file(path, store=example_store(), catalogues=make_registry())
    assert not report.ok and any(f.line == 2 for f in report.errors)
    assert not any(b"\r" in line for line in good)
