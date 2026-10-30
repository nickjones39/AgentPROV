"""JCS lines and ``$``-escapes (C.11): canonical bytes are order-independent and values survive a round trip."""

from __future__ import annotations

import json
import math
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.aer.canon import LexHints, decode_value, dumps_line, encode_value, loads_strict, utf16_order

S = settings(max_examples=300, deadline=None, derandomize=True)
SURROGATES = st.text(alphabet=st.characters(codec="utf-8", exclude_categories=()), max_size=6) | st.sampled_from(["\ud800", "a\udfffb", "\U0001f600"])
KEYS = st.one_of(st.text(max_size=5), st.sampled_from(["$int", "$lit", "$blob", "b", "a", "｝", "\U0001f600"]))
VALUES = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(-(2**80), 2**80),
        st.floats(allow_nan=True, allow_infinity=True),
        st.sampled_from([0.0, -0.0, 1.0, 2.0**53, 1e20, 1e21, 1e300, 5e-324]),
        SURROGATES,
    ),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(KEYS, children, max_size=4),
    max_leaves=8,
)


def same(a: Any, b: Any) -> bool:
    """Equality that tells 1 from 1.0, -0.0 from 0.0 and respects NaN, and compares member order."""
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or (a == b and math.copysign(1, a) == math.copysign(1, b))
    return type(a) is type(b) and a == b


@S
@given(VALUES)
def test_encode_dumps_loads_decode_roundtrip(value: Any) -> None:
    lex = LexHints()
    encoded = encode_value(value, at="/v", lex=lex)
    record = {"v": encoded, "ext": {"lex": lex.as_dict()}} if lex else {"v": encoded}
    line = dumps_line(record)
    parsed = loads_strict(line[:-1])
    assert dumps_line(parsed) == line  # canonical form is a fixed point
    hints = LexHints.from_dict(parsed["ext"]["lex"]) if "ext" in parsed else None
    assert same(decode_value(parsed["v"], at="/v", lex=hints), value)


@S
@given(st.dictionaries(st.text(max_size=5), st.integers(-100, 100), max_size=6), st.randoms(use_true_random=False))
def test_dumps_line_is_independent_of_insertion_order(obj: dict[str, int], rnd: Any) -> None:
    keys = list(obj)
    rnd.shuffle(keys)
    shuffled = {k: obj[k] for k in keys}
    assert dumps_line(obj) == dumps_line(shuffled)
    assert list(json.loads(dumps_line(obj))) == utf16_order(list(obj))


@S
@given(VALUES)
def test_encoded_values_are_always_representable(value: Any) -> None:
    dumps_line({"v": encode_value(value, at="/v", lex=LexHints())})  # never raises: every source value has an encoding
