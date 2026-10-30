"""The SEM engine (C.14.1-C.14.2): header, numbering, seal, the C.14.5 vector byte for byte, profile defects, paths."""

from __future__ import annotations

import hashlib
import json

import pytest
from sem_support import (
    EXAMPLE_ANNOTATIONS,
    EXAMPLE_SEM,
    SYN_EX,
    StubProfile,
    ann,
    example_aer,
    example_sem,
    p,
    synthetic_aer,
)

from agentprov.corpus.layout import CorpusLayout, shard
from agentprov.sem.engine import SemAnnotationError, annotate, dumps_sem, sem_header
from agentprov.sem.types import Annotation, sem_profile_dir


def test_c145_example_is_reproduced_byte_for_byte() -> None:
    aer = example_aer()
    expected = EXAMPLE_SEM.read_bytes()
    header = json.loads(expected.split(b"\n", 1)[0])
    assert header["aer_digest"] == "sha256:" + aer.execution_digest, "the C.14.5 aer_digest no longer matches C.16.2"
    doc = example_sem()
    assert dumps_sem(doc) == expected
    assert doc.digest == json.loads(expected.splitlines()[-1])["records_sha256"]
    assert doc.file_sha256 == hashlib.sha256(expected).hexdigest()


def test_header_numbering_and_seal() -> None:
    aer = example_aer()
    doc = example_sem()
    assert doc.header == sem_header(aer, StubProfile(EXAMPLE_ANNOTATIONS))
    assert doc.header == {
        "k": "sem", "id": "sem", "sem": "0.1", "ex": aer.ex, "aer_digest": "sha256:" + aer.execution_digest,
        "profile": {"id": "agentdojo.suites", "version": 1}, "rules": {"agentdojo": 1}, "ns": {},
        "canon": "jcs-rfc8785", "hash": "sha256",
    }
    assert [a["id"] for a in doc.annotations] == [f"a{i}" for i in range(8)]
    assert doc.seal["n_records"] == 10 and set(doc.seal) == {"k", "id", "n_records", "records_sha256"}
    body = dumps_sem(doc).rsplit(b"\n", 2)[0] + b"\n"
    assert doc.seal["records_sha256"] == hashlib.sha256(body).hexdigest() == doc.digest
    assert doc.on("m3#0", "integrity")[0]["value"] == "untrusted" and doc.get("a7") is not None
    assert doc.profile_dir == "agentdojo.suites-1" and doc.aer_digest == aer.execution_digest


def test_empty_profile_gives_header_and_seal_only() -> None:
    doc = annotate(example_aer(), StubProfile(()))
    assert doc.annotations == [] and doc.seal["n_records"] == 2


def test_engine_is_deterministic_across_runs() -> None:
    first = dumps_sem(example_sem())
    assert dumps_sem(example_sem()) == first
    assert dumps_sem(annotate(example_aer(), StubProfile(tuple(EXAMPLE_ANNOTATIONS)))) == first


def test_optional_members_are_omitted_and_method_confidence_written() -> None:
    a = ann("m0#3", "author", {"actor": "att"}, ev="I", rule=("tst.i@1",), method="tst.attribution", confidence=0.75)
    doc = annotate(synthetic_aer(), StubProfile((a,), id="tst.syn", rules={"tst": 1}))
    rec = doc.annotations[0]
    assert rec["method"] == "tst.attribution" and rec["confidence"] == 0.75 and "at" not in rec and "span" not in rec


@pytest.mark.parametrize(
    ("annotation", "code"),
    [
        (ann("m0#3", "integrity", "untrusted", premises=(p("a0"),)), "sem.premise.forward"),  # names itself
        (ann("m0#3", "integrity", "untrusted", premises=(p("a5"),)), "sem.premise.forward"),  # names a later one
        (ann("a0", "tst.note", 1), "sem.target.forward"),
        (ann("m0#3", "integrity", "maybe"), "sem.value"),
        (ann("m0#3", "role", []), "sem.value"),
        (ann("m0#3", "integrity", "trusted", rule=()), "sem.schema"),
        (ann("m0#3", "integrity", "trusted", rule=("not a rule",)), "sem.rule.syntax"),
        (ann("m0#3", "integrity", "trusted", span=(0, 1)), "sem.span"),  # span without at
        (ann("m0#3", "integrity", "trusted", confidence=0.5), "sem.method"),
        (ann("m0#3", "x.undeclared", 1), "sem.type.undeclared"),
        (ann("m0#3", "Integrity", "trusted"), "sem.schema"),
        (ann("m0#3", "channel", float("nan")), "sem.value"),  # not representable in JCS
    ],
)
def test_profile_defects_are_rejected(annotation: Annotation, code: str) -> None:
    profile = StubProfile((annotation,), id="tst.syn", rules={"tst": 1}, ns={"tst.note": {}})
    with pytest.raises(SemAnnotationError) as info:
        annotate(synthetic_aer(), profile)
    assert info.value.code == code and info.value.index == 0


def test_a_premise_on_an_earlier_annotation_is_accepted() -> None:
    first = ann("m0#3", "integrity", "untrusted")
    second = ann("m0#3", "channel", "email", premises=(p("a0", "/value"),))
    doc = annotate(synthetic_aer(), StubProfile((first, second), id="tst.syn", rules={"tst": 1}))
    assert doc.annotations[1]["premises"] == [{"id": "a0", "p": "/value"}]


def test_non_annotation_yield_is_rejected() -> None:
    with pytest.raises(SemAnnotationError):
        annotate(synthetic_aer(), StubProfile(({"target": "m0"},), id="tst.syn"))  # type: ignore[arg-type]


def test_sem_path_uses_the_aer_shard() -> None:
    layout = CorpusLayout("/corpus")
    rel = layout.sem_relpath("agentdojo.suites@1", SYN_EX)
    assert rel == f"sem/{sem_profile_dir('agentdojo.suites', 1)}/{shard(SYN_EX)}/{SYN_EX}.sem.jsonl"
    assert rel.split("/")[2] == layout.aer_relpath(SYN_EX).split("/")[1]
    deep = CorpusLayout("/corpus", shard_depth=2)
    assert deep.sem_relpath("agentdojo.suites@1", SYN_EX).split("/")[2:4] == deep.aer_relpath(SYN_EX).split("/")[1:3]
    assert layout.sem_path("agentdojo.suites@1", SYN_EX).parts[-4:] == ("sem", "agentdojo.suites-1", shard(SYN_EX),
                                                                         f"{SYN_EX}.sem.jsonl")
    for bad in ("../x@1", "agentdojo.suites@0", "agentdojo.suites@01", "agentdojo.suites", "Agentdojo.suites@1"):
        with pytest.raises(ValueError):
            layout.sem_relpath(bad, SYN_EX)
