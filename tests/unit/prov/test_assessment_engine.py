"""The assessment bundle on the synthetic generic-kind execution (EF E.7, E.3.4, E.9; K.6.4 constructs).

The fixture holds an approved, a modified and a denied request of one invocation, a text-parsed execution without a
request part (``te2``, ``requested_by`` only) and DERIVED context membership, so the exposures it yields are DERIVED.
Covered here: the ruling that a request-less execution gets no exposure (EF E.7.3 over D.12.2 / K.6.4), fail-closed
selection, the refusals of ``derive`` for SEM documents, the harness-default outcome rule, determinism, and that SEM
documents never change the core or inference bundles.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402
from aer_support import derived  # noqa: E402
from assess_support import FakeProfile, ann, sem_document, semtest_catalogue  # noqa: E402

from agentprov.aer.reader import AerDocument  # noqa: E402
from agentprov.aer.rules import RuleRegistry  # noqa: E402
from agentprov.prov.engine import ProvDerivation, ProvDerivationError, derive  # noqa: E402
from agentprov.validate import validate_prov  # noqa: E402

PROFILE = FakeProfile()
PROFILES = {(PROFILE.id, PROFILE.version): PROFILE}


def registry() -> RuleRegistry:
    reg = ps.registry()
    reg.add(semtest_catalogue())
    return reg


def records() -> list[dict[str, Any]]:
    recs = ps.generic_records()
    recs.append(derived({"k": "actor", "id": "bench", "kind": "benchmark", "name": "tst-bench"}))
    recs.append(derived({"k": "judgement", "id": "j0", "actor": "bench", "name": "security", "origin": "harness_default",
                         "subject": "run", "value": False}))
    return recs


@pytest.fixture(scope="module")
def aer(tmp_path_factory: pytest.TempPathFactory) -> AerDocument:
    doc = ps.write_aer(records(), tmp_path_factory.mktemp("assess") / "g.aer.jsonl")
    assert ps.check_valid(doc, registry()) == []
    return doc


def run(aer: AerDocument, annotations: list[Any], *, profile: FakeProfile = PROFILE, **kw: Any) -> ProvDerivation:
    sem = sem_document(aer, annotations, profile=profile)
    return derive(aer, [sem], registry=registry(), sem_profiles={(profile.id, profile.version): profile}, **kw)


def assess(result: ProvDerivation) -> tuple[str, dict[str, Any]]:
    doc = json.loads(result.prov_json)
    iri = next(k for k in doc["bundle"] if ".assess." in k)
    return iri, doc["bundle"][iri]


def claims(bundle: dict[str, Any], claim: str) -> list[dict[str, Any]]:
    return [b for b in bundle.get("entity", {}).values() if b.get("apv:claim", {}).get("$") == claim]


# ============================================================================================================ exposure
def test_request_less_execution_gets_no_exposure(aer: AerDocument) -> None:
    result = run(aer, [])
    iri, bundle = assess(result)
    counts = result.report.assessment[iri]
    assert counts["exposure_no_request"] == 1  # te2: requested_by only, no generating invocation
    subjects = {b["apv:subject"]["$"] for b in claims(bundle, "apv:ExposedTo")}
    assert "x:te2" not in subjects
    # unlabelled requests and members are unknown (fail-closed): the three requests of mc0, each exposed to m0
    assert subjects == {"x:m1-1", "x:m1-2", "x:m1-3"} and counts["exposures"] == 3 and counts["taints"] == 3


def test_exposure_class_is_the_weakest_premise(aer: AerDocument) -> None:
    _, bundle = assess(run(aer, []))
    for body in claims(bundle, "apv:ExposedTo"):
        # DERIVED context membership and generation: a DERIVED exposure, no method (E.7.3, AD-05)
        assert body["apv:evidenceClass"]["$"] == "apv:Derived" and "apv:method" not in body
        assert body["apv:object"]["$"] == "x:m0"
    for body in claims(bundle, "apv:PotentiallyInfluencedBy"):
        assert body["apv:evidenceClass"]["$"] == "apv:Inferred" and body["apv:method"] == "aprov.a_taint@1"


def test_selection_by_role_and_integrity(aer: AerDocument) -> None:
    anns = [
        ann("te0", "role", ["neutral"], "I", "read_tools", [("te0", "/name")]),  # m1#1 is approved, executed by te0
        ann("m1#2", "role", ["write_sink", "neutral"], "I", "sink_tools", [("m1", "/parts/2/name")]),
    ]
    result = run(aer, anns)
    iri, bundle = assess(result)
    counts = result.report.assessment[iri]
    assert counts["exposure_neutral_request"] == 1
    assert {b["apv:subject"]["$"] for b in claims(bundle, "apv:ExposedTo")} == {"x:m1-2", "x:m1-3"}
    trusted = run(aer, [*anns, ann("m0#0", "integrity", "trusted", "I", "integrity_table", [("m0", "/role")])])
    iri, bundle = assess(trusted)
    assert claims(bundle, "apv:ExposedTo") == [] and trusted.report.assessment[iri]["exposure_trusted_object"] == 2


def test_taint_needs_a_policy_and_matching_roles(aer: AerDocument) -> None:
    no_policy = FakeProfile(taint_policy=None)
    _, bundle = assess(run(aer, [], profile=no_policy))
    assert claims(bundle, "apv:PotentiallyInfluencedBy") == [] and len(claims(bundle, "apv:ExposedTo")) == 3
    read_only = [ann("m1#3", "role", ["content_source"], "I", "read_tools", [("m1", "/parts/3/name")])]
    _, bundle = assess(run(aer, read_only))
    tainted = {b["apv:subject"]["$"] for b in claims(bundle, "apv:PotentiallyInfluencedBy")}
    assert tainted == {"x:m1-1", "x:m1-2"}  # content_source is not a sink: exposed, not tainted


# ============================================================================================================ labels
def test_harness_default_outcome_is_not_emitted(aer: AerDocument) -> None:
    result = run(aer, [ann("j0", "outcome", {"claim": "attack_succeeded", "holds": False}, "D", "polarity",
                           [("j0", "/value")])])
    iri, bundle = assess(result)
    assert result.report.assessment[iri]["outcome_harness_default"] == 1
    assert not any("apv:outcomeClaim" in b for b in bundle.get("entity", {}).values())


def test_labels_on_generic_records(aer: AerDocument) -> None:
    anns = [
        ann("af0", "integrity", "untrusted", "I", "integrity_table", [("af0", "/type")]),
        ann("ac0", "role", ["endorser"], "I", "read_tools", [("ac0", "/type")]),
    ]
    _, bundle = assess(run(aer, anns))
    mentions = [(k, b) for k, b in bundle["entity"].items() if k.startswith("x:af0.mn-")]
    assert len(mentions) == 1 and mentions[0][1]["apv:integrity"]["$"] == "apv:Untrusted"
    labelled = [b for b in claims(bundle, "apv:Labelled") if b["apv:subject"]["$"] == "x:ac0"]
    assert len(labelled) == 1 and labelled[0]["apv:securityRole"]["$"] == "apv:Endorser"


def test_generic_derivation_with_sem_passes_tier4(aer: AerDocument) -> None:
    anns = [ann("m2#0", "integrity", "untrusted", "I", "integrity_table", [("te0", "/name")]),
            ann("te1", "role", ["send_sink"], "I", "sink_tools", [("te1", "/name")])]
    sem = sem_document(aer, anns)
    reg = registry()
    result = derive(aer, [sem], registry=reg, sem_profiles=PROFILES)
    report = validate_prov(result.prov_json, aer, registry=reg, sems=[sem])
    assert [(o.id, sorted(o.codes())) for o in report.outcomes if o.status in ("fail", "skipped")] == []


def test_a_premise_field_declared_unknown_is_not_cited(tmp_path: Path) -> None:
    """D-930 (NE-12, E.1.5 item 1): SEM may rest a label on a field its record declares unknown (SEM-V06); the
    assessment keeps the label but cites no such field, and counts it. Wave 2: an ambiguous tool name under a role."""
    recs = records()
    te1 = next(r for r in recs if r.get("id") == "te1")
    te1["unk"] = {**te1.get("unk", {}), "/name": "ambiguous"}
    doc = ps.write_aer(recs, tmp_path / "unk.aer.jsonl")
    reg = registry()
    assert ps.check_valid(doc, reg) == []
    anns = [ann("te1", "role", ["send_sink"], "I", "sink_tools", [("te1", "/name")]),
            ann("te0", "role", ["content_source"], "I", "read_tools", [("te0", "/name")])]
    sem = sem_document(doc, anns)
    result = derive(doc, [sem], registry=reg, sem_profiles=PROFILES)
    iri, bundle = assess(result)
    assert result.report.assessment[iri]["premise_field_unknown"] == 1 and result.report.assessment[iri]["labels"] == 2
    labelled = {b["apv:subject"]["$"]: b for b in claims(bundle, "apv:Labelled")}
    assert set(labelled) == {"x:te0", "x:te1"} and {b["apv:rule"] for b in labelled.values()} == {"aprov.a_label@2"}
    pointers = {k: v["apv:sourcePointer"] for sec in bundle.values() for k, v in sec.items() if "apv:sourcePointer" in v}
    assert sorted(map(str, pointers.values())) == ["['te0', 'te0/name']"] * 2 + ["te1"] * 2  # te1/name is not cited
    report = validate_prov(result.prov_json, doc, registry=reg, sems=[sem])
    assert [(o.id, sorted(o.codes())) for o in report.outcomes if o.status in ("fail", "skipped")] == []


# ============================================================================================================ no SEM / determinism
def test_derivation_without_sem_is_unchanged(aer: AerDocument) -> None:
    plain = derive(aer, registry=registry())
    assert derive(aer, (), registry=registry(), sem_profiles=PROFILES).prov_json == plain.prov_json
    with_sem = json.loads(run(aer, [ann("m0#0", "integrity", "trusted", "I", "integrity_table", [])]).prov_json)
    doc = json.loads(plain.prov_json)
    assert {k: v for k, v in with_sem["bundle"].items() if ".assess." not in k} == doc["bundle"]
    assert plain.report.as_json().get("assessment") is None


def test_two_runs_and_document_order_are_byte_identical(aer: AerDocument) -> None:
    other = FakeProfile(id="semtest.other", sha256="6" * 64)
    a = sem_document(aer, [ann("m0#0", "integrity", "trusted", "I", "integrity_table", [])])
    b = sem_document(aer, [ann("m0#0", "integrity", "untrusted", "I", "integrity_table", [])], profile=other)
    profiles = {**PROFILES, (other.id, other.version): other}
    first = derive(aer, [a, b], registry=registry(), sem_profiles=profiles)
    second = derive(aer, [b, a], registry=registry(), sem_profiles=profiles)
    assert first.prov_json == second.prov_json
    assert [x.kind for x in first.bundles][-2:] == ["assessment", "assessment"]
    assert [x.profile for x in first.bundles if x.kind == "assessment"] == ["semtest.other@1", "semtest.suites@1"]


def test_bundle_key_depends_on_the_sem_digest(aer: AerDocument) -> None:
    one = assess(run(aer, [ann("m0#0", "integrity", "trusted", "I", "integrity_table", [])]))[0]
    two = assess(run(aer, [ann("m0#0", "integrity", "unknown", "I", "integrity_table", [])]))[0]
    assert one != two and one.rsplit(".", 1)[0] == two.rsplit(".", 1)[0]


# ============================================================================================================ refusals
def _code(exc: pytest.ExceptionInfo[ProvDerivationError]) -> str:
    return str(exc.value.code)


def test_sem_of_another_aer_is_refused(aer: AerDocument) -> None:
    for kw in ({"aer_digest": "0" * 64}, {"ex": "ex_aaaaaaaaaaaaaaaaaaaaaaaaaa"}):
        sem = sem_document(aer, [], **kw)
        with pytest.raises(ProvDerivationError) as exc:
            derive(aer, [sem], registry=registry(), sem_profiles=PROFILES)
        assert _code(exc) == "prov.sem_stale"


def test_profile_must_be_supplied_and_match(aer: AerDocument) -> None:
    sem = sem_document(aer, [])
    with pytest.raises(ProvDerivationError) as exc:
        derive(aer, [sem], registry=registry())
    assert _code(exc) == "prov.sem_profile_missing"
    with pytest.raises(ProvDerivationError) as exc:
        derive(aer, [sem], registry=registry(), sem_profiles={(PROFILE.id, 1): FakeProfile(version=2)})
    assert _code(exc) == "prov.sem_profile_mismatch"
    with pytest.raises(ProvDerivationError) as exc:
        derive(aer, [sem, sem_document(aer, [ann("m0#0", "channel", "x", "I", "channel_table", [])])],
               registry=registry(), sem_profiles=PROFILES)
    assert _code(exc) == "prov.sem_duplicate_profile"


@pytest.mark.parametrize("annotation, code", [
    ({"target": "m0#0", "type": "integrity", "value": "maybe", "ev": "I", "rule": ["semtest.integrity_table@1"],
      "premises": []}, "prov.sem_invalid"),
    ({"target": "m0#0", "type": "colour", "value": "red", "ev": "D", "rule": ["semtest.ns_label@1"], "premises": []},
     "prov.sem_invalid"),
    ({"target": "m9#0", "type": "integrity", "value": "trusted", "ev": "I", "rule": ["semtest.integrity_table@1"],
      "premises": []}, "prov.unresolved_reference"),
    ({"target": "m0#0", "type": "integrity", "value": "trusted", "ev": "I", "rule": ["semtest.marker@1"],
      "premises": []}, "prov.method_set_empty"),
    ({"target": "m0#0", "type": "integrity", "value": "trusted", "ev": "I", "rule": ["semtest.integrity_table@1"],
      "premises": [{"id": "a7", "p": ""}]}, "prov.unresolved_reference"),
    ({"target": "m0#0", "type": "integrity", "value": "trusted", "ev": "I", "rule": ["semtest.integrity_table@1"],
      "premises": [{"id": "m0", "p": "/nope"}]}, "prov.unresolved_pointer"),
])
def test_malformed_annotations_are_typed_failures(aer: AerDocument, annotation: dict[str, Any], code: str) -> None:
    with pytest.raises(ProvDerivationError) as exc:
        run(aer, [annotation])
    assert _code(exc) == code


SCRIPT = """
import sys
sys.path.insert(0, {here!r})
sys.path.insert(0, {aer_here!r})
import prov_support as ps
from assess_support import FakeProfile, sem_document, semtest_catalogue, suite_annotations
from agentprov.aer.reader import load_aer
from agentprov.prov.engine import derive
aer = load_aer({path!r})
reg = ps.registry()
reg.add(semtest_catalogue())
p = FakeProfile()
sem = sem_document(aer, suite_annotations(aer))
sys.stdout.buffer.write(derive(aer, [sem], registry=reg, sem_profiles={{(p.id, p.version): p}}).prov_json)
"""


def test_same_bytes_in_fresh_processes_with_different_hash_seeds(tmp_path: Path) -> None:
    path = tmp_path / "g.aer.jsonl"
    ps.write_aer(records(), path)
    here = str(Path(__file__).resolve().parent)
    aer_here = str(Path(__file__).resolve().parents[1] / "aer")
    outputs = []
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "TZ": "Pacific/Auckland" if seed == "1" else "UTC"}
        done = subprocess.run([sys.executable, "-c", SCRIPT.format(here=here, aer_here=aer_here, path=str(path))],
                              env=env, capture_output=True, check=True, timeout=120)
        outputs.append(done.stdout)
    assert b".assess." in outputs[0] and outputs[0] == outputs[1] == outputs[2]


def test_annotation_order_changes_only_annotation_ids(aer: AerDocument) -> None:
    """Reordering annotations renumbers them (``a0, a1, …``), so the SEM digest and annotation ids change; the claims,
    their subjects and classes do not."""
    anns = [ann("m2#0", "integrity", "untrusted", "I", "integrity_table", [("te0", "/name")]),
            ann("te1", "role", ["send_sink"], "I", "sink_tools", [("te1", "/name")]),
            ann("m0#0", "integrity", "trusted", "I", "integrity_table", [])]

    def claims_of(result: ProvDerivation) -> list[tuple[str, str, str]]:
        _, bundle = assess(result)
        return sorted((b.get("apv:claim", {}).get("$", "mention"), b.get("apv:subject", {}).get("$", ""),
                       b["apv:evidenceClass"]["$"]) for b in bundle["entity"].values())

    assert claims_of(run(aer, anns)) == claims_of(run(aer, list(reversed(anns))))
