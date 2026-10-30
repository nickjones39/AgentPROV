"""K.11.1 JSONL fuzzing (SEC-03): framing mutations never raise, never lose a good line, and are deterministic.

Mutations are JSONL-specific: split or merge lines, CRLF, bare CR, BOM, NUL, over-long lines, a truncated tail, and
the byte mutations of ``fuzz_support``. Every issue carries a G.3.9 code and a line locator.
"""

from __future__ import annotations

import io
import json

from fuzz_support import budget, byte_mutations
from hypothesis import given
from hypothesis import strategies as st

from agentprov.errors import INGEST_CODES
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl

LIMITS = IngestLimits().replace(max_jsonl_line_bytes=256)
GOOD = [json.dumps({"i": i, "s": "x" * (i % 7), "u": "\u00e9"}, ensure_ascii=False).encode() for i in range(5)]

line = st.one_of(
    st.sampled_from(GOOD),
    byte_mutations(GOOD[1], max_ops=3),
    st.sampled_from([b"", b" ", b"\t", b"\xef\xbb\xbf" + GOOD[0], GOOD[2] + b"\r", b"\x00", b"{", b"]", b"null",
                     b'{"a":1,"a":2}', b'{"n": NaN}', b'{"n": 1e999}', b'"\\ud800"', b"\xff\xfe", b'{"s":"a\rb"}',
                     b'{"s":"\xe2\x80\xa8"}', b"x" * 300]),
)


def run(data: bytes) -> tuple[list[tuple[int, object]], list[tuple[str, int | None]]]:
    issues: list = []
    rows = [(n, value) for n, _offset, value in iter_jsonl(io.BytesIO(data), LIMITS, issues=issues)]
    return rows, [(i.code, i.line) for i in issues]


@budget(150)
@given(st.lists(line, max_size=8), st.sampled_from([b"\n", b"\r\n"]), st.booleans())
def test_jsonl_framing_is_total_typed_and_deterministic(lines: list[bytes], sep: bytes, final_lf: bool) -> None:
    data = sep.join(lines) + (sep if final_lf and lines else b"")
    first = run(data)
    assert first == run(data)  # F-5
    rows, issues = first
    assert all(code in INGEST_CODES for code, _ in issues)  # F-1
    assert all(isinstance(n, int) and n >= 0 for n, _ in rows)
    assert len({n for n, _ in rows}) == len(rows)  # one record per line at most


@budget(150)
@given(st.lists(line, min_size=1, max_size=6), st.integers(0, 6))
def test_a_damaged_line_never_costs_a_good_one(noise: list[bytes], at: int) -> None:
    """Good records keep their line numbers and values whatever surrounds them (D.2.8: other lines still mapped)."""
    body = list(GOOD)
    position = at % (len(body) + 1)
    body[position:position] = [n.replace(b"\n", b" ") for n in noise]
    rows, _ = run(b"\n".join(body) + b"\n")
    got = dict(rows)
    for index, good in enumerate(body):
        if good in GOOD:
            assert got[index] == json.loads(good)


@budget(100)
@given(byte_mutations(b"\n".join(GOOD) + b"\n", max_ops=8))
def test_byte_mutations_of_a_whole_file(data: bytes) -> None:
    rows, issues = run(data)
    assert (rows, issues) == run(data)
    assert all(code in INGEST_CODES for code, _ in issues)
