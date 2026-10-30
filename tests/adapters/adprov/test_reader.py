"""Reader of ``adprov.transcript_v1`` (docs/architecture D.7.2, D.2.3; K.6.2, K.11)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

import pytest

from agentprov.adapters.adprov.dialect import (
    FLAG_CAPTURE,
    FLAG_CONVERTED,
    FLAG_DISCARDED,
    FLAG_NULL_AS_EMPTY,
    FLAG_STUBBED,
    TranscriptV1Reader,
)
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.types import ArtefactRef, CandidateArtefact
from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()


def test_golden_transcripts_sniff_as_the_dialect_with_their_flags(golden_pairs):
    reader = TranscriptV1Reader()
    for pair_id, pair in sorted(golden_pairs.items()):
        result = reader.sniff(pair.transcript.read_bytes(), label=pair_id, limits=LIMITS)
        assert result.match and result.dialect == "adprov.transcript_v1" and result.variant == "v1", pair_id
        if pair_id.startswith("C"):
            assert {FLAG_CONVERTED, FLAG_STUBBED} <= result.flags and FLAG_NULL_AS_EMPTY not in result.flags
        else:
            assert result.flags == frozenset({FLAG_NULL_AS_EMPTY}), pair_id


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xef\xbb\xbf{}",
        b"[1, 2]",
        b'{"adprov_schema": "transcript/v2", "meta": {}, "turns": []}',
        b'{"adprov_schema": "transcript/v1", "meta": [], "turns": []}',
        b'{"adprov_schema": "transcript/v1", "meta": {}, "turns": {}}',
        b'{"adprov_schema": "transcript/v1", "adprov_schema": "transcript/v1", "meta": {}, "turns": []}',
        b'{"suite_name": "banking", "messages": []}',
        b"\xff\xfe not utf-8",
    ],
)
def test_foreign_or_unsafe_bytes_never_match_and_never_raise(data):
    result = TranscriptV1Reader().sniff(data, label="x", limits=LIMITS)
    assert not result.match and result.reasons


def test_flags_follow_d72():
    reader = TranscriptV1Reader()
    base = b'{"adprov_schema": "transcript/v1", "meta": %s, "turns": []%s}'
    assert reader.sniff(base % (b"{}", b""), label="", limits=LIMITS).flags == {FLAG_NULL_AS_EMPTY}
    capture = reader.sniff(base % (b'{"capture": {}, "n_attempts": 1}', b""), label="", limits=LIMITS).flags
    assert capture == {FLAG_CAPTURE}
    discarded = reader.sniff(base % (b"{}", b', "discarded_attempts": []'), label="", limits=LIMITS).flags
    assert discarded == {FLAG_DISCARDED}


def test_parse_yields_one_item_at_the_json_root(v1):
    raw = v1.dump(v1.released())
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", v1.origin("x"))
    (item,) = list(TranscriptV1Reader().parse(raw, artefact, limits=LIMITS))
    assert item.locator.key() == {"p": ""} and item.dialect == "adprov.transcript_v1"
    assert list(item.value) == ["adprov_schema", "meta", "turns"]  # source member order kept for ext.lex


def test_parse_enforces_tier1_limits(v1):
    raw = v1.dump(v1.released())
    artefact = ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", v1.origin("x"))
    with pytest.raises(IngestError):
        list(TranscriptV1Reader().parse(raw, artefact, limits=LIMITS.replace(max_json_bytes=64)))


def test_discovery_applies_the_profile_globs_and_skips_strays(v1):
    labels = ["b/x.transcript.json", "a/._x.transcript.json", "a/.DS_Store", "a/x.json", "x.transcript.json"]

    class Tree:
        def walk(self) -> Iterator[CandidateArtefact]:
            for label in labels:
                yield CandidateArtefact(label, 1, v1.origin(label))

        def open(self, label: str, *, max_bytes: int) -> bytes:
            raise AssertionError("discovery must not read contents")

    found = [c.label for c in TranscriptV1Reader().iter_artefacts(Tree(), load_profile("adprov-v1"))]
    assert found == ["b/x.transcript.json", "x.transcript.json"]
