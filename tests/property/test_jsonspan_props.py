"""D-222: reading a string by its byte span changes nothing observable.

For generated documents (nested objects and arrays, strings with escapes, brackets, quotes and non-ASCII text, several
serialisations), every string-valued pointer is read by :func:`string_value_at` as a whole parse resolves it. For
corrupted documents, it never returns a value a whole parse would not give: either the same string or ``None``. And a
carve with the span path forced on (``span_min=0``) gives the same bytes, or the same error, as with it off.
"""

from __future__ import annotations

import json
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.errors import AgentProvError
from agentprov.ingest.jsonspan import string_value_at
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.raw.carve import carve

S = settings(max_examples=400, deadline=None, derandomize=True)
LIMITS = IngestLimits(max_json_depth=12)

TEXT = st.text(alphabet=st.sampled_from(list('ab"\\/[]{},: \n\té€\U0001f600~')), max_size=12)
KEYS = st.text(alphabet=st.sampled_from(list('ab"\\/~[]{},: é')), max_size=6)
SCALARS = st.one_of(st.none(), st.booleans(), st.integers(-10**6, 10**6), st.floats(allow_nan=False, allow_infinity=False),
                    TEXT)
VALUES = st.recursive(SCALARS, lambda inner: st.one_of(st.lists(inner, max_size=4),
                                                        st.dictionaries(KEYS, inner, max_size=4)), max_leaves=24)


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _string_pointers(value: Any, at: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(at, value)]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _string_pointers(v, f"{at}/{_escape(k)}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _string_pointers(v, f"{at}/{i}")]
    return []


def _serialise(value: Any, style: int) -> bytes:
    if style == 0:
        return json.dumps(value).encode()
    if style == 1:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return json.dumps(value, ensure_ascii=False, indent=1).encode()


def _whole(data: bytes, pointer: str) -> Any:
    """The value a whole strict parse resolves at ``pointer``, or ``None`` when the parse or the pointer fails."""
    try:
        current = strict_json_loads(data, LIMITS)
    except AgentProvError:
        return None
    for raw in pointer[1:].split("/") if pointer else ():
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return None
    return current


@S
@given(VALUES, st.integers(0, 2))
def test_every_string_is_read_as_a_whole_parse_reads_it(value, style):
    data = _serialise(value, style)
    for pointer, expected in _string_pointers(value):
        assert string_value_at(data, pointer, LIMITS) == expected


@S
@given(VALUES, st.integers(0, 2), st.data())
def test_a_corrupted_document_never_yields_a_value_a_whole_parse_would_not(value, style, data):
    raw = bytearray(_serialise(value, style))
    pointers = _string_pointers(value) or [("", "")]
    for _ in range(data.draw(st.integers(1, 3))):
        if not raw:
            break
        at = data.draw(st.integers(0, len(raw) - 1))
        action = data.draw(st.sampled_from(["flip", "drop", "insert"]))
        if action == "flip":
            raw[at] = data.draw(st.sampled_from(list(b'"\\[]{},:x0 \xff\x01')))
        elif action == "drop":
            del raw[at]
        else:
            raw.insert(at, data.draw(st.sampled_from(list(b'"\\[]{},:x'))))
    corrupted = bytes(raw)
    for pointer, _expected in pointers:
        got = string_value_at(corrupted, pointer, LIMITS)
        if got is not None:
            assert got == _whole(corrupted, pointer)


@S
@given(VALUES, st.integers(0, 2), st.sampled_from(["utf8", "base64"]))
def test_a_carve_by_span_equals_a_carve_by_whole_parse(value, style, transform):
    data = _serialise(value, style)
    for pointer, _expected in _string_pointers(value) or [("/missing", "")]:
        outcomes = []
        for span_min in (0, 1 << 40):
            try:
                outcomes.append(carve(data, {"p": pointer}, transform, LIMITS, span_min=span_min))
            except AgentProvError as exc:
                outcomes.append((type(exc).__name__, exc.code, str(exc)))
        assert outcomes[0] == outcomes[1]
