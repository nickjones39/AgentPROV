"""yamlsafe.safe_load (G.3.7; K.5.6 item 4). Bombs: tests/security/test_yaml_bombs.py."""

from __future__ import annotations

import io

import pytest
import yaml

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.yamlsafe import YAMLError, safe_load

LIMITS = IngestLimits()

SAME_AS_YAML_SAFE_LOAD = [
    "a: 1\nb: [x, y]\nc: {d: 2.5}",
    "- 1\n- two\n- null\n- true",
    "key: NO\nother: 12:30:00\nmode: 0755",  # YAML 1.1 implicit typing is kept (strings stay the caller's concern)
    "text: |\n  multi\n  line\n",
    "'quoted': \"double\"",
    "",
    "plain scalar",
    "anchor_without_alias: &x [1, 2]",
]


@pytest.mark.parametrize("doc", SAME_AS_YAML_SAFE_LOAD)
def test_values_equal_yaml_safe_load(doc):
    assert safe_load(doc) == yaml.safe_load(doc)


def test_accepts_bytes_and_streams():
    assert safe_load(b"a: 1") == {"a": 1}
    assert safe_load(io.StringIO("a: 1")) == {"a": 1}
    assert safe_load(io.BytesIO(b"a: 1")) == {"a": 1}


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_size_cap(delta):
    limits = LIMITS.replace(max_yaml_bytes=64)
    doc = "k: " + "x" * (limits.max_yaml_bytes - 3 + delta)
    if delta > 0:
        with pytest.raises(IngestError) as info:
            safe_load(doc, limits)
        assert info.value.code == "ingest.size.record"
    else:
        assert safe_load(doc, limits)["k"]


def test_alias_is_rejected_with_the_closed_code():
    with pytest.raises(IngestError) as info:
        safe_load("a: &x [1]\nb: *x")
    assert info.value.code == "ingest.yaml.alias"


def test_duplicate_keys_are_rejected():
    with pytest.raises(YAMLError):
        safe_load("a: 1\na: 2")


def test_syntax_errors_and_bad_utf8_are_yaml_errors():
    with pytest.raises(YAMLError):
        safe_load("a: [1, 2")
    with pytest.raises(YAMLError):
        safe_load(b"a: \xff\xfe")


def test_python_tags_are_never_constructed():
    with pytest.raises(YAMLError):
        safe_load("!!python/object/apply:os.system ['true']")


@pytest.mark.parametrize("doc", ["2001-13-45", "a: 2001-02-30 10:00:00", "!!int 'x'", "!!timestamp 'zz'"])
def test_unconstructible_scalars_are_yaml_errors_not_raw_value_errors(doc):
    with pytest.raises(YAMLError):
        safe_load(doc)


def _sexagesimal(chars: int) -> str:
    """A base-60 int scalar of exactly ``chars`` characters (``1`` then ``:59`` parts, padded with a final ``:5``)."""
    text = "1" + ":59" * ((chars - 1) // 3)
    return text + (":5" if chars - len(text) == 2 else "") if len(text) < chars else text


def test_a_long_sexagesimal_int_is_refused_before_construction() -> None:
    """Pre-round review D #4: PyYAML builds a base-60 int in quadratic time (about 50 s for 1 MiB within max_yaml_bytes).
    Up to MAX_SEXAGESIMAL_CHARS it is constructed as before; one more character is a YAMLError (the marker falls back)."""
    from agentprov.ingest.yamlsafe import MAX_SEXAGESIMAL_CHARS, YAMLError, safe_load

    at_limit = _sexagesimal(MAX_SEXAGESIMAL_CHARS)
    assert len(at_limit) == MAX_SEXAGESIMAL_CHARS and isinstance(safe_load(at_limit), int)
    over = "1" + at_limit  # still base-60: the first part becomes 11
    assert len(over) == MAX_SEXAGESIMAL_CHARS + 1
    with pytest.raises(YAMLError):
        safe_load(over)
    with pytest.raises(YAMLError):
        safe_load("a: x\nb: !!int " + over)
    with pytest.raises(YAMLError):
        safe_load("a: x\nb: " + "1" + ":59" * 340_000)  # the review's 1 MiB tool output


def test_short_times_and_quoted_or_str_tagged_long_scalars_are_unchanged() -> None:
    from agentprov.ingest.yamlsafe import MAX_SEXAGESIMAL_CHARS, safe_load

    assert safe_load("t: 1:30") == {"t": 90}
    long = _sexagesimal(MAX_SEXAGESIMAL_CHARS + 30)
    assert safe_load(f't: "{long}"') == {"t": long}
    assert safe_load(f"t: !!str {long}") == {"t": long}
