"""P4: :func:`agentprov.corpus.derive.raw_input_closure`, the raw objects a sampled re-derivation stages (members'
containers at every level, a split descriptor's parts, a carved blob's source and a source's carved blobs)."""

from __future__ import annotations

import hashlib

from agentprov.corpus.derive import raw_input_closure
from agentprov.raw.members import MemberRow
from agentprov.raw.origins import Origin, OriginRow


def h(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


FN = h("fn")


def member(sha: str, container: str) -> MemberRow:
    return MemberRow(container=container, fn_digest=FN, label="m", method=0, crc32="00000000", size=1, sha256=sha,
                     disposition="selected")


def origin(sha: str, kind: str, **data: object) -> OriginRow:
    return OriginRow(sha, Origin.from_json({"kind": kind, **data}))


def test_members_climb_every_container_level_and_split_parts_and_carved_pairs_join():
    outer, inner, leaf, other_leaf = h("outer.zip"), h("inner.zip"), h("leaf.eval"), h("other.eval")
    part1, part2, blob, other_blob, unrelated = h("p1"), h("p2"), h("blob"), h("other-blob"), h("unrelated")
    members = [member(inner, outer), member(leaf, inner), member(other_leaf, inner)]
    origins = [
        origin(outer, "split", archive="zip", label="deposit.zip", parts=[part1, part2]),
        origin(blob, "carved", **{"from": leaf, "loc": {"line": 0, "p": "/task"}, "transform": "utf8"}),
        origin(other_blob, "carved", **{"from": other_leaf, "loc": {"line": 0, "p": "/task"}, "transform": "utf8"}),
    ]
    closure = raw_input_closure([leaf], members, origins)
    assert closure == {leaf, inner, outer, part1, part2, blob}  # never the sibling member or its blob
    assert raw_input_closure([blob], members, origins) == closure  # from the blob: its source, and the source's chain
    assert raw_input_closure([unrelated], members, origins) == {unrelated}
    assert raw_input_closure([], members, origins) == frozenset()


def test_a_member_held_in_two_containers_needs_both_and_a_cycle_ends():
    a, b, m = h("a.zip"), h("b.zip"), h("m")
    assert raw_input_closure([m], [member(m, a), member(m, b)], []) == {m, a, b}
    assert raw_input_closure([a], [member(a, b), member(b, a)], []) == {a, b}
