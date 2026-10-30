"""K.5.2 properties: the execution-id function is deterministic, well formed and sensitive to every input."""

from __future__ import annotations

import hashlib
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.aer.ids import (
    EXECUTION_ID_RE,
    LOCAL_ID_RE,
    import_execution_id,
    instance_iri,
    mapping_id,
    part_id,
    shard,
    split_part_id,
)

S = settings(max_examples=300, deadline=None, derandomize=True)
HEX64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
IDENT = st.from_regex(r"[a-z][a-z0-9_]{0,12}(\.[a-z][a-z0-9_]{0,12}){0,2}", fullmatch=True)
LOC = st.one_of(
    st.just({}),
    st.builds(lambda p: {"p": p}, st.one_of(st.just(""), st.integers(0, 9999).map(lambda i: f"/{i}"))),
    st.builds(lambda n: {"line": n}, st.integers(0, 10**6)),
    st.builds(lambda a, d: {"bytes": [a, a + 1 + d]}, st.integers(0, 10**6), st.integers(0, 10**6)),
)


@S
@given(IDENT, IDENT, HEX64, LOC)
def test_id_is_well_formed_and_deterministic(adapter: str, profile: str, sha: str, loc: dict[str, object]) -> None:
    ex = import_execution_id(mapping_id(adapter, profile), sha, loc)
    assert EXECUTION_ID_RE.fullmatch(ex) and len(ex) == 29 and re.fullmatch(r"ex_[a-z2-7]{26}", ex)
    assert ex == import_execution_id(mapping_id(adapter, profile), sha, dict(reversed(list(loc.items()))))


@S
@given(IDENT, IDENT, HEX64, HEX64, LOC, LOC)
def test_every_input_changes_the_id(adapter: str, profile: str, sha_a: str, sha_b: str, loc_a: dict[str, object], loc_b: dict[str, object]) -> None:
    base = import_execution_id(mapping_id(adapter, profile), sha_a, loc_a)
    if sha_a != sha_b:
        assert import_execution_id(mapping_id(adapter, profile), sha_b, loc_a) != base
    if loc_a != loc_b:
        assert import_execution_id(mapping_id(adapter, profile), sha_a, loc_b) != base
    assert import_execution_id(mapping_id(adapter + "x", profile), sha_a, loc_a) != base
    assert import_execution_id(mapping_id(adapter, profile + "x"), sha_a, loc_a) != base


@S
@given(st.text(max_size=20))
def test_local_id_grammar_matches_its_definition(text: str) -> None:
    expected = bool(re.fullmatch(r"[a-z][a-z0-9_]{0,31}", text)) and not re.fullmatch(r"a(0|[1-9][0-9]*)", text) and text != "as"
    assert bool(LOCAL_ID_RE.fullmatch(text)) == expected


@S
@given(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True).filter(lambda s: LOCAL_ID_RE.fullmatch(s) is not None), st.integers(0, 10**4))
def test_part_ids_roundtrip_and_iris_are_injective(message: str, k: int) -> None:
    assert split_part_id(part_id(message, k)) == (message, k)
    ex = "ex_" + "a" * 26
    assert instance_iri(ex, part_id(message, k)) != instance_iri(ex, part_id(message + "x", k))
    assert "#" in instance_iri(ex, message) and instance_iri(ex, part_id(message, k)).count("#") == 1


@S
@given(st.from_regex(r"ex_[a-z2-7]{26}", fullmatch=True))
def test_shard_is_two_hex_digits_of_the_id_digest(ex: str) -> None:
    assert shard(ex) == hashlib.sha256(ex.encode()).hexdigest()[:2] and len(shard(ex)) == 2
