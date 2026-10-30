"""C.6.3 / C.6.5 properties: longest-prefix resolution and the weakest-class combinator."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.aer.evidence import effective_tag, is_prefix, tag_class, weakest

S = settings(max_examples=300, deadline=None, derandomize=True)
TAGS = st.sampled_from(["O", "D", "I", "O:source", "O:provider", "O:capture"])
TOKEN = st.sampled_from(["a", "b", "parts", "0", "1", "x~0y"])
POINTERS = st.lists(TOKEN, min_size=1, max_size=4).map(lambda t: "".join("/" + x for x in t))
EVF = st.dictionaries(POINTERS, TAGS, max_size=5)
RANK = {"O": 0, "D": 1, "I": 2}


@S
@given(st.lists(TAGS, min_size=1, max_size=6))
def test_weakest_is_commutative_idempotent_and_never_stronger_than_an_input(tags: list[str]) -> None:
    w = weakest(*tags)
    assert w == weakest(*reversed(tags)) and w == weakest(w, *tags) and w in RANK
    assert all(RANK[w] >= RANK[tag_class(t)] for t in tags)
    assert w in {tag_class(t) for t in tags}


@S
@given(st.lists(TAGS, min_size=1, max_size=4), st.lists(TAGS, min_size=1, max_size=4))
def test_weakest_is_associative(a: list[str], b: list[str]) -> None:
    assert weakest(weakest(*a), *b) == weakest(*a, *b)


@S
@given(TAGS.filter(lambda t: t in ("O", "D", "I")), EVF, POINTERS)
def test_effective_tag_is_the_longest_matching_prefix(ev: str, evf: dict[str, str], pointer: str) -> None:
    got = effective_tag({"ev": ev, "evf": evf}, pointer)
    matching = [k for k in evf if is_prefix(k, pointer)]
    expected = evf[max(matching, key=len)] if matching else ev
    assert got == expected


@S
@given(TAGS.filter(lambda t: t in ("O", "D", "I")), EVF, POINTERS, TAGS)
def test_a_more_specific_entry_always_wins(ev: str, evf: dict[str, str], pointer: str, tag: str) -> None:
    specific = {**evf, pointer: tag}
    assert effective_tag({"ev": ev, "evf": specific}, pointer) == tag
    assert effective_tag({"ev": ev, "evf": specific}, pointer + "/child") in (tag, *[evf[k] for k in evf if is_prefix(k, pointer + "/child") and len(k) > len(pointer)])
