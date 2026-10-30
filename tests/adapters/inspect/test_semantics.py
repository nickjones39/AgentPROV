"""The ``inspect.agentharm@1`` semantics profile (docs/architecture D.9, C.14.1-C.14.3, EF E.7.3; R-37).

The profile is discovered by convention (``agentprov.adapters.semantics_profiles.load_semantics_profile``) and reads only the AER. Tools
are fail-closed (AgentHarm's tool list is not available offline) and there is no taint policy; outcomes come from the
scorer table. The committed survey log (176 samples) is the observed case; the benign split, a recomputed score, an
unlisted scorer, a missing value and a ``harness_default`` judgement are built in code. The logs hold harmful requests
by design: these tests compare ids, kinds and numbers and print nothing else (R-42).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest

import inspect_support as support
from agentprov.adapters.registry import get_source
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import load_catalogue
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.sem.profiles import parse_profile_ref, profile_digest
from agentprov.sem.types import CORE_OUTCOME_CLAIMS, INTEGRITY_VALUES, ROLE_VALUES, Annotation, SemanticsProfile

PACKAGE = "agentprov.adapters.inspect"
SEMANTICS = Path(__file__).resolve().parents[3] / "src" / "agentprov" / "adapters" / "inspect" / "semantics"
CONTENT_PARTS = {"text", "reasoning", "tool_call", "tool_result", "blob", "file", "uri", "refusal", "other"}
DECLARED = {"inspect.tools_fail_closed@1", "inspect.scorer_claim_table@1"}
HARMFUL = "inspect_evals/agentharm"


def profile() -> SemanticsProfile:
    return load_semantics_profile("inspect.agentharm", 1)


def annotate(data: bytes) -> tuple[AerDocument, list[Annotation]]:
    doc = load_aer_bytes(data)
    return doc, list(profile().annotate(doc))


@pytest.fixture(scope="module")
def sems(committed: support.Imported) -> list[tuple[support.Unit, AerDocument, list[Annotation]]]:
    out = []
    for u in committed.units:
        doc, anns = annotate(u.data)
        out.append((u, doc, anns))
    return out


def synthetic(tmp_path: Path, **tune: Any) -> tuple[support.Unit, AerDocument, list[Annotation]]:
    sample = support.basic_sample(tune=tune.get("tune"))
    header = support.synthetic_header()
    if "task" in tune:
        header["eval"]["task"] = tune["task"]
    imported = support.import_log(support.build_eval(header, {"s1_epoch_1.json": sample}), tmp_path / "raw")
    (unit,) = imported.units
    assert not unit.outcome.degenerate
    doc, anns = annotate(unit.data)
    return unit, doc, anns


def outcomes(anns: list[Annotation]) -> dict[str, Any]:
    return {a.target: a.value for a in anns if a.type == "outcome"}


def with_records(doc: AerDocument, *extra: dict[str, Any], header: dict[str, Any] | None = None) -> AerDocument:
    return AerDocument(header or doc.header, [*doc.records, *extra], doc.seal, doc.execution_digest, doc.file_sha256)


def test_the_profile_is_found_by_convention_and_digests_its_data_files():
    prof = profile()
    assert isinstance(prof, SemanticsProfile)
    assert (prof.id, prof.version, dict(prof.rules), dict(prof.ns), prof.taint_policy) == ("inspect.agentharm", 1, {"inspect": 1}, {}, None)
    assert parse_profile_ref("inspect.agentharm@1") == ("inspect.agentharm", 1)
    files = {p.relative_to(SEMANTICS / "inspect.agentharm-1").as_posix(): p.read_bytes()
             for p in (SEMANTICS / "inspect.agentharm-1").rglob("*") if p.is_file()}
    assert set(files) == {"tables.toml"} and prof.sha256 == profile_digest(files)
    assert b"EMPTY ON PURPOSE" in files["tables.toml"]  # the profile data says that no tool is known


def test_annotate_is_deterministic(sems):
    for u, doc, anns in sems[:20]:
        assert list(profile().annotate(load_aer_bytes(u.data))) == anns == list(profile().annotate(doc))


def test_every_target_exists_with_an_allowed_kind_and_every_value_is_in_the_closed_vocabulary(sems):
    kinds = set()
    for u, doc, anns in sems:
        for a in anns:
            kinds.add(a.type)
            if "#" in a.target:
                part = doc.part(a.target)
                assert part is not None, (u.label, a.target)
                record, part_kind = "part", part["t"]
            else:
                found = doc.get(a.target)
                assert found is not None, (u.label, a.target)
                record, part_kind = found["k"], None
            if a.type == "integrity":
                assert record == "part" and part_kind in CONTENT_PARTS and a.value in INTEGRITY_VALUES
            elif a.type == "role":
                assert (record, part_kind) in {("part", "tool_call"), ("tool_execution", None), ("activity", None)}
                assert isinstance(a.value, list) and set(a.value) <= set(ROLE_VALUES)
            else:
                assert a.type == "outcome" and record == "judgement"
                assert isinstance(a.value, dict) and set(a.value) <= {"claim", "holds", "score", "scale"}
            assert a.at is None and a.span is None and a.method is None and a.confidence is None
            for premise in a.premises:
                assert doc.get(premise.id) is not None, (u.label, premise)
    assert kinds == {"integrity", "role", "outcome"}  # no channel, marker or author: nothing here justifies one


def test_every_cited_rule_is_declared_citable_and_matches_the_evidence_class(sems):
    cat = load_catalogue("inspect", 1, package=PACKAGE)
    cited = set()
    for _, _, anns in sems:
        for a in anns:
            assert a.ev == "I" and a.rule
            for ref in a.rule:
                entry = cat.get(ref.split("#", 1)[0])
                assert entry is not None and entry.citable and entry.status == "active" and entry.cls == a.ev
                cited.add(entry.rule_id)
    assert cited == DECLARED
    source = (SEMANTICS / "__init__.py").read_text(encoding="utf-8")
    assert set(re.findall(r'"(inspect\.[a-z_]+@[0-9]+)"', source)) == DECLARED


def test_every_tool_is_fail_closed(sems, tmp_path):
    seen = {"calls": 0, "executions": 0, "results": 0}
    for _, doc, anns in sems:
        roles = {a.target: a.value for a in anns if a.type == "role"}
        integrity = {a.target: a.value for a in anns if a.type == "integrity"}
        for te in doc.of_kind("tool_execution"):
            assert roles[te["id"]] == ["unknown"]
            seen["executions"] += 1
        for msg in doc.of_kind("message"):
            for i, part in enumerate(msg["parts"]):
                target = f"{msg['id']}#{i}"
                if part["t"] == "tool_call":
                    assert roles[target] == ["unknown"]
                    seen["calls"] += 1
                elif part["t"] == "tool_result":
                    assert integrity[target] == "unknown"
                    seen["results"] += 1
                else:
                    assert target not in roles and target not in integrity  # nothing but tool traffic is labelled
        assert set(integrity.values()) <= {"unknown"} and all(v == ["unknown"] for v in roles.values())
    assert min(seen.values()) > 0
    _, doc, anns = synthetic(tmp_path)  # the synthetic tool get_x is no more known than AgentHarm's
    assert sorted((a.type, a.value) for a in anns if a.type != "outcome") == [("integrity", "unknown"), ("role", ["unknown"]), ("role", ["unknown"])]
    assert len(doc.of_kind("tool_execution")) == 1


def test_outcomes_follow_the_scorer_table_and_carry_score_and_scale(sems, tmp_path):
    n = 0
    for _, doc, anns in sems:
        judgements = [j for j in doc.of_kind("judgement") if j["origin"] != "harness_default" and j.get("value") is not None]
        assert len(judgements) == 2 and set(outcomes(anns)) == {j["id"] for j in judgements}
        for j in judgements:
            value = outcomes(anns)[j["id"]]
            assert value["score"] == j["value"] and "scale" in value
            if j["name"] == "combined_scorer.score":
                assert value == {"claim": "inspect.harmful_task_score", "score": j["value"], "scale": "unit_interval"}
                assert 0 <= value["score"] <= 1
            else:
                assert j["name"] == "combined_scorer.refusal"
                assert value == {"claim": "inspect.refusal", "holds": j["value"] == 1, "score": j["value"], "scale": "binary"}
            assert value["claim"].startswith("inspect.") and value["claim"] not in CORE_OUTCOME_CLAIMS
            n += 1
        (annotation,) = [a for a in anns if a.type == "outcome" and a.target == judgements[0]["id"]]
        assert [(p.id, p.p) for p in annotation.premises][:3] == [(judgements[0]["id"], "/name"), (judgements[0]["id"], "/value"), (judgements[0]["id"], "/origin")]
    assert n == 352
    # the benign split (polarity: a higher score is more capability, not more harm)
    _, _, anns = synthetic(tmp_path)
    assert sorted(outcomes(anns).values(), key=lambda v: v["claim"]) == [
        {"claim": "inspect.benign_task_score", "score": 1.0, "scale": "unit_interval"},
        {"claim": "inspect.refusal", "holds": False, "score": 0.0, "scale": "binary"},
    ]
    # a suite that is neither: the polarity-free claim
    _, _, anns = synthetic(tmp_path / "other", task="some_other/agentharm_variant")
    assert {v["claim"] for v in outcomes(anns).values()} == {"inspect.task_score", "inspect.refusal"}


def test_a_recomputed_score_is_read_like_the_checker_one(tmp_path):
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-se", "span_id": None, "timestamp": support.ts(30.0), "working_start": 30.0,
                                 "event": "score_edit", "score_name": "combined_scorer",
                                 "edit": {"value": {"score": 0.5}, "explanation": "Synthetic correction."}})

    unit, doc, anns = synthetic(tmp_path, tune=tune)
    edited = next(j for j in doc.of_kind("judgement") if j["origin"] == "recomputed")
    assert outcomes(anns)[edited["id"]] == {"claim": "inspect.benign_task_score", "score": 0.5, "scale": "unit_interval"}
    assert len(outcomes(anns)) == 3 and unit.of_kind("judgement")


def test_no_outcome_for_a_harness_default_an_unrecorded_value_an_unlisted_scorer_or_an_out_of_scale_value(sems):
    _, doc, _ = sems[0]
    base = {"k": "judgement", "actor": "bench", "subject": "run", "ev": "O", "by": "benchmark"}
    cases = [
        {"id": "jx0", "name": "combined_scorer.score", "origin": "harness_default", "value": 1},  # C.14.3
        {"id": "jx1", "name": "combined_scorer.score", "origin": "checker"},  # no recorded value
        {"id": "jx2", "name": "combined_scorer.score", "origin": "checker", "value": None},
        {"id": "jx3", "name": "other_scorer.score", "origin": "checker", "value": 1},  # unlisted scorer
        {"id": "jx4", "name": "combined_scorer.score", "origin": "checker", "value": 2},  # outside its scale
        {"id": "jx5", "name": "combined_scorer.refusal", "origin": "checker", "value": 0.5},  # not a flag
        {"id": "jx6", "name": "combined_scorer.refusal", "origin": "checker", "value": "yes"},
    ]
    for case in cases:
        stub = with_records(doc, {**base, **case})
        assert case["id"] not in outcomes(list(profile().annotate(stub))), case["id"]
    ok = with_records(doc, {**base, "id": "jy", "name": "combined_scorer.refusal", "origin": "checker", "value": True})
    assert outcomes(list(profile().annotate(ok)))["jy"] == {"claim": "inspect.refusal", "holds": True, "scale": "binary"}


def test_the_registry_part_declares_the_profile():
    part = {c.part: c for c in get_source("agent-security-tools-survey").capabilities}["agentharm"]
    assert part.semantics == ("inspect.agentharm@2",)  # D-31 option B: @1 on the inspect catalogue version 2
    assert all(parse_profile_ref(ref) == ("inspect.agentharm", 2) for ref in part.semantics)


def test_the_header_task_is_not_modified_by_annotation(sems):
    u, doc, _ = sems[0]
    before = copy.deepcopy(doc.header)
    list(profile().annotate(doc))
    assert doc.header == before and doc.header["task"]["suite"] == HARMFUL and u.header["task"]["suite"] == HARMFUL


def test_every_sem_document_seals_and_passes_the_tier3_validator(sems):
    """End to end through the SEM engine and validator (C.14.4), with the profile's own declarations."""
    from agentprov.sem.engine import annotate as sem_annotate
    from agentprov.sem.validate import validate_sem_document

    prof = profile()
    for _unit, doc, _anns in sems:
        report = validate_sem_document(sem_annotate(doc, prof), doc, mode="release", profile=prof)
        assert report.ok and not report.errors, [f.code for f in report.errors]
