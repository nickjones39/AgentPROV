"""Core review A's CA-1 and CA-2 fixes hold for ``aer/0.2`` records too (deferrals part C).

``aer/0.2`` is validated by the same ``AerValidator`` code path as ``aer/0.1`` (version modes, D-212), so the fixes of
regen items 60 (CA-1: the body of a ``{"$lit": ...}`` escape is not read as reserved forms) and 61 (CA-2: the
``MAX_FINDINGS`` cap never hides an error) apply unchanged. These tests run their cases on records whose header says
``"aer": "0.2"``. (The writer half of CA-1 is covered by ``test_lit_escape_walk``: the writer always seals ``aer/0.2``.)
"""

from __future__ import annotations

from typing import Any

import pytest
import test_findings_cap as cap
import test_lit_escape_walk as lit
from aer_support import example_records, example_store, seal_record

from agentprov.aer.canon import dumps_line
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.validate import MAX_FINDINGS


def _as_02(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recs[0]["aer"] = "0.2"
    return recs


@pytest.mark.parametrize("source", lit.ESCAPED, ids=lit.IDS)
def test_aer_02_an_escaped_body_is_not_read_as_reserved_forms(source: dict[str, Any]) -> None:
    recs = _as_02(lit.escaped(source))
    assert "blobs" not in seal_record(recs)
    assert lit.errors(recs, store=example_store()) == []
    assert lit.errors(recs) == []


def test_aer_02_values_nested_in_an_escaped_body_keep_reserved_semantics() -> None:
    store = example_store()
    digest = "sha256:" + store.put(lit.PAYLOAD)
    recs = _as_02(lit.with_args({"$lit": {"$k": {"$blob": digest, "bytes": len(lit.PAYLOAD)}}}))
    assert seal_record(recs)["blobs"] == [digest]
    assert lit.errors(recs, store=store) == []
    assert ("aer.blob.missing", "/parts/1/args/$lit/$k") in lit.errors(recs, store=example_store())


def _flooded_02() -> bytes:
    recs = _as_02(example_records())
    recs[-1]["parts"] = [{"t": "text", "text": ""} for _ in range(MAX_FINDINGS)] + recs[-1]["parts"]
    recs = cap.edit(recs, "m2", generated_by="zzz")  # dangling reference: an error in both modes
    data = b"".join(dumps_line(r) for r in [*recs, seal_record(recs)])
    load_aer_bytes(data)
    return data


@pytest.mark.parametrize("mode", ["dev", "release"])
def test_aer_02_an_error_after_the_findings_cap_fails_the_report(mode: str) -> None:
    report = cap._validate(_flooded_02(), mode)
    assert report.truncated and len(report.findings) == MAX_FINDINGS
    assert not report.ok and not report.passed
