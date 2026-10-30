"""The SEM validator, D8 tier 3 (C.14.4; K.5.8 ``test_sem_validator``): every check, positive and negative."""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

import pytest
from sem_support import (
    EXAMPLE_AER,
    EXAMPLE_ANNOTATIONS,
    EXAMPLE_SEM,
    StubProfile,
    ann,
    example_aer,
    example_registry,
    example_sem,
    p,
    syn_sem,
    synthetic_aer,
)

from agentprov.aer.canon import dumps_line
from agentprov.aer.validate import ValidationReport
from agentprov.sem.engine import dumps_sem
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.types import SemDocument
from agentprov.sem.validate import ALLOWED_TARGETS, SEM_CHECKS, annotation_problems, validate_sem, validate_sem_document
from agentprov.validate import report_outcomes

REG = example_registry()


def codes(report: ValidationReport) -> set[str]:
    return {f.code for f in report.errors}


def check(doc: SemDocument, aer=None, **kwargs: Any) -> ValidationReport:
    return validate_sem_document(doc, aer or synthetic_aer(), catalogues=kwargs.pop("catalogues", REG), **kwargs)


def reseal(header: dict[str, Any], records: list[dict[str, Any]]) -> SemDocument:
    """A consistent (correctly sealed) document with arbitrary content, read back through the reader."""
    body = b"".join(dumps_line(r) for r in [header, *records])
    seal = {"k": "seal", "id": "seal", "n_records": len(records) + 2, "records_sha256": hashlib.sha256(body).hexdigest()}
    return load_sem_bytes(body + dumps_line(seal))


# ------------------------------------------------------------------------------------------------ the C.14.5 vector
def test_c145_example_validates_with_test_catalogues() -> None:
    report = validate_sem_document(example_sem(), example_aer(), catalogues=REG)
    assert report.passed, report.findings
    assert report.execution_digest == example_sem().digest and report.n_records == 10 and report.ex == example_aer().ex
    assert report.deferred and report.mode == "release"


def test_validate_sem_on_files(tmp_path) -> None:
    assert validate_sem(EXAMPLE_SEM, EXAMPLE_AER, catalogues=REG).passed
    bad = tmp_path / "x.sem.jsonl"
    bad.write_bytes(EXAMPLE_SEM.read_bytes().replace(b'"untrusted"', b'"trusted"'))
    assert codes(validate_sem(bad, EXAMPLE_AER, catalogues=REG)) == {"sem.seal.digest"}
    bad.write_bytes(EXAMPLE_SEM.read_bytes().replace(b"\n", b"\r\n", 1))
    assert codes(validate_sem(bad, EXAMPLE_AER, catalogues=REG)) == {"sem.format"}
    assert codes(validate_sem(EXAMPLE_SEM, tmp_path / "missing.aer.jsonl", catalogues=REG)) == {"sem.aer_digest"}


def test_the_shipped_reserved_marker_rule_is_not_citable() -> None:
    reg = example_registry(reserved=("agentdojo.injection_marker_yaml@1",))
    report = validate_sem_document(example_sem(), example_aer(), catalogues=reg)
    assert codes(report) == {"sem.rule.reserved"} and [f.line for f in report.errors] == [3]


# ------------------------------------------------------------------------------------------------ SEM-V01 .. V03
def test_stale_aer_digest_is_invalid() -> None:
    aer = example_aer()
    other = dataclasses.replace(aer, execution_digest="0" * 64)
    assert codes(validate_sem_document(example_sem(), other, catalogues=REG)) == {"sem.aer_digest"}


def test_ex_must_be_the_aer_execution() -> None:
    doc = example_sem()
    header = {**doc.header, "ex": "ex_aaaaaaaaaaaaaaaaaaaaaaaaaa"}
    assert "sem.ex" in codes(validate_sem_document(reseal(header, doc.annotations), example_aer(), catalogues=REG))


def test_in_memory_seal_tampering() -> None:
    doc = example_sem()
    wrong_digest = dataclasses.replace(doc, seal={**doc.seal, "records_sha256": "0" * 64})
    assert codes(validate_sem_document(wrong_digest, example_aer(), catalogues=REG)) == {"sem.seal.digest"}
    wrong_count = dataclasses.replace(doc, seal={**doc.seal, "n_records": 9})
    assert codes(validate_sem_document(wrong_count, example_aer(), catalogues=REG)) == {"sem.seal.count"}
    edited = [dict(r) for r in doc.records]
    edited[1]["value"] = "trusted"
    stale = dataclasses.replace(doc, records=edited, header=edited[0])
    assert codes(validate_sem_document(stale, example_aer(), catalogues=REG)) == {"sem.seal.digest"}
    extra = dataclasses.replace(doc, seal={**doc.seal, "accounting": {}})
    assert codes(validate_sem_document(extra, example_aer(), catalogues=REG)) == {"sem.format"}


@pytest.mark.parametrize(
    "change",
    [
        {"canon": "json"},
        {"hash": "sha512"},
        {"sem": "0.2"},
        {"id": "x"},
        {"profile": {"id": "agentdojo.suites", "version": 0}},  # a non-int version fails the reader
        {"profile": {"id": "agentdojo.suites", "version": 1, "sha256": "x"}},
        {"rules": {"agentdojo": 0}},
        {"rules": []},
        {"ns": {"plain": {}}},
        {"aer_digest": "0f43"},
        {"extra": 1},
        {"ignore previous instructions": 1},
    ],
)
def test_header_is_closed(change: dict[str, Any]) -> None:
    doc = example_sem()
    report = validate_sem_document(reseal({**doc.header, **change}, doc.annotations), example_aer(), catalogues=REG)
    assert "sem.header" in codes(report)
    for f in report.findings:
        assert "ignore" not in f.pointer and "ignore" not in f.detail  # hostile names are never echoed


def test_missing_header_member() -> None:
    doc = example_sem()
    header = {k: v for k, v in doc.header.items() if k != "ns"}
    assert "sem.header" in codes(validate_sem_document(reseal(header, doc.annotations), example_aer(), catalogues=REG))


# ------------------------------------------------------------------------------------------------ SEM-V04
def test_duplicate_annotation_ids() -> None:
    doc = syn_sem(ann("m0#3", "integrity", "untrusted"), ann("m0#3", "channel", "email"))
    records = [dict(r) for r in doc.annotations]
    records[1]["id"] = "a0"
    assert codes(check(reseal(doc.header, records))) == {"sem.id"}


@pytest.mark.parametrize(
    ("record", "code"),
    [
        ({"prop": "x"}, "sem.schema"),
        ({"id": "x0"}, "sem.id"),
        ({"type": "security_role"}, "sem.schema"),
        ({"type": "contains_payload"}, "sem.schema"),
        ({"ev": "X"}, "sem.schema"),
        ({"premises": [{"id": "m0"}]}, "sem.schema"),
        ({"premises": [{"id": "m0", "p": "x"}]}, "sem.schema"),
        ({"span": {"start": 0, "end": 1}, "at": "/text"}, "sem.span"),
        ({"span": [2, 1], "at": "/text"}, "sem.span"),
        ({"span": [True, 1], "at": "/text"}, "sem.span"),
        ({"at": "text"}, "sem.at"),
        ({"confidence": 1.5, "method": "m"}, "sem.method"),
        ({"confidence": -0.1, "method": "m"}, "sem.method"),
        ({"method": "m"}, "sem.method"),
        ({"confidence": 0.5}, "sem.method"),
        ({"method": "", "confidence": 0.5}, "sem.method"),
        ({"type": "author", "value": {"actor": "att"}, "ev": "D"}, "sem.ev"),
        ({"type": "role", "value": ["write_sink", "write_sink"]}, "sem.value"),
        ({"type": "role", "value": ["sink"]}, "sem.value"),
        ({"type": "role", "value": "write_sink"}, "sem.value"),
        ({"type": "integrity", "value": "Trusted"}, "sem.value"),
        ({"type": "channel", "value": ""}, "sem.value"),
        ({"type": "outcome", "value": {"claim": "x", "holds": True}}, "sem.value"),
        ({"type": "outcome", "value": {"claim": "attack_succeeded", "holds": "yes"}}, "sem.value"),
        ({"type": "outcome", "value": {"claim": "attack_succeeded", "meaning": "bad"}}, "sem.value"),
        ({"type": "outcome", "value": {"claim": "attack_succeeded", "score": True}}, "sem.value"),
        ({"type": "injection_marker", "value": {"fixture": "fx0", "status": "present", "normaliser": "n@1"}},
         "sem.rule.syntax"),
        ({"type": "injection_marker", "value": {"fixture": "fx0", "present": True, "normaliser": "tst.d@1"}},
         "sem.value"),
        ({"type": "injection_marker", "value": {"status": "absent", "normaliser": "tst.d@1"}}, "sem.value"),
        ({"type": "author", "value": "att", "ev": "I"}, "sem.value"),
    ],
)
def test_record_shapes(record: dict[str, Any], code: str) -> None:
    base = {"k": "ann", "id": "a0", "target": "m0#3", "type": "integrity", "value": "untrusted", "ev": "D",
            "rule": ["tst.d@1"], "premises": []}
    found = {c for c, _, _ in annotation_problems({**base, **record})}
    assert code in found
    assert annotation_problems(base) == []


def test_record_shapes_accept_the_c143_vocabulary() -> None:
    base = {"k": "ann", "id": "a0", "target": "m0#3", "ev": "I", "rule": ["tst.i@1"], "premises": []}
    good = [
        {"type": "role", "value": ["write_sink", "send_sink"]},
        {"type": "role", "value": ["unknown"]},
        {"type": "outcome", "value": {"claim": "attack_goal_progress", "score": 0.4, "scale": "0-1"}},
        {"type": "outcome", "value": {"claim": "tst.refused", "holds": False}},
        {"type": "injection_marker", "value": {"status": "gap", "normaliser": "tst.d@1"}},
        {"type": "injection_marker", "value": {"fixture": "fx0", "status": "ambiguous", "normaliser": "tst.d@1"}},
        {"type": "author", "value": {"actor": "att"}, "method": "tst.attribution", "confidence": 0.0},
    ]
    for extra in good:
        assert annotation_problems({**base, **extra}) == [], extra


# ------------------------------------------------------------------------------------------------ SEM-V05
_VALUES = {
    "integrity": ("untrusted", "D", ("tst.d@1",)),
    "channel": ("email", "D", ("tst.d@1",)),
    "role": (["unknown"], "I", ("tst.i@1",)),
    "injection_marker": ({"fixture": "fx0", "status": "absent", "normaliser": "tst.d@1"}, "D", ("tst.d@1",)),
    "outcome": ({"claim": "user_task_solved", "holds": True}, "D", ("tst.d@1",)),
    "author": ({"actor": "att"}, "I", ("tst.i@1",)),
}
_TARGETS = {
    **{f"m0#{k}": f"part:{t}" for k, t in enumerate(
        ("text", "reasoning", "tool_call", "tool_result", "blob", "file", "uri", "refusal", "other"))},
    "m0": "message", "fx0": "fixture", "af0": "artefact", "ac0": "activity", "te0": "tool_execution",
    "j0": "judgement", "mc0": "model_call", "att": "actor", "run": "scope", "exec": "execution", "dc0": "decision",
}


@pytest.mark.parametrize("type_", sorted(_VALUES))
@pytest.mark.parametrize("target", sorted(_TARGETS))
def test_target_kinds_follow_c143(type_: str, target: str) -> None:
    value, ev, rule = _VALUES[type_]
    a = ann(target, type_, value, ev=ev, rule=rule, premises=(p("exec", "/ex"),) if ev == "D" else ())
    report = check(syn_sem(a))
    allowed = _TARGETS[target] in ALLOWED_TARGETS[type_]
    assert ("sem.target.kind" not in codes(report)) is allowed
    if allowed:
        assert report.passed, report.findings


def test_allowed_target_table_is_c143() -> None:
    parts = {f"part:{t}" for t in ("text", "reasoning", "tool_call", "tool_result", "blob", "file", "uri", "refusal",
                                   "other")}
    assert ALLOWED_TARGETS["integrity"] == parts | {"fixture", "artefact"}
    assert ALLOWED_TARGETS["channel"] == {"part:tool_result", "artefact"}
    assert ALLOWED_TARGETS["role"] == {"tool_execution", "part:tool_call", "activity"}
    assert ALLOWED_TARGETS["injection_marker"] == {"part:tool_result"}
    assert ALLOWED_TARGETS["outcome"] == {"judgement"}
    assert ALLOWED_TARGETS["author"] == parts | {"message", "artefact"}


def test_dangling_and_forward_targets() -> None:
    assert codes(check(syn_sem(ann("m9", "integrity", "untrusted", premises=())))) == {"sem.target.dangling"}
    assert codes(check(syn_sem(ann("m0#9", "integrity", "untrusted", premises=())))) == {"sem.target.dangling"}
    assert codes(check(syn_sem(ann("te0#0", "role", ["unknown"], ev="I", rule=("tst.i@1",), premises=())))) == {
        "sem.target.dangling"}
    doc = syn_sem(ann("m0#3", "integrity", "untrusted"), ann("a0", "tst.note", 1), ns={"tst.note": {}})
    assert check(doc).passed
    records = [dict(r) for r in doc.annotations]
    records[0], records[1] = {**records[1], "id": "a0", "target": "a1", "premises": []}, {**records[0], "id": "a1"}
    assert codes(check(reseal(doc.header, records))) == {"sem.target.forward"}


def test_namespaced_types_may_target_any_record_or_the_header() -> None:
    for target in ("exec", "mc0", "dc0", "run", "m0#4"):
        a = ann(target, "tst.note", 1, premises=(p("exec", "/ex"),))
        assert check(syn_sem(a, ns={"tst.note": {"type": "integer"}})).passed


def test_outcome_on_a_harness_default_judgement_is_an_error() -> None:
    a = ann("j1", "outcome", {"claim": "attack_succeeded", "holds": False})
    assert codes(check(syn_sem(a))) == {"sem.outcome.harness_default"}


def test_value_references_into_the_aer() -> None:
    marker = ann("m0#3", "injection_marker", {"fixture": "te0", "status": "absent", "normaliser": "tst.d@1"})
    assert codes(check(syn_sem(marker))) == {"sem.value"}
    gap = ann("m0#3", "injection_marker", {"status": "gap", "normaliser": "tst.d@1"})
    assert check(syn_sem(gap)).passed
    author = ann("m0#3", "author", {"actor": "fx0"}, ev="I", rule=("tst.i@1",))
    assert codes(check(syn_sem(author))) == {"sem.value"}
    unknown_norm = ann("m0#3", "injection_marker", {"fixture": "fx0", "status": "absent", "normaliser": "tst.nope@1"})
    assert codes(check(syn_sem(unknown_norm))) == {"sem.rule.missing"}


# ------------------------------------------------------------------------------------------------ SEM-V06
def test_premises_resolve() -> None:
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", premises=(p("m9", "/x"),))))) == {
        "sem.premise.dangling"}
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", premises=(p("te0", "/nope"),))))) == {
        "sem.premise.pointer"}
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", premises=(p("m0#3", "/nope"),))))) == {
        "sem.premise.pointer"}
    ok = (p("m0#3", "/text"), p("m0", "/parts/3/text"), p("exec", "/task/attack_id"), p("te0", "/name"),
          p("m0", "/actor"))  # /actor is declared not_recorded in unk: reading an unknown is a premise
    assert check(syn_sem(ann("m0#3", "integrity", "untrusted", premises=ok))).passed


def test_annotation_premises_must_be_earlier() -> None:
    doc = syn_sem(ann("m0#3", "integrity", "untrusted"), ann("m0#3", "channel", "email", premises=(p("a0", "/value"),)))
    assert check(doc).passed
    records = [dict(r) for r in doc.annotations]
    records[0]["premises"] = [{"id": "a1", "p": ""}]
    assert codes(check(reseal(doc.header, records))) == {"sem.premise.forward"}
    records[0]["premises"] = [{"id": "a0", "p": ""}]
    assert codes(check(reseal(doc.header, records))) == {"sem.premise.forward"}
    records = [dict(r) for r in doc.annotations]
    records[1]["premises"] = [{"id": "a0", "p": "/nope"}]
    assert codes(check(reseal(doc.header, records))) == {"sem.premise.pointer"}


# ------------------------------------------------------------------------------------------------ SEM-V07
@pytest.mark.parametrize(
    ("at", "span", "code"),
    [
        ("/text", (0, 3), None),  # three scalar values (one astral) = the whole string
        ("/text", (1, 3), None),
        ("/text", (3, 3), None),  # empty half-open range at the end
        ("/text", (0, 4), "sem.span"),  # four UTF-16 code units, but only three scalar values
        ("/nope", (0, 1), "sem.at"),
        ("", (0, 1), "sem.span"),  # the part object is not a string
        ("/t", (0, 4), None),
        ("/t", (0, 5), "sem.span"),
    ],
)
def test_span_counts_unicode_scalar_values(at: str, span: tuple[int, int], code: str | None) -> None:
    report = check(syn_sem(ann("m0#0", "integrity", "untrusted", at=at, span=span)))
    assert codes(report) == ({code} if code else set())


def test_marker_span_on_a_tool_result() -> None:
    value = {"fixture": "fx0", "status": "present", "normaliser": "tst.d@1"}
    assert check(syn_sem(ann("m0#3", "injection_marker", value, at="/text", span=(7, 10)))).passed
    assert codes(check(syn_sem(ann("m0#3", "injection_marker", value, at="/text", span=(7, 11))))) == {"sem.span"}


# ------------------------------------------------------------------------------------------------ SEM-V09
def test_namespaced_type_declared_and_schema() -> None:
    ns = {"tst.note": {"type": "object", "properties": {"n": {"type": "integer", "minimum": 0}},
                       "required": ["n"], "additionalProperties": False}}
    assert check(syn_sem(ann("m0", "tst.note", {"n": 2}), ns=ns)).passed
    for bad in ({"n": -1}, {"n": "2"}, {}, {"n": 1, "x": 0}, [1]):
        assert codes(check(syn_sem(ann("m0", "tst.note", bad), ns=ns))) == {"sem.value.schema"}, bad
    doc = syn_sem(ann("m0", "tst.note", {"n": 2}), ns=ns)
    assert codes(check(reseal({**doc.header, "ns": {}}, doc.annotations))) == {"sem.type.undeclared"}
    unsupported = syn_sem(ann("m0", "tst.note", 1), ns={"tst.note": {"oneOf": [{"type": "integer"}]}})
    assert codes(check(unsupported)) == {"sem.ns.schema"}


def test_header_patterns_are_not_run_without_a_trusted_profile() -> None:
    ns = {"tst.note": {"type": "string", "pattern": "^a"}}
    doc = syn_sem(ann("m0", "tst.note", "b"), ns=ns)
    report = check(doc)
    assert report.ok and not report.passed and any(s.startswith("SEM-V09:") for s in report.skipped)
    profile = StubProfile((), id="tst.syn", rules={"tst": 1}, ns=ns)
    assert codes(check(doc, profile=profile)) == {"sem.value.schema"}
    assert check(syn_sem(ann("m0", "tst.note", "abc"), ns=ns), profile=profile).passed
    other = StubProfile((), id="tst.syn", rules={"tst": 1}, ns={})
    assert "sem.header" in codes(check(doc, profile=other))


# ------------------------------------------------------------------------------------------------ SEM-V10, V11
def test_rule_existence() -> None:
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", rule=("tst.nope@1",))))) == {"sem.rule.missing"}
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", rule=("tst.held@1",))))) == {"sem.rule.reserved"}
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", rule=("tst.d@2",))))) == {"sem.rule.missing"}
    undeclared = syn_sem(ann("m0#3", "integrity", "untrusted", rule=("agentdojo.read_tools@1",)))
    assert codes(check(undeclared)) == {"sem.rule.missing"}
    unavailable = check(syn_sem(ann("m0#3", "integrity", "untrusted"), rules={"tst": 2}))
    assert codes(unavailable) == {"sem.rule.missing"} and [f.line for f in unavailable.errors] == [0]
    scoped = syn_sem(ann("m0#3", "integrity", "untrusted", rule=("tst.d@1#/value",)))
    assert check(scoped).passed
    assert codes(check(syn_sem(ann("m0#3", "integrity", "untrusted", rule=("tst.d@1#/nope",))))) == {"sem.rule.syntax"}


@pytest.mark.parametrize(
    ("ev", "rule", "premises", "code"),
    [
        ("D", ("tst.d@1",), (p("te0", "/name"),), None),
        ("D", ("tst.i@1",), (p("te0", "/name"),), "sem.rule.class"),  # D annotation citing an I rule
        ("D", ("tst.d@1", "tst.i@1"), (p("te0", "/name"),), "sem.rule.class"),
        ("I", ("tst.i@1",), (p("te0", "/name"),), None),
        ("I", ("tst.d@1",), (p("te0", "/name"),), "sem.rule.class"),  # I annotation without an I rule
        ("I", ("tst.d@1",), (p("m0", "/parts/1/text"),), None),  # I only by propagation from an I premise (C.6.4)
        ("D", ("tst.d@1",), (p("m0", "/parts/1/text"),), "sem.ev"),  # D over an I premise raises the class
        ("D", ("tst.d@1",), (p("mc0", ""),), None),
        ("O", ("tst.d@1",), (p("te0", "/name"),), None),  # the source recorded the label itself
        ("O", ("tst.d@1",), (p("mc0", ""),), "sem.ev"),  # O over a D premise
        ("O", ("tst.i@1",), (p("te0", "/name"),), "sem.rule.class"),
        ("I", ("tst.i@1",), (p("dc0", ""),), None),
    ],
)
def test_class_constraints_and_propagation(ev: str, rule: tuple[str, ...], premises: tuple, code: str | None) -> None:
    report = check(syn_sem(ann("m0#3", "integrity", "untrusted", ev=ev, rule=rule, premises=premises)))
    assert codes(report) == ({code} if code else set())


def test_premise_on_an_earlier_annotation_carries_its_class() -> None:
    first = ann("m0#3", "integrity", "untrusted", ev="I", rule=("tst.i@1",))
    second = ann("m0#3", "channel", "email", ev="D", rule=("tst.d@1",), premises=(p("a0", "/value"),))
    assert codes(check(syn_sem(first, second))) == {"sem.ev"}


def test_without_catalogues_package_resources_are_used() -> None:
    report = validate_sem_document(syn_sem(ann("m0#3", "integrity", "untrusted")), synthetic_aer())
    assert codes(report) == {"sem.rule.missing"}  # the package ships no ``tst`` catalogue


def test_mode_is_validated() -> None:
    with pytest.raises(ValueError):
        check(example_sem(), mode="lenient")
    assert check(syn_sem(ann("m0#3", "integrity", "untrusted")), mode="dev").mode == "dev"


# ------------------------------------------------------------------------------------------------ tier wiring
def test_report_outcomes_fold_tier_3_into_the_check_registry() -> None:
    passing = report_outcomes(validate_sem_document(example_sem(), example_aer(), catalogues=REG), SEM_CHECKS)
    assert [o.id for o in passing] == list(SEM_CHECKS) and all(o.status == "pass" for o in passing)
    failing = report_outcomes(check(syn_sem(ann("j1", "outcome", {"claim": "attack_succeeded"}))), SEM_CHECKS)
    by_id = {o.id: o for o in failing}
    assert by_id["SEM-V08"].status == "fail" and by_id["SEM-V08"].codes() == {"sem.outcome.harness_default"}
    assert sum(o.failed for o in failing) == 1
    ns = {"tst.note": {"type": "string", "pattern": "^a"}}
    skipped = {o.id: o for o in report_outcomes(check(syn_sem(ann("m0", "tst.note", "b"), ns=ns)), SEM_CHECKS)}
    assert skipped["SEM-V09"].status == "skipped" and skipped["SEM-V09"].reason


def test_example_round_trips_and_stays_valid(tmp_path) -> None:
    path = tmp_path / "e.sem.jsonl"
    path.write_bytes(dumps_sem(example_sem()))
    assert validate_sem(path, EXAMPLE_AER, catalogues=REG).passed
    assert len(EXAMPLE_ANNOTATIONS) == 8


def test_a_present_marker_found_only_in_a_decoded_reading_may_omit_at_and_span() -> None:
    """EF E.7.3 gives a span only "when SEM gives a span"; a decoded-only match has no location in the text (C.14.6)."""
    base = {"k": "ann", "id": "a0", "target": "m0#3", "type": "injection_marker", "ev": "D", "rule": ["tst.d@1"],
            "premises": [], "value": {"fixture": "fx0", "status": "present", "normaliser": "tst.d@1"}}
    assert not [p for p in annotation_problems(base) if p[0] == "sem.span"]


def test_an_annotation_with_no_premises_is_bounded_by_its_rule_34() -> None:
    """Pre-round review #34: C.6.5 rule 3 makes an annotation's class the weakest of its premises and its rule's class.
    With no premises the bound is the rule's class, and no rule is O, so an O annotation without premises is refused;
    before, SEM-V11 said nothing for an empty premise list."""
    observed = syn_sem(ann("m0#0", "integrity", "untrusted", ev="O", rule=("tst.d@1",), premises=()))
    assert "sem.ev" in codes(check(observed))
    derived = syn_sem(ann("m0#0", "integrity", "untrusted", ev="D", rule=("tst.d@1",), premises=()))
    assert "sem.ev" not in codes(check(derived))
