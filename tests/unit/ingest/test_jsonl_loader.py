"""iter_jsonl / scan_jsonl (G.3.3; K.5.6 item 2): LF-only framing, 0-based line numbers, byte offsets, per-line issues."""

from __future__ import annotations

import io

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.errors import IngestError, IngestFinding
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import NO_VALUE, iter_jsonl, scan_jsonl

LIMITS = IngestLimits()


def run(data: bytes, limits: IngestLimits = LIMITS, **kw):
    issues: list[IngestFinding] = []
    rows = list(iter_jsonl(io.BytesIO(data), limits, issues=issues, **kw))
    return rows, issues


def codes(issues):
    return [i.code for i in issues]


def test_yields_line_numbers_and_byte_offsets():
    data = b'{"a":1}\n{"b":2}\n[3]\n'
    rows, issues = run(data)
    assert rows == [(0, 0, {"a": 1}), (1, 8, {"b": 2}), (2, 16, [3])]
    assert issues == []
    for _line_no, offset, _ in rows:
        assert data[offset : offset + 1] in (b"{", b"[")


def test_unicode_line_separators_stay_inside_one_record():
    separators = [chr(0x2028), chr(0x2029), chr(0x85)]
    text = "".join(f'{{"k{i}": "a{sep}b"}}\n' for i, sep in enumerate(separators))
    rows, issues = run(text.encode("utf-8"))
    assert issues == []
    assert [r[2] for r in rows] == [{f"k{i}": f"a{sep}b"} for i, sep in enumerate(separators)]
    assert [r[0] for r in rows] == [0, 1, 2]


def test_bare_cr_between_tokens_is_whitespace_within_one_line():
    rows, issues = run(b'{"a":\r1}\n{"b":2}\n')
    assert issues == []
    assert rows == [(0, 0, {"a": 1}), (1, 9, {"b": 2})]


def test_missing_final_newline_is_reported_not_silent():
    rows, issues = run(b'{"a":1}\n{"b":2}')
    assert rows == [(0, 0, {"a": 1}), (1, 8, {"b": 2})]
    assert [(i.code, i.line, i.offset) for i in issues] == [("ingest.jsonl.no_final_newline", 1, 8)]


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b'{"a":1}\r\n', "ingest.jsonl.crlf"),
        (b'\n{"a":1}\n', "ingest.jsonl.blank"),
        (b'   \n{"a":1}\n', "ingest.jsonl.blank"),
        (b'{"a":\x001}\n', "ingest.jsonl.nul"),
        (b'\xef\xbb\xbf{"a":1}\n', "ingest.json.bom"),
    ],
)
def test_strict_profile_gives_each_framing_defect_its_own_code(data, code):
    rows, issues = run(data)
    assert code in codes(issues)
    first = issues[0]
    assert first.severity == "error" and first.line == 0 and first.offset == 0
    assert all(r[0] != 0 for r in rows)  # the defective line is not yielded


def test_bad_lines_do_not_stop_the_remaining_lines():
    data = b'{"a":1}\r\n{"b":2}\n\n{"c":\n{"d":4}\n'
    rows, issues = run(data)
    assert [r[2] for r in rows] == [{"b": 2}, {"d": 4}]
    assert [(i.code, i.line) for i in issues] == [
        ("ingest.jsonl.crlf", 0),
        ("ingest.jsonl.blank", 2),
        ("ingest.json.syntax", 3),
    ]


def test_without_a_sink_the_iterator_fails_closed():
    with pytest.raises(IngestError) as info:
        list(iter_jsonl(io.BytesIO(b'{"a":1}\n\n{"b":2}\n')))
    assert info.value.code == "ingest.jsonl.blank" and info.value.line == 1 and info.value.offset == 8
    with pytest.raises(IngestError) as info:
        list(iter_jsonl(io.BytesIO(b'{"a":1}')))  # missing final newline is not silently accepted
    assert info.value.code == "ingest.jsonl.no_final_newline"


def test_lenient_profile_records_and_keeps_the_lines():
    data = b'\xef\xbb\xbf{"a":1}\r\n\n{"b":2}\n'
    rows, issues = run(data, profile="lenient")
    assert [r[2] for r in rows] == [{"a": 1}, {"b": 2}]
    assert {i.severity for i in issues} == {"warning"}
    assert set(codes(issues)) == {"ingest.json.bom", "ingest.jsonl.crlf", "ingest.jsonl.blank"}


def test_python_json_profile_accepts_nan_constants():
    rows, issues = run(b'{"x": NaN}\n', profile="python-json")
    assert rows[0][2] == {"x": {"$float": "NaN"}}
    assert codes(issues) == ["ingest.number.nonfinite"] and issues[0].line == 0


def test_strict_profile_rejects_nan_line():
    rows, issues = run(b'{"x": NaN}\n{"y":1}\n')
    assert rows == [(1, 11, {"y": 1})]
    assert codes(issues) == ["ingest.number.nonfinite"]


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_line_length_cap_probed_at_the_limit(delta):
    limits = LIMITS.replace(max_jsonl_line_bytes=64)
    body = b'"' + b"x" * (limits.max_jsonl_line_bytes - 2 + delta) + b'"'
    data = body + b"\n" + b'{"after":1}\n'
    rows, issues = run(data, limits)
    if delta > 0:
        assert codes(issues) == ["ingest.jsonl.line_too_long"]
        assert rows == [(1, len(body) + 1, {"after": 1})]  # the offset accounts for the discarded bytes
    else:
        assert issues == [] and len(rows) == 2


def test_overlong_line_without_final_newline_and_huge_line_are_bounded():
    limits = LIMITS.replace(max_jsonl_line_bytes=64)
    rows, issues = run(b'"' + b"x" * 1_000_000, limits)
    assert rows == [] and codes(issues)[0] == "ingest.jsonl.line_too_long"


def test_text_mode_streams_are_refused():
    with pytest.raises(TypeError):
        list(iter_jsonl(io.StringIO('{"a":1}\n')))  # type: ignore[arg-type]


def test_unknown_profile_is_a_programming_error():
    with pytest.raises(ValueError):
        list(iter_jsonl(io.BytesIO(b""), profile="loose"))


def test_empty_stream_yields_nothing():
    assert run(b"") == ([], [])


def test_scan_reports_every_line_including_rejected_ones():
    lines = list(scan_jsonl(io.BytesIO(b'{"a":1}\n\n[}\n')))
    assert [(n, v is NO_VALUE) for n, _, v, _ in lines] == [(0, False), (1, True), (2, True)]


@settings(max_examples=200, deadline=None)
@given(st.lists(st.binary(max_size=40), max_size=8))
def test_arbitrary_lines_never_escape_as_other_exceptions(lines):
    data = b"\n".join(lines)
    issues: list[IngestFinding] = []
    rows = list(iter_jsonl(io.BytesIO(data), LIMITS, issues=issues))
    assert all(isinstance(n, int) and isinstance(o, int) for n, o, _ in rows)
    assert all(i.code.startswith("ingest.") for i in issues)
    # determinism and monotone offsets
    assert [o for _, o, _ in rows] == sorted(o for _, o, _ in rows)
    again: list[IngestFinding] = []
    assert list(iter_jsonl(io.BytesIO(data), LIMITS, issues=again)) == rows and again == issues
