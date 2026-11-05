"""Pieces of the examination-2 tools (``tools/analysis2/``), on synthetic rows only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools" / "analysis2"


@pytest.fixture(scope="module")
def detsum():
    sys.path.insert(0, str(TOOLS))
    try:
        import exam2_detsum

        yield exam2_detsum
    finally:
        sys.path.remove(str(TOOLS))


@pytest.fixture(scope="module")
def exam2():
    sys.path.insert(0, str(TOOLS))
    try:
        import exam2_lib
        import exam2_scan

        yield exam2_lib, exam2_scan
    finally:
        sys.path.remove(str(TOOLS))


def test_x01_rejects_an_escaped_lone_surrogate_and_keeps_pairs(exam2) -> None:
    """AU-TRS-5: json.loads decodes '\\ud800' silently, so strict_parse accepted what its docstring says it rejects."""
    lib, _ = exam2
    from collections import Counter

    for line in (b'{"t":"a\\ud800b"}', b'{"a\\udfffb":1}', b'[["x",{"y":"\\uDC00"}]]'):
        with pytest.raises(lib.StrictError) as exc:
            lib.strict_parse(line, Counter())
        assert exc.value.code == "lone_surrogate"
    assert lib.strict_parse(b'{"t":"\\ud83d\\ude00"}', Counter()) == {"t": "\U0001f600"}
    assert lib.strict_parse(b'{"t":"\\\\ud800"}', Counter()) == {"t": "\\ud800"}  # an escaped backslash, no surrogate


def test_u02_decoded_surrogate_pattern_is_gated_by_a_byte_prefilter(exam2) -> None:
    """AU-TRS-5: P['SURROGATE'] was in no prefilter group, so the decoded walk never applied it."""
    _, scan = exam2
    line = b'{"k":"message","parts":[{"t":"text","text":"a\\ud800b"}]}'
    acc = scan.Acc("ex_x")
    active = scan.byte_checks(acc, "aer", line)
    assert "SURROGATE" in active
    scan.walk_strings(acc, "aer", json.loads(line), ["message:"], active)
    assert sum(v for k, v in acc.hits.items() if str(k).startswith("SURROGATE|")) == 1


def test_detsum_counts_an_execution_failing_in_either_sem_or_prov(detsum, tmp_path, monkeypatch, capsys) -> None:
    """AU-TRS-6: k_fail was n - min(sem_equal, prov_equal), so a SEM-only and a PROV-only failure counted once."""
    rows = [("ex_1", False, True), ("ex_2", True, False), ("ex_3", True, True), ("ex_4", True, True)]
    (tmp_path / "c0_baseline.0.jsonl").write_text("".join(
        json.dumps({"corpus": "c", "ex": ex, "sem": {"p@1": {"equal": sem, "sha": "a"}}, "prov": {"equal": prov, "sha": "b"}})
        + "\n" for ex, sem, prov in rows), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["exam2_detsum.py", str(tmp_path)])
    assert detsum.main() == 0
    summary = json.loads(capsys.readouterr().out)["configs"]["c0_baseline"]
    assert summary["mismatching_ex"] == ["ex_1", "ex_2"]
    assert summary["wilson95"] == [round(x, 5) for x in detsum.wilson(2, 4)]
    assert summary["upper95_if_zero"] is None
