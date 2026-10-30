"""C.6: evidence classes, effective tags (longest-prefix ``evf``), propagation by ``weakest``."""

from __future__ import annotations

import pytest

from agentprov.aer.evidence import (
    asserted_fields,
    effective_party,
    effective_tag,
    effective_tags,
    is_prefix,
    is_valid_tag,
    parse_tag,
    tag_class,
    weakest,
)


def test_effective_tag_is_longest_prefix_on_slash_boundaries() -> None:
    rec = {"k": "message", "ev": "O", "evf": {"/parts": "D", "/parts/0": "I", "/part": "O:provider"}}
    assert effective_tag(rec, "/parts/0/text") == "I"
    assert effective_tag(rec, "/parts/1/text") == "D"
    assert effective_tag(rec, "/parts") == "D"
    assert effective_tag(rec, "/partsx") == "O"  # "/parts" is not a prefix of "/partsx" on a boundary
    assert effective_tag(rec, "/part/a") == "O:provider"
    assert effective_tag(rec, "/role") == "O"


def test_ev_is_the_default_and_the_seal_has_none() -> None:
    assert effective_tag({"ev": "D"}, "/anything") == "D"
    with pytest.raises(ValueError, match="."):
        effective_tag({"k": "seal"}, "/x")


def test_weakest_orders_o_d_i_and_never_raises_a_class() -> None:
    assert weakest("O") == "O"
    assert weakest("O", "D") == "D"
    assert weakest("D", "I", "O") == "I"
    assert weakest("O:provider", "O") == "O"
    assert weakest("O:source", "D") == "D"
    with pytest.raises(ValueError, match="."):
        weakest()


def test_tag_grammar() -> None:
    for good in ("O", "D", "I", "O:capture", "O:source", "O:provider", "O:benchmark", "O:config", "O:replay"):
        assert is_valid_tag(good)
    for bad in ("", "o", "X", "D:source", "O:", "O:other", "O:Source", 1, None):
        assert not is_valid_tag(bad)
    assert parse_tag("O:provider") == ("O", "provider") and parse_tag("I") == ("I", None)
    assert tag_class("O:replay") == "O"


def test_effective_party() -> None:
    rec = {"ev": "O", "by": "source"}
    assert effective_party(rec, "O") == "source"
    assert effective_party(rec, "O:provider") == "provider"
    assert effective_party(rec, "D") is None
    assert effective_party({"ev": "O"}, "O") is None


def test_asserted_fields_exclude_envelope_meta_and_seal() -> None:
    rec = {"k": "message", "id": "m", "ev": "O", "by": "x", "evf": {}, "rule": [], "src": [], "unk": {}, "ext": {},
           "after": [], "role": "user", "parts": []}
    assert asserted_fields(rec) == ["after", "role", "parts"]
    header = {"k": "execution", "id": "exec", "ev": "O", "aer": "0.1", "ex": "e", "task": {}, "rules": {}, "instrumentation": []}
    assert asserted_fields(header) == ["task", "instrumentation"]
    assert asserted_fields({"k": "seal", "id": "seal", "n_records": 3}) == []


def test_effective_tags_collects_defaults_and_overrides() -> None:
    rec = {"k": "actor", "ev": "D", "kind": "llm_agent", "model": {}, "evf": {"/model": "I", "/x/y": "O"}}
    assert effective_tags(rec) == {"D", "I", "O"}


@pytest.mark.parametrize(("a", "b", "expected"), [("/a", "/a", True), ("/a", "/a/b", True), ("/a", "/ab", False), ("", "/a", True)])
def test_is_prefix(a: str, b: str, expected: bool) -> None:
    assert is_prefix(a, b) is expected
