"""strict_json_loads (G.3.3; K.5.6 item 1). Limits come from IngestLimits and are probed at limit-1, limit, limit+1."""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.errors import IngestError, IngestFinding
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

LIMITS = IngestLimits()


def code_of(data: bytes, limits: IngestLimits = LIMITS, **kw) -> str:
    with pytest.raises(IngestError) as info:
        strict_json_loads(data, limits, **kw)
    return info.value.code


def nested(depth: int, leaf: bytes = b"1") -> bytes:
    return b"[" * depth + leaf + b"]" * depth


def test_parses_ordinary_documents():
    assert strict_json_loads(b' {"a": [1, 2.5, "x", null, true], "b": {}} \n') == {
        "a": [1, 2.5, "x", None, True],
        "b": {},
    }
    assert strict_json_loads(b"3") == 3
    assert strict_json_loads(b'"s"') == "s"


def test_str_input_is_refused_not_decoded():
    with pytest.raises(TypeError):
        strict_json_loads("{}")  # type: ignore[arg-type]


def test_unknown_profile_is_a_programming_error():
    with pytest.raises(ValueError):
        strict_json_loads(b"{}", profile="loose")


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_document_size_cap(delta):
    limits = LIMITS.replace(max_json_bytes=64)
    data = b'"' + b"x" * (limits.max_json_bytes - 2 + delta) + b'"'
    if delta > 0:
        assert code_of(data, limits) == "ingest.size.file"
    else:
        assert strict_json_loads(data, limits)


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_record_size_cap_uses_the_record_code(delta):
    limits = LIMITS.replace(max_jsonl_line_bytes=64)
    data = b'"' + b"x" * (limits.max_jsonl_line_bytes - 2 + delta) + b'"'
    if delta > 0:
        assert code_of(data, limits, record=True) == "ingest.size.record"
    else:
        assert strict_json_loads(data, limits, record=True)


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_depth_cap_at_default(delta):
    depth = LIMITS.max_json_depth + delta
    if delta > 0:
        assert code_of(nested(depth)) == "ingest.json.depth"
    else:
        assert strict_json_loads(nested(depth)) is not None


def test_depth_counts_objects_and_mixed_nesting():
    limit = LIMITS.max_json_depth

    def mixed(objects: int) -> bytes:
        arrays = limit - limit // 2
        return b'{"a":' * objects + b"[" * arrays + b"0" + b"]" * arrays + b"}" * objects

    assert strict_json_loads(mixed(limit // 2)) is not None
    assert code_of(mixed(limit // 2 + 1)) == "ingest.json.depth"


def test_brackets_inside_strings_do_not_count():
    hostile = '"' + "[" * 10_000 + '\\"' + "{" * 10_000 + '"'
    assert strict_json_loads(hostile.encode()) == "[" * 10_000 + '"' + "{" * 10_000


def test_escaped_backslash_before_quote_ends_the_string():
    # The string "\\" closes; the brackets after it are structure and exceed the cap.
    depth = LIMITS.max_json_depth
    data = b'["\\\\",' + b"[" * depth + b"0" + b"]" * depth + b"]"
    assert code_of(data) == "ingest.json.depth"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_integer_digit_cap_at_default(delta):
    digits = LIMITS.max_int_digits + delta
    data = b"1" + b"0" * (digits - 1)
    if delta > 0:
        assert code_of(data) == "ingest.number.digits"
        assert code_of(b"-" + data) == "ingest.number.digits"
    else:
        assert strict_json_loads(data) == 10 ** (digits - 1)


def test_huge_integer_gives_the_typed_code_before_python_does():
    assert code_of(b"1" * 1_000_000) == "ingest.number.digits"


@pytest.mark.parametrize("literal", [b"1e400", b"-1e400", b"1E999999999999"])
def test_overflowing_floats_are_rejected(literal):
    assert code_of(literal) == "ingest.number.nonfinite"
    assert code_of(b"[" + literal + b"]") == "ingest.number.nonfinite"


def test_large_finite_floats_pass():
    assert strict_json_loads(b"1e308") == 1e308


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonfinite_constants_rejected_under_strict(literal):
    assert code_of(literal) == "ingest.number.nonfinite"
    assert code_of(b'{"x": [' + literal + b"]}") == "ingest.number.nonfinite"


def test_python_json_profile_maps_constants_and_records_a_finding():
    findings: list[IngestFinding] = []
    value = strict_json_loads(b"[NaN, Infinity, -Infinity, 1]", profile="python-json", findings=findings)
    assert value == [{"$float": "NaN"}, {"$float": "Infinity"}, {"$float": "-Infinity"}, 1]
    assert [f.code for f in findings] == ["ingest.number.nonfinite"]
    # an overflowing literal is still rejected in that profile
    assert code_of(b"1e400", profile="python-json") == "ingest.number.nonfinite"


@pytest.mark.parametrize("data", [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":1}}', b'[{"x":{"y":[{"k":1,"k":2}]}}]'])
def test_duplicate_keys_at_any_depth(data):
    assert code_of(data) == "ingest.json.duplicate_key"


def test_same_key_in_different_objects_is_fine():
    assert strict_json_loads(b'[{"a":1},{"a":2},{"b":{"a":3}}]') == [{"a": 1}, {"a": 2}, {"b": {"a": 3}}]


def test_bom_rejected_and_lenient_profile_records():
    assert code_of(b'\xef\xbb\xbf{"a":1}') == "ingest.json.bom"
    findings: list[IngestFinding] = []
    assert strict_json_loads(b'\xef\xbb\xbf{"a":1}', profile="lenient-bom", findings=findings) == {"a": 1}
    assert [f.code for f in findings] == ["ingest.json.bom"]


def test_syntax_errors_carry_the_offset():
    with pytest.raises(IngestError) as info:
        strict_json_loads(b'{"a": }')
    assert info.value.code == "ingest.json.syntax" and info.value.offset == 6
    for bad in (b"", b"{", b"[1,]", b"{'a':1}", b"01", b'"\n"', b"1 2", b"tru"):
        assert code_of(bad) == "ingest.json.syntax"


def test_escaped_lone_surrogate_is_a_finding_not_a_rejection():
    findings: list[IngestFinding] = []
    value = strict_json_loads(b'["\\ud800", "ok", {"\\udc00": 1}]', findings=findings)
    assert value[0] == chr(0xD800)
    assert [(f.code, f.severity) for f in findings] == [("ingest.json.lone_surrogate", "info")]
    findings.clear()
    assert strict_json_loads(b'"\\ud83d\\ude00"', findings=findings) == chr(0x1F600)  # a valid pair
    assert findings == []


def test_error_messages_never_contain_source_text():
    marker = "ZZ-MARK-" + "q" * 20
    for data in (
        f'{{"{marker}": 1, "{marker}": 2}}'.encode(),
        f'["{marker}", NaN]'.encode(),
        f'{{"{marker}": }}'.encode(),
    ):
        with pytest.raises(IngestError) as info:
            strict_json_loads(data)
        assert marker not in str(info.value)


JSON_LEAVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**18), max_value=10**18),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)
JSON_VALUES = st.recursive(
    JSON_LEAVES,
    lambda children: st.one_of(
        st.lists(children, max_size=4), st.dictionaries(st.text(max_size=6), children, max_size=4)
    ),
    max_leaves=25,
)


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(JSON_VALUES)
def test_round_trip_of_json_dumps(value):
    try:
        text = json.dumps(value, ensure_ascii=False).encode("utf-8").decode("utf-8")
    except UnicodeEncodeError:
        return  # lone surrogates written raw are not valid UTF-8: covered by test_encoding
    assert strict_json_loads(text.encode()) == json.loads(text)


@settings(max_examples=300, deadline=None)
@given(st.binary(max_size=2048))
def test_arbitrary_bytes_give_a_value_or_an_ingest_error(data):
    def run():
        try:
            return ("ok", strict_json_loads(data))
        except IngestError as exc:
            return ("err", exc.code)

    first = run()
    assert first == run()  # deterministic
    if first[0] == "err":
        assert first[1].startswith(("ingest.json.", "ingest.number."))


@pytest.mark.parametrize(
    ("data", "profile", "prescan", "walk"),
    [
        (b"[" * 256 + b"]" * 256, "strict", False, False),  # k = max: both skipped
        (b"[" * 257 + b"]" * 257, "strict", True, False),  # k = max + 1: the prescan runs and rejects before parsing
        (b'["' + b"[" * 300 + b'"]', "strict", True, True),  # k over max from string bytes: both run (the bound is k)
        (b"[" * 255 + b"NaN" + b"]" * 255, "python-json", False, False),  # k + $float level = max: skipped
        (b"[" * 256 + b"NaN" + b"]" * 256, "python-json", False, True),  # k = max but the $float level makes max + 1
        (b'["\\ud800"]', "strict", False, True),  # a lone-surrogate escape: the walk counts it
    ],
)
def test_depth_checks_are_skipped_exactly_when_the_byte_count_bounds_them(monkeypatch, data, profile, prescan, walk):
    """D-412: the prescan runs iff the count k of '[' and '{' bytes exceeds max_json_depth; the walk runs iff it may
    raise (k plus one level for a mapped python-json constant exceeds the limit) or must count lone surrogates."""
    from agentprov.ingest import loaders

    called: list[str] = []
    real_prescan, real_walk = loaders._prescan_depth, loaders._walk

    def spy_prescan(*args, **kwargs):
        called.append("prescan")
        return real_prescan(*args, **kwargs)

    def spy_walk(*args, **kwargs):
        called.append("walk")
        return real_walk(*args, **kwargs)

    monkeypatch.setattr(loaders, "_prescan_depth", spy_prescan)
    monkeypatch.setattr(loaders, "_walk", spy_walk)
    try:
        strict_json_loads(data, profile=profile)
    except IngestError as exc:
        assert exc.code == "ingest.json.depth"
    assert ("prescan" in called) is prescan
    assert ("walk" in called) is walk
