"""D-412: the strict loader's depth fast path changes nothing observable.

``strict_json_loads`` skips the depth prescan when the count k of ``[`` and ``{`` bytes is at most ``max_json_depth``, and
the depth walk when, in addition, no ``python-json`` constant was mapped to a ``{"$float": ...}`` dict (one level from no
bracket byte) and no lone-surrogate escape forces the walk. For generated documents near the depth limit, every profile
gives the same value, the same findings and the same error code with the fast path as with the unconditional checks
(``loaders._DEPTH_FAST_PATH = False``).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.errors import IngestError
from agentprov.ingest import loaders
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import JSON_PROFILES, strict_json_loads

S = settings(max_examples=400, deadline=None, derandomize=True)

#: Leaves chosen to stress the bound: strings full of brackets and escaped quotes (counted in k, never structural), an
#: escaped bracket, lone-surrogate escapes, python-json constants and plain scalars.
LEAVES = st.sampled_from([
    '"[[{{"', '"\\"[{"', '"\\u005b\\u007b"', '"]}]}"', '"\\ud800"', '"x\\udfff["', '"é["', "NaN", "Infinity",
    "-Infinity", "0", "-0.0", "1e400", "true", "null", '""',
])  # fmt: skip
CONSTANTS = st.sampled_from(["NaN", "Infinity", "-Infinity"])


@st.composite
def documents(draw: Any) -> tuple[bytes, int]:
    """A document nested to a depth near a small limit, sometimes corrupted, and the limit."""
    limit = draw(st.integers(4, 10))
    depth = draw(st.integers(max(0, limit - 2), limit + 1))
    opens = draw(st.lists(st.sampled_from("[{"), min_size=depth, max_size=depth))
    plain = draw(st.booleans())  # no sibling leaves: k is exactly the nesting depth, the case the bound is tight on
    text = draw(st.one_of(CONSTANTS, LEAVES))
    for opener in reversed(opens):
        extra = [] if plain else draw(st.lists(LEAVES, max_size=2))
        if opener == "[":
            text = "[" + ",".join([text, *extra]) + "]"
        else:
            text = "{" + ",".join(f'"k{i}":{v}' for i, v in enumerate([text, *extra])) + "}"
    data = text.encode("utf-8")
    corruption = draw(st.sampled_from(["none", "none", "none", "truncate", "stray_closer", "unterminated", "bom"]))
    if corruption == "truncate" and len(data) > 1:
        data = data[: draw(st.integers(1, len(data) - 1))]
    elif corruption == "stray_closer":
        data += b"]"
    elif corruption == "unterminated":
        data = b'["' + data
    elif corruption == "bom":
        data = b"\xef\xbb\xbf" + data
    return data, limit


def outcome(data: bytes, limits: IngestLimits, profile: str) -> tuple[Any, ...]:
    findings: list[Any] = []
    try:
        value = strict_json_loads(data, limits, profile=profile, findings=findings)
    except IngestError as exc:
        return ("error", exc.code)
    return ("ok", json.dumps(value, sort_keys=False, ensure_ascii=True), [(f.code, f.severity, f.detail) for f in findings])


@S
@given(documents(), st.sampled_from(JSON_PROFILES))
def test_fast_path_is_observationally_identical(doc: tuple[bytes, int], profile: str) -> None:
    data, limit = doc
    limits = IngestLimits(max_json_depth=limit)
    fast = outcome(data, limits, profile)
    try:
        loaders._DEPTH_FAST_PATH = False
        full = outcome(data, limits, profile)
    finally:
        loaders._DEPTH_FAST_PATH = True
    assert fast == full


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity"])
@pytest.mark.parametrize("depth", [255, 256])
def test_python_json_constant_at_the_depth_limit(constant: bytes, depth: int) -> None:
    """The deferrals review case: k = depth bracket bytes, plus the one-level ``$float`` dict of a mapped constant."""
    data = b"[" * depth + constant + b"]" * depth
    if depth == 256:  # k = 256 = max, but the parsed depth is 257: still rejected
        with pytest.raises(IngestError) as info:
            strict_json_loads(data, profile="python-json")
        assert info.value.code == "ingest.json.depth"
    else:
        value = strict_json_loads(data, profile="python-json")
        for _ in range(depth):
            value = value[0]
        assert value == {"$float": constant.decode()}
