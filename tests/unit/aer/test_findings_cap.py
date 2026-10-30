"""Regen item 61 (CA-2): the ``MAX_FINDINGS`` cap never hides an error finding.

In dev mode the release-only checks report warnings. A file with ``MAX_FINDINGS`` such warnings fills the findings list,
so later errors are not stored; ``ValidationReport.ok`` must still be False (``dropped_errors`` counts them). Warnings
past the cap are dropped without a count, and a report with nothing dropped is unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest
from aer_support import edit, example_records, example_store, make_registry, seal_record

from agentprov.aer.canon import dumps_line
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.validate import MAX_FINDINGS, AerValidator, ValidationReport


def _flooded(*, error_after: bool, extra: int = 0) -> bytes:
    """``MAX_FINDINGS + extra`` empty assistant text parts (release-only ``aer.sentinel``), then two errors if asked."""
    recs = example_records()
    m3 = recs[-1]
    assert m3["id"] == "m3" and m3["role"] == "assistant"
    m3["parts"] = [{"t": "text", "text": ""} for _ in range(MAX_FINDINGS + extra)] + m3["parts"]
    seal: dict[str, Any]
    if error_after:
        recs = edit(recs, "m2", generated_by="zzz")  # dangling reference: an error in both modes
        seal = seal_record(recs)
        seal["accounting"]["status"] = "consistent"  # forged accounting status: an error in both modes
    else:
        seal = seal_record(recs)
    data = b"".join(dumps_line(r) for r in [*recs, seal])
    load_aer_bytes(data)  # count and digest are right: the reader accepts the file
    return data


def _validate(data: bytes, mode: str) -> ValidationReport:
    v = AerValidator(store=example_store(), catalogues=make_registry(), mode=mode)  # type: ignore[arg-type]
    for line in data.splitlines(keepends=True):
        v.feed(line)
    return v.finish()


@pytest.mark.parametrize("mode", ["dev", "release"])
def test_error_after_the_cap_fails_the_report(mode: str) -> None:
    report = _validate(_flooded(error_after=True), mode)
    assert report.truncated and len(report.findings) == MAX_FINDINGS
    assert not report.ok, f"{mode}: errors dropped by the findings cap, report.ok is True"
    assert not report.passed


def test_dev_counts_the_dropped_errors() -> None:
    report = _validate(_flooded(error_after=True), "dev")
    assert report.errors == () and report.dropped_errors >= 2


def test_dropped_warnings_alone_do_not_fail() -> None:
    report = _validate(_flooded(error_after=False, extra=5), "dev")
    assert report.truncated and report.dropped_errors == 0
    assert report.errors == () and report.ok


def test_nothing_dropped_leaves_the_report_as_before() -> None:
    report = _validate(_flooded(error_after=False), "dev")
    assert not report.truncated and report.dropped_errors == 0 and report.ok


def test_release_mode_is_unchanged() -> None:
    report = _validate(_flooded(error_after=False, extra=5), "release")
    assert report.truncated and len(report.errors) == MAX_FINDINGS
    assert not report.ok and not report.passed
