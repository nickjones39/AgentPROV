"""K.11.1 over the raw layer: the decoders of ``origins.jsonl``, ``members.jsonl`` and ``REFERENCES.json`` (files of a
corpus that may come back from a deposit, so untrusted), and the content-addressed store.

Properties: F-1 (success or a typed error with its code), F-5 (determinism), round trips (decode . encode = id), and the
store never turns a hostile digest string into a path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.raw.members import MembersError, decode_members
from agentprov.raw.origins import Origin, OriginError, OriginLog, OriginRow, decode_origins, encode_origins
from agentprov.raw.references import ReferencesError, parse_references
from agentprov.raw.store import RawObjectStore, RawStoreError

HEX = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
SHA1 = st.text(alphabet="0123456789abcdef", min_size=40, max_size=40)
LABEL = st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Cf", "Zl", "Zp")), min_size=1, max_size=40)
SLUG = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=12)
REPO = st.tuples(SLUG, SLUG).map(lambda p: f"https://github.com/{p[0]}/{p[1]}")
UUID7 = st.uuids(version=4).map(lambda u: str(u)[:14] + "7" + str(u)[15:])
ORIGINS = st.one_of(
    st.builds(Origin.git, REPO, SHA1, LABEL, SHA1),
    st.builds(Origin.hf, st.tuples(SLUG, SLUG).map("/".join), SHA1, LABEL),
    st.builds(Origin.zenodo, st.integers(1, 10**8).map(lambda n: f"10.5281/zenodo.{n}"), LABEL),
    st.builds(Origin.corpus, LABEL, LABEL, LABEL),
    st.builds(Origin.capture, UUID7),
)


@budget(80)
@given(st.lists(st.tuples(HEX, ORIGINS), max_size=6))
def test_origins_round_trip_and_stay_one_line_per_row(rows: list[tuple[str, Origin]]) -> None:
    built = [OriginRow(sha, origin) for sha, origin in rows]
    data = encode_origins(built)
    assert data.count(b"\n") == len({r.sort_key for r in built})
    decoded = decode_origins(data)
    assert encode_origins(decoded) == data


def _origins_seed() -> bytes:
    log = OriginLog()
    log.add("a" * 64, Origin.git("https://github.com/x/y", "c" * 40, "runs/a.json", "d" * 40))
    log.add("b" * 64, Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.json"))
    return log.serialise()


@budget(150)
@given(byte_mutations(_origins_seed()))
def test_mutated_origins_files_fail_closed_with_a_code(data: bytes) -> None:
    first = outcome(lambda: [r.to_json() for r in decode_origins(data)], OriginError)
    assert first == outcome(lambda: [r.to_json() for r in decode_origins(data)], OriginError)
    if first[0] == "OriginError":
        assert str(first[1]).startswith("raw.origin.")


MEMBERS_SEED = b"".join(
    json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    for row in [
        {"container": "sha256:" + "a" * 64, "crc32": "0000abcd", "disposition": "selected", "fn_digest": "sha256:" + "f" * 64,
         "label": "header.json", "method": 8, "sha256": "sha256:" + "b" * 64, "size": 10},
        {"container": "sha256:" + "a" * 64, "crc32": "00001234", "disposition": "not_selected",
         "fn_digest": "sha256:" + "f" * 64, "label": "x.bin", "method": 0, "sha256": None, "size": 3},
    ]
)


def test_the_members_seed_is_valid() -> None:
    assert len(decode_members(MEMBERS_SEED)) == 2


@budget(150)
@given(byte_mutations(MEMBERS_SEED))
def test_mutated_members_files_fail_closed_with_a_code(data: bytes) -> None:
    first = outcome(lambda: [r.to_json() for r in decode_members(data)], MembersError)
    assert first == outcome(lambda: [r.to_json() for r in decode_members(data)], MembersError)
    if first[0] == "MembersError":
        assert str(first[1]).startswith("raw.members.")


REFERENCES_SEED = json.dumps({
    "format": "agentprov-raw-references/0.1",
    "objects": [{"sha256": "sha256:" + "a" * 64, "bytes": 3, "reason": "licence-no-redistribution",
                 "origins": [{"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "x.zip"}]}],
}).encode()


def test_the_references_seed_is_valid() -> None:
    assert [r.sha256 for r in parse_references(REFERENCES_SEED)] == ["a" * 64]


@budget(150)
@given(byte_mutations(REFERENCES_SEED))
def test_mutated_references_fail_closed_with_a_code(data: bytes) -> None:
    first = outcome(lambda: [r.sha256 for r in parse_references(data)], ReferencesError)
    assert first == outcome(lambda: [r.sha256 for r in parse_references(data)], ReferencesError)


@budget(60)
@given(st.text(max_size=80))
def test_hostile_digest_strings_are_absent_and_never_reach_the_filesystem(tmp_path_factory, digest: str) -> None:
    store = RawObjectStore(tmp_path_factory.mktemp("store"))
    for call in (store.has, store.read_bytes, store.size, store.verify):
        result = outcome(lambda call=call: call(digest), RawStoreError, KeyError, ValueError)
        assert result[0] in ("ok", "RawStoreError", "KeyError", "ValueError"), result
        if call is store.has:
            assert result == ("ok", False)


@budget(60)
@given(st.binary(max_size=4096))
def test_the_store_round_trips_any_bytes_by_their_digest(tmp_path_factory, data: bytes) -> None:
    root: Path = tmp_path_factory.mktemp("store")
    store = RawObjectStore(root)
    put = store.put(data, ext="bin")
    assert put.sha256 == hashlib.sha256(data).hexdigest() and store.read_bytes(put.sha256) == data
    assert store.put(data, ext="bin").created is False  # never rewritten
    assert all(p.stat().st_mode & 0o222 == 0 for p in root.rglob("*") if p.is_file())  # mode 0444
