"""The ``foobench.toy@1`` semantics profile (docs/architecture D.12.1 row 7; C.14.1-C.14.3; EF E.7; DECISIONS D-16).

The profile is discovered by convention (``agentprov.adapters.semantics_profiles.load_semantics_profile``), reads only the AER and yields
class-I annotations from its tool, artefact and observation tables. Fail-closed: a tool or artefact type outside the
tables is ``unknown``. FooBench records no judgement, so there is no ``outcome``. The text-parsed action ``te5`` is
labelled like any execution (the engine, not the profile, withholds its exposure, D-16).
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.registry import get_source
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import load_catalogue
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.sem.profiles import parse_profile_ref, profile_digest
from agentprov.sem.types import (
    INTEGRITY_VALUES,
    ROLE_VALUES,
    SINK_ROLES,
    Annotation,
    SemanticsProfile,
)

PACKAGE = "agentprov.adapters.foobench"
SEMANTICS = Path(__file__).resolve().parents[3] / "src" / "agentprov" / "adapters" / "foobench" / "semantics"
DECLARED = {
    "foobench.tool_role_table@1", "foobench.tool_output_label_table@1", "foobench.artefact_label_table@1",
    "foobench.observation_label_table@1", "foobench.taint_sink_untrusted@1",
}  # fmt: skip
#: C.14.3 allowed targets by annotation type: part kinds (``t``) or record kinds (``k``).
CONTENT_PARTS = {"text", "reasoning", "tool_call", "tool_result", "blob", "file", "uri", "refusal", "other"}


def profile() -> SemanticsProfile:
    return load_semantics_profile("foobench.toy", 1)


def annotate(data: bytes) -> tuple[AerDocument, list[Annotation]]:
    doc = load_aer_bytes(data)
    return doc, list(profile().annotate(doc))


@pytest.fixture(scope="module")
def sem(mapped) -> tuple[AerDocument, list[Annotation]]:
    return annotate(mapped.data)


def on(anns: list[Annotation], target: str, type_: str) -> list[Annotation]:
    return [a for a in anns if a.target == target and a.type == type_]


def one(anns: list[Annotation], target: str, type_: str) -> Annotation:
    (found,) = on(anns, target, type_)
    return found


def kind_of(doc: AerDocument, target: str) -> tuple[str, str | None]:
    """(record kind, part kind) of an annotation target; the target must exist."""
    if "#" in target:
        part = doc.part(target)
        assert part is not None, target
        return "part", str(part["t"])
    record = doc.get(target)
    assert record is not None, target
    return str(record["k"]), None


def test_the_profile_is_found_by_convention_and_digests_its_data_files():
    prof = profile()
    assert isinstance(prof, SemanticsProfile)
    assert (prof.id, prof.version, dict(prof.rules), dict(prof.ns)) == ("foobench.toy", 1, {"foobench": 1}, {})
    assert parse_profile_ref("foobench.toy@1") == ("foobench.toy", 1)
    files = {p.relative_to(SEMANTICS / "foobench.toy-1").as_posix(): p.read_bytes()
             for p in (SEMANTICS / "foobench.toy-1").rglob("*") if p.is_file()}
    assert set(files) == {"tables.toml"} and prof.sha256 == profile_digest(files)


def test_annotate_is_deterministic_and_stable_across_loads(mapped, sem):
    again = annotate(mapped.data)[1]
    assert again == sem[1] and list(load_semantics_profile("foobench.toy", 1).annotate(load_aer_bytes(mapped.data))) == again
    # roles: 6 executions + 6 request parts; integrity: 6 tool results + 4 artefacts + 2 inserted observations;
    # channel: 4 tool results + 3 artefacts
    assert Counter(a.type for a in sem[1]) == Counter({"role": 12, "integrity": 12, "channel": 7})


def test_every_target_exists_with_an_allowed_kind_and_every_value_is_in_the_closed_vocabulary(sem):
    doc, anns = sem
    assert anns and {a.type for a in anns} == {"integrity", "channel", "role"}
    for a in anns:
        record, part = kind_of(doc, a.target)
        if a.type == "integrity":
            assert (record, part) in {("part", p) for p in CONTENT_PARTS} | {("artefact", None), ("fixture", None)}
            assert a.value in INTEGRITY_VALUES
        elif a.type == "channel":
            assert (record, part) in {("part", "tool_result"), ("artefact", None)}
            assert isinstance(a.value, str) and a.value
        else:
            assert (record, part) in {("part", "tool_call"), ("tool_execution", None), ("activity", None)}
            assert isinstance(a.value, list) and a.value and set(a.value) <= set(ROLE_VALUES)
            assert "unknown" not in a.value or a.value == ["unknown"]  # unknown never mixes with a known role
        assert a.at is None and a.span is None and a.method is None and a.confidence is None
        for premise in a.premises:  # every premise reads an existing record
            assert doc.get(premise.id) is not None, premise


def test_every_cited_rule_is_declared_citable_and_matches_the_evidence_class(sem):
    cat = load_catalogue("foobench", 1, package=PACKAGE)
    cited: set[str] = set()
    for a in sem[1]:
        assert a.rule and a.ev in ("D", "I")
        for ref in a.rule:
            rid = ref.split("#", 1)[0]
            entry = cat.get(rid)
            assert entry is not None and entry.citable and entry.status == "active", rid
            assert entry.cls == a.ev == "I", rid  # table lookups are inferred; O would need a source-recorded label
            cited.add(rid)
    policy = profile().taint_policy
    assert policy is not None and cat.get(policy.rule) is not None and cat.get(policy.rule).cls == "I"  # type: ignore[union-attr]
    assert cited | {policy.rule} == DECLARED and DECLARED <= set(cat.rules)
    source = (SEMANTICS / "__init__.py").read_text(encoding="utf-8")
    assert set(re.findall(r'"(foobench\.[a-z_]+@[0-9]+)"', source)) == DECLARED


def test_roles_follow_the_tool_table_and_unknown_tools_fail_closed(foo, mapped, sem):
    doc, anns = sem
    roles = {te["name"]: one(anns, te["id"], "role").value for te in mapped.of_kind("tool_execution")}
    assert roles == {
        "lookup": ["content_source"], "save_memory": ["write_sink"], "transfer_to_researcher": ["execute_sink"],
        "click": ["execute_sink"], "send_note": ["send_sink"], "scroll": ["neutral"],
    }  # fmt: skip
    for te in mapped.of_kind("tool_execution"):  # the request part carries the same roles as its execution
        if "call" in te:
            assert one(anns, te["call"], "role").value == one(anns, te["id"], "role").value
    # the call the guard denied has no execution but its request part is labelled, by name: fail-closed
    assert one(anns, "m13#1", "role").value == ["unknown"] and doc.part("m13#1")["name"] == "delete_file"  # type: ignore[index]
    # unlisted names, as executions (a tool and a text action) and as request parts
    events = foo.events(foo.raw(foo.PRIMARY))
    for e in events:
        if e.get("name") == "send_note":
            e["name"] = "wire_money"
        for call in (e["reply"].get("calls", []) if isinstance(e.get("reply"), dict) else []):
            if call["name"] == "send_note":
                call["name"] = "wire_money"
        if e.get("type") == "text_action":
            e["raw"] = "wipe(direction=down)"
    changed = foo.map(foo.lines(events))
    cdoc, canns = annotate(changed.data)
    names = {te["name"]: te["id"] for te in changed.of_kind("tool_execution")}
    assert {"wire_money", "wipe"} <= set(names)
    for name in ("wire_money", "wipe"):
        assert one(canns, names[name], "role").value == ["unknown"]
    (call_part,) = [a for a in canns if a.type == "role" and cdoc.part(a.target) and cdoc.part(a.target).get("name") == "wire_money"]  # type: ignore[union-attr]
    assert call_part.value == ["unknown"]
    # an unlisted tool's output is unknown, never defaulted to trusted
    for name in ("wire_money", "wipe"):
        (result,) = [m for m in changed.of_kind("message") if m.get("generated_by") == names[name]]
        assert one(canns, f"{result['id']}#0", "integrity").value == "unknown"
        assert on(canns, f"{result['id']}#0", "channel") == []


def test_the_text_action_is_labelled_like_any_execution(mapped, sem):
    _, anns = sem
    te5 = mapped.by_id()["te5"]
    assert te5["name"] == "scroll" and "call" not in te5 and te5["requested_by"] == "agent"
    role = one(anns, "te5", "role")
    assert (role.value, role.ev, role.rule) == (["neutral"], "I", ("foobench.tool_role_table@1",))
    assert [(p.id, p.p) for p in role.premises] == [("te5", "/name")]
    result = next(m for m in mapped.of_kind("message") if m.get("generated_by") == "te5")
    assert one(anns, f"{result['id']}#0", "integrity").value == "unknown"
    assert one(anns, f"{result['id']}#0", "channel").value == "web"


def test_tool_outputs_are_labelled_from_the_tool_table(mapped, sem):
    _, anns = sem
    expected = {
        "lookup": ("untrusted", "document"), "save_memory": ("trusted", None),
        "transfer_to_researcher": ("unknown", "message"), "click": ("unknown", "web"), "send_note": ("trusted", None),
        "scroll": ("unknown", "web"),
    }  # fmt: skip
    tools = {te["id"]: te["name"] for te in mapped.of_kind("tool_execution")}
    results = [m for m in mapped.of_kind("message") if m.get("generated_by") in tools]
    assert len(results) == len(tools) == 6
    for m in results:
        integrity, channel = expected[tools[m["generated_by"]]]
        target = f"{m['id']}#0"
        assert one(anns, target, "integrity").value == integrity
        assert [a.value for a in on(anns, target, "channel")] == ([channel] if channel else [])
        assert one(anns, target, "integrity").premises[0].id == m["generated_by"]
    # the guard's replacement (generated by a decision) is not tool output: no label, no claim
    guard = next(m for m in mapped.of_kind("message") if str(m.get("generated_by", "")).startswith("dc"))
    assert not [a for a in anns if a.target.startswith(f"{guard['id']}#")]


def test_artefacts_are_labelled_from_their_type(foo, mapped, sem):
    _, anns = sem
    expected = {
        "foobench:plan": ("unknown", None), "foobench:memory_item": ("unknown", "memory"),
        "foobench:memory_snippet": ("unknown", "memory"), "foobench:screenshot": ("untrusted", "screen"),
    }  # fmt: skip
    arts = mapped.of_kind("artefact")
    assert {a["type"] for a in arts} == set(expected)
    for art in arts:
        integrity, channel = expected[art["type"]]
        assert one(anns, art["id"], "integrity").value == integrity
        assert [a.value for a in on(anns, art["id"], "channel")] == ([channel] if channel else [])
    # fail-closed: an artefact of a type outside the table is unknown (profile built over the fixture's types only)
    doc, _ = sem
    odd = {**doc.of_kind("artefact")[0], "type": "foobench:unlisted"}
    stub = AerDocument(doc.header, [odd], doc.seal, doc.execution_digest, doc.file_sha256)
    assert [(a.type, a.value) for a in profile().annotate(stub)] == [("integrity", "unknown")]


def test_inserted_observations_are_labelled_by_their_actor(mapped, sem):
    _, anns = sem
    by_id = mapped.by_id()
    assert (by_id["m5"]["actor"], by_id["m5"]["role"], by_id["m6"]["actor"], by_id["m6"]["role"]) == ("harness", "user", "env", "user")
    # integrity only: C.14.3 allows a channel on tool_result parts and artefacts, not on these text and blob parts
    assert [(a.value, a.rule) for a in [a for a in anns if a.target == "m5#0"]] == [
        ("unknown", ("foobench.observation_label_table@1",))]
    assert [(a.type, a.value) for a in anns if a.target == "m6#0"] == [("integrity", "untrusted")]
    # user, agent and sub-agent prompts and assistant text are not labelled: no table justifies a claim about them
    labelled = {a.target.split("#")[0] for a in anns if a.type in ("integrity", "channel")}
    assert not labelled & {"m0", "sm0", "m1", "m7", "p0"}
    assert by_id["m0"]["actor"] == "user"


def test_the_taint_policy_is_sinks_and_unknown_over_untrusted_and_unknown():
    policy = profile().taint_policy
    assert policy is not None and policy.rule == "foobench.taint_sink_untrusted@1"
    assert policy.subject_roles == SINK_ROLES | {"unknown"} and policy.object_integrity == {"untrusted", "unknown"}


def test_foobench_records_no_judgement_so_there_is_no_outcome(mapped, sem):
    assert mapped.of_kind("judgement") == [] and not [a for a in sem[1] if a.type == "outcome"]


def test_the_registry_part_declares_the_profile():
    (part,) = get_source("foobench").capabilities
    assert part.part == "fixture" and part.semantics == ("foobench.toy@1",)
    assert all(parse_profile_ref(ref) == ("foobench.toy", 1) for ref in part.semantics)


def test_the_unused_annotation_order_is_the_aer_record_order(sem: tuple[AerDocument, list[Any]]):
    doc, anns = sem
    order = {r["id"]: i for i, r in enumerate(doc.records)}
    positions = [order[a.target.split("#")[0]] for a in anns]
    assert positions == sorted(positions)  # one pass over the AER in file order


def test_the_sem_document_seals_and_passes_the_tier3_validator(sem):
    """End to end through the SEM engine and validator (C.14.4), with the profile's own declarations."""
    from agentprov.sem.engine import annotate as sem_annotate
    from agentprov.sem.engine import dumps_sem
    from agentprov.sem.reader import load_sem_bytes
    from agentprov.sem.validate import validate_sem_document

    doc, _anns = sem
    prof = profile()
    document = sem_annotate(doc, prof)
    assert load_sem_bytes(dumps_sem(document)).digest == document.digest
    report = validate_sem_document(document, doc, mode="release", profile=prof)
    assert report.ok and not report.errors, [f.code for f in report.errors]
