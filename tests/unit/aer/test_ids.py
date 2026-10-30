"""K.5.2: execution ids (C.4.1 known-answer vectors), local ids, part ids, instance IRIs."""

from __future__ import annotations

import base64
import hashlib

import pytest
from aer_support import KAT1_EX, REPO, VECTOR_NAMES, vector_records

from agentprov.aer.ids import (
    EXECUTION_ID_RE,
    FIXED_IDS,
    LOCAL_ID_PREFIXES,
    LOCAL_ID_RE,
    canonical_key_loc,
    import_execution_id,
    instance_iri,
    is_local_id,
    is_part_id,
    is_ref_id,
    live_execution_id,
    mapping_id,
    part_id,
    shard,
    split_part_id,
)
from agentprov.io.canonical import jcs_bytes

SHA_C161 = "99e641af97e56971dd67308beec96ac08fdca7063141f3714389733ba845cc8a"
MAPPING = "agentdojo.tracelogger/agentdojo-upstream"

# The four known-answer vectors of C.4.1 (identical to K.5.2).
KATS = [
    (MAPPING, SHA_C161, {"p": ""}, "fd33a7625df9e869ca8445f0b613855f77c7c31ca3c300e3caab17a25e781345", KAT1_EX),
    (
        MAPPING,
        SHA_C161,
        {},
        "5670e59816893573d45e1704128116fe2d5b5666b2201ef91368960e338b404a",
        "ex_kzyolgawre2xhvc6c4cbfaiw7y",
    ),
    (
        MAPPING,
        SHA_C161,
        {"line": 0},
        "06dead820644bf297f8b13a1f92e9ed880a51049b10d51793fa6c6a83dbdc1c2",
        "ex_a3pk3aqgis7ss74lcoq7slu63c",
    ),
    (
        "inspect.eval/survey-agentharm",
        "3a04cbc50dee2ec447a4796004a4800e68d3ceb30a3f886a52db88b184fad35d",
        {"p": ""},
        "4c4c6ae10744f755cae97a1d0ce302dc9577db0826da20bfb9c53e1e79aadf75",
        "ex_jrggvyihit3vlsxjpioqzyyc3s",
    ),
]


@pytest.mark.parametrize(("mapping", "sha", "loc", "preimage_sha", "ex"), KATS)
def test_known_answer_vectors(mapping: str, sha: str, loc: dict[str, object], preimage_sha: str, ex: str) -> None:
    preimage = b"aer-ex/1\n" + mapping.encode() + b"\n" + sha.encode() + b"\n" + jcs_bytes(loc)
    assert hashlib.sha256(preimage).hexdigest() == preimage_sha
    assert import_execution_id(mapping, sha, loc) == ex
    assert EXECUTION_ID_RE.fullmatch(ex)


def test_kat1_is_the_c161_header_id() -> None:
    header = vector_records("agentdojo_2024_pi_detector")[0]
    assert header["ex"] == KAT1_EX
    assert (
        import_execution_id(
            mapping_id(header["adapter"]["id"], header["profile"]["id"]),
            header["source_key"]["sha256"],
            header["source_key"]["loc"],
        )
        == KAT1_EX
    )


@pytest.mark.parametrize("name", VECTOR_NAMES)
def test_every_vector_header_id_is_recomputable(name: str) -> None:
    header = vector_records(name)[0]
    key = header["source_key"]
    assert header["ex"] == import_execution_id(
        mapping_id(header["adapter"]["id"], header["profile"]["id"]), key["sha256"], key["loc"]
    )


def test_the_first_sixteen_bytes_variant_differs() -> None:
    # The trace-format sketch's variant (base32 of the first 16 bytes) is not the rule (obs-K6, AD-04).
    preimage = b"aer-ex/1\n" + MAPPING.encode() + b"\n" + SHA_C161.encode() + b"\n" + b'{"p":""}'
    short = base64.b32encode(hashlib.sha256(preimage).digest()[:16]).decode().lower().rstrip("=")
    assert ("ex_" + short[:26]) != KAT1_EX


def test_mapping_id_excludes_versions_and_is_part_of_the_preimage() -> None:
    assert mapping_id("a.b", "p") == "a.b/p"
    assert import_execution_id("a.b/p", SHA_C161, {}) != import_execution_id("a.b/q", SHA_C161, {})
    for bad in (("", "p"), ("a", ""), ("a/b", "p"), ("a\n", "p")):
        with pytest.raises(ValueError, match="."):
            mapping_id(*bad)


def test_the_id_depends_on_the_artefact_digest_and_locator() -> None:
    base = import_execution_id(MAPPING, SHA_C161, {"p": ""})
    assert import_execution_id(MAPPING, "0" * 64, {"p": ""}) != base
    assert import_execution_id(MAPPING, SHA_C161, {"p": "/0"}) != base


@pytest.mark.parametrize(
    "loc",
    [{"a": "a0"}, {"p": "x"}, {"line": -1}, {"bytes": [3, 3]}, {"bytes": [1, 2], "p": ""}, {"line": True}, {"o": "/x"}],
)
def test_non_canonical_key_locators_are_rejected(loc: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="."):
        canonical_key_loc(loc)
    with pytest.raises(ValueError, match="."):
        import_execution_id(MAPPING, SHA_C161, loc)


@pytest.mark.parametrize("loc", [{}, {"p": ""}, {"p": "/223"}, {"line": 0}, {"line": 4, "p": "/x"}, {"bytes": [0, 9]}])
def test_canonical_key_locators_are_accepted(loc: dict[str, object]) -> None:
    assert canonical_key_loc(loc) == loc


def test_artefact_digest_must_be_lowercase_hex64() -> None:
    for bad in ("", "A" * 64, "0" * 63, "sha256:" + "0" * 64):
        with pytest.raises(ValueError, match="."):
            import_execution_id(MAPPING, bad, {})


def test_live_ids() -> None:
    session = "0190a6e0-1d5c-7a3b-8c4d-123456789abc"
    assert live_execution_id(session) == "ex_" + session
    assert EXECUTION_ID_RE.fullmatch("ex_" + session)
    for bad in ("0190A6E0-1D5C-7A3B-8C4D-123456789ABC", "0190a6e0-1d5c-4a3b-8c4d-123456789abc", "x"):
        with pytest.raises(ValueError, match="."):
            live_execution_id(bad)


@pytest.mark.parametrize("good", ["m0", "mc12", "te0", "agent", "def_pi_detector", "att0", "run", "x" + "y" * 31])
def test_local_id_grammar_accepts(good: str) -> None:
    assert is_local_id(good)


@pytest.mark.parametrize("bad", ["", "0m", "M0", "a-b", "x" * 33, "def.pi", "a0", "a12", "as", "m0#1", "é"])
def test_local_id_grammar_rejects(bad: str) -> None:
    assert not is_local_id(bad)


def test_header_artefact_ids_and_the_reserved_name_as_are_not_record_ids() -> None:
    # `a<n>` names raw artefacts of the header; `af<n>` (artefact records) can never collide with it (K.5.1 item 7).
    assert not LOCAL_ID_RE.fullmatch("a0")
    assert LOCAL_ID_RE.fullmatch("af0") and LOCAL_ID_RE.fullmatch("ac0")
    assert not LOCAL_ID_RE.fullmatch("as")


def test_prefix_table_is_read_from_the_grammar_and_disjoint_from_header_artefact_ids() -> None:
    assert LOCAL_ID_PREFIXES["artefact"] == "af" and LOCAL_ID_PREFIXES["activity"] == "ac"
    for prefix in LOCAL_ID_PREFIXES.values():
        assert prefix != "a"
        assert LOCAL_ID_RE.fullmatch(prefix + "0")
    assert FIXED_IDS == {"execution": "exec", "seal": "seal"}


def test_part_ids() -> None:
    assert part_id("m2", 1) == "m2#1"
    assert split_part_id("m2#10") == ("m2", 10)
    assert is_part_id("m2#0") and not is_part_id("m2#01") and not is_part_id("m2") and not is_part_id("m2#-1")
    assert is_ref_id("m2#3") and is_ref_id("exec") and not is_ref_id("M2")
    for bad in ("m2", "m2#01", "#1"):
        with pytest.raises(ValueError, match="."):
            split_part_id(bad)
    with pytest.raises(ValueError, match="."):
        part_id("m2", -1)


def test_instance_iri_maps_hash_to_hyphen() -> None:
    assert instance_iri(KAT1_EX, "m2#1") == f"https://w3id.org/agentprov/exec/{KAT1_EX}#m2-1"
    assert instance_iri(KAT1_EX, "run") == f"https://w3id.org/agentprov/exec/{KAT1_EX}#run"
    with pytest.raises(ValueError, match="."):
        instance_iri("not-an-id", "m0")
    with pytest.raises(ValueError, match="."):
        instance_iri(KAT1_EX, "M0")


def test_shard_is_the_first_two_hex_digits_of_the_id_digest() -> None:
    assert shard(KAT1_EX) == hashlib.sha256(KAT1_EX.encode()).hexdigest()[:2]


def test_the_ids_module_has_no_clock_or_randomness() -> None:
    source = (REPO / "src" / "agentprov" / "aer" / "ids.py").read_text(encoding="utf-8")
    for forbidden in ("import time", "import random", "import uuid", "datetime", "urandom"):
        assert forbidden not in source
