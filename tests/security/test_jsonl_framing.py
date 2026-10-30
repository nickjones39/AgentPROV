"""SEC-03 (K.12.3, K.5.6 item 2): JSONL framing codes, per-line issues with locators, other lines still mapped."""

from __future__ import annotations

import io

from agentprov.errors import IngestFinding
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl

LIMITS = IngestLimits()


def run(data: bytes, limits: IngestLimits = LIMITS, **kw):
    issues: list[IngestFinding] = []
    return list(iter_jsonl(io.BytesIO(data), limits, issues=issues, **kw)), issues


def test_sec03_u2028_u0085_and_u2029_inside_a_record_stay_one_line():
    for cp in (0x2028, 0x2029, 0x85):
        record = ('{"s": "x' + chr(cp) + 'y"}').encode("utf-8")
        rows, issues = run(record + b"\n" + record + b"\n")
        assert issues == [] and len(rows) == 2 and [r[0] for r in rows] == [0, 1]


def test_sec03_each_defect_has_its_own_distinct_code_and_locator():
    lines = [
        b'{"ok":0}\n',
        b'{"cr":1}\r\n',
        b"\n",
        b'{"nul":\x002}\n',
        b'{"long":"' + b"x" * (LIMITS.replace(max_jsonl_line_bytes=40).max_jsonl_line_bytes) + b'"}\n',
        b'{"ok":5}\n',
        b'{"last":6}',
    ]
    limits = LIMITS.replace(max_jsonl_line_bytes=40)
    data = b"".join(lines)
    rows, issues = run(data, limits)
    assert [r[2] for r in rows] == [{"ok": 0}, {"ok": 5}, {"last": 6}]  # the good lines are still mapped
    got = [(i.code, i.line) for i in issues]
    assert got == [
        ("ingest.jsonl.crlf", 1),
        ("ingest.jsonl.blank", 2),
        ("ingest.jsonl.nul", 3),
        ("ingest.jsonl.line_too_long", 4),
        ("ingest.jsonl.no_final_newline", 6),
    ]
    # the locator is the byte offset of the start of the line
    for issue in issues:
        assert data[issue.offset : issue.offset + 1] == lines[issue.line][:1]
    assert len({code for code, _ in got}) == len(got)


def test_sec03_bom_on_the_first_line_only():
    rows, issues = run(b'\xef\xbb\xbf{"a":1}\n{"b":2}\n')
    assert [(i.code, i.line) for i in issues] == [("ingest.json.bom", 0)]
    assert rows == [(1, 11, {"b": 2})]
    rows, issues = run(b'{"a":1}\n\xef\xbb\xbf{"b":2}\n')
    assert [(i.code, i.line) for i in issues] == [("ingest.json.bom", 1)]  # a BOM mid-stream is a syntax-level defect


def test_sec03_a_line_made_only_of_whitespace_is_blank_not_a_record():
    rows, issues = run(b' \t \n{"a":1}\n')
    assert [(i.code, i.line) for i in issues] == [("ingest.jsonl.blank", 0)]


def test_sec03_overlong_line_is_discarded_in_bounded_chunks_and_framing_resumes():
    limits = LIMITS.replace(max_jsonl_line_bytes=100)
    huge = b'{"x":"' + b"y" * 5_000_000 + b'"}\n'
    rows, issues = run(huge + b'{"next":1}\n' + huge + b'{"last":2}\n', limits)
    assert [r[2] for r in rows] == [{"next": 1}, {"last": 2}]
    assert [(i.code, i.line) for i in issues] == [("ingest.jsonl.line_too_long",) * 1 + (0,), ("ingest.jsonl.line_too_long", 2)]


def test_sec03_strict_numbers_apply_per_line():
    rows, issues = run(b'{"a":NaN}\n{"b":1e400}\n{"c":' + b"7" * 2000 + b"}\n" + b'{"ok":1}\n')
    assert [r[2] for r in rows] == [{"ok": 1}]
    assert [i.code for i in issues] == ["ingest.number.nonfinite", "ingest.number.nonfinite", "ingest.number.digits"]


def test_sec03_a_bare_cr_never_splits_a_record():
    """Text-mode reading would split at a bare CR; binary LF framing keeps one line. Between tokens it is JSON
    whitespace; inside a string it is an unescaped control character, so that one line is an issue and the others
    are still mapped."""
    rows, issues = run(b'{"a":\r1}\n{"b": 2}\n')
    assert issues == [] and [r[2] for r in rows] == [{"a": 1}, {"b": 2}]
    rows, issues = run(b'{"ok": 0}\n{"s": "x\ry"}\n{"ok": 2}\n')
    assert [r[2] for r in rows] == [{"ok": 0}, {"ok": 2}] and [r[0] for r in rows] == [0, 2]
    assert len(issues) == 1 and issues[0].line == 1 and issues[0].code.startswith("ingest.")


def test_sec03_line_cap_probed_at_the_limit():
    limits = LIMITS.replace(max_jsonl_line_bytes=64)
    for delta, ok in ((-1, True), (0, True), (1, False)):
        body = b'{"x":"' + b"a" * (64 + delta - 8) + b'"}'
        rows, issues = run(body + b"\n" + b'{"after":1}\n', limits)
        assert len(body) == 64 + delta
        assert (len(rows) == 2) is ok and rows[-1][2] == {"after": 1}
        assert (issues == []) is ok
