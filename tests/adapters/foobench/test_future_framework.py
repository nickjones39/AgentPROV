"""The future-framework test (docs/architecture D.12.3, K.6.4; DoD Q.3): FooBench lands with zero core changes.

Import the fixture, derive PROV, and assert by rule id:

1. the protected set is untouched, and the new adapter uses only specialised kinds where they fit (K.6.4 items 1, 2);
2. the named statements of D.12.2 for every row, each with its rule and in the bundle its evidence class dictates (item 3);
3. the named, disclosed gaps, with **no** PROV statement emitted for them (item 4);
4. the AER validates (tier 2) and the PROV bundles pass tier 4 (item 5).

Phase 6 ran map -> PROV -> validate on the core and inference bundles. Phase 7 extends it to map -> SEM -> PROV -> validate
(K.6.4 item 6): the ``foobench.toy@1`` SEM file validates (tier 3), the assessment bundle holds the labels of the text
action ``te5`` and, per DECISIONS D-16, **no** exposure or taint for it (a request-less execution has no generating
invocation, EF E.7.3), and every bundle passes tier 4.

Three gaps found by this test were closed by one core change made before FooBench landed (commit "Core: discover
adapter families from package data"): profiles and rule catalogues are found by convention, and the runner supplies
auxiliary artefacts. The three tests below run unpatched, in a fresh interpreter where it matters.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov.aer.reader import load_aer
from agentprov.aer.validate import validate_records
from agentprov.prov.engine import ProvDerivation, derive
from agentprov.validate.prov import validate_prov

REPO = Path(__file__).resolve().parents[3]
OBSERVED, DERIVED, INFERRED = "apv:Observed", "apv:Derived", "apv:Inferred"

#: D.12.1: the files the adding commit may touch. `tools/gen_foobench_fixture.py` generates the fixture of row 8, and the
#: one existing registry test that lists the registered sources is updated for the one registry entry (row 10).
ALLOWED_PREFIXES = (
    "src/agentprov/adapters/foobench/",
    "tests/fixtures/foobench/",
    "tests/adapters/foobench/",
)
ALLOWED_FILES = frozenset(
    {
        "src/agentprov/adapters/registry/__init__.py",
        "tools/gen_foobench_fixture.py",
        "tests/adapters/adprov/test_registry_entry.py",
    }
)


# ------------------------------------------------------------------------------------------------ PROV helpers
def statements(result: ProvDerivation) -> list[dict[str, Any]]:
    out = []
    for iri, bundle in result.document["bundle"].items():
        kind = "core" if ".core." in iri else "inf"
        for section, items in bundle.items():
            for ident, body in items.items():
                out.append({"bundle": kind, "section": section, "id": ident, **body})
    return out


def find(result: ProvDerivation, section: str, rule: str | None = None, **args: str) -> list[dict[str, Any]]:
    keys = {k.replace("__", ":"): v for k, v in args.items()}
    return [
        s for s in statements(result)
        if s["section"] == section and (rule is None or s.get("apv:rule") == rule) and all(s.get(k) == v for k, v in keys.items())
    ]  # fmt: skip


def one(result: ProvDerivation, section: str, rule: str, *, bundle: str = "core", cls: tuple[str, ...] = (OBSERVED, DERIVED), **args: str) -> dict[str, Any]:
    """Exactly one statement with this rule and these arguments, in the bundle and at the evidence class the engine routes it to."""
    found = find(result, section, rule, **args)
    assert len(found) == 1, (section, rule, args, len(found))
    (stmt,) = found
    assert stmt["bundle"] == bundle, (rule, args, stmt["bundle"])
    if "apv:evidenceClass" in stmt:
        assert stmt["apv:evidenceClass"]["$"] in cls, (rule, args, stmt["apv:evidenceClass"])
    return stmt


def types_of(body: dict[str, Any]) -> set[str]:
    value = body.get("prov:type", [])
    return {v["$"] for v in (value if isinstance(value, list) else [value])}


def gaps(result: ProvDerivation, about: str) -> list[tuple[str, str]]:
    return [(g["apv:property"], g["apv:status"]["$"]) for g in find(result, "entity", "aprov.n_gap@1") if g["apv:about"]["$"] == about]


@pytest.fixture(scope="module")
def aer_path(mapped, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("foobench") / "trace-001.aer.jsonl"
    path.write_bytes(mapped.data)
    return path


@pytest.fixture(scope="module")
def doc(aer_path: Path):
    return load_aer(aer_path)


@pytest.fixture(scope="module")
def result(doc, foo) -> ProvDerivation:
    return derive(doc, registry=foo.registry())


# ------------------------------------------------------------------------------------------------ 1. protected set
def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_the_adapter_imports_only_the_stdlib_and_the_adapter_facing_core():
    """D.2.1 boundary: ``dialect`` and ``mapper`` (and the package) import the stdlib and ``agentprov.{ingest,aer,adapters}`` only.

    ``agentprov.errors`` is allowed as well: it is the home of the exception types of D.2.7. Nothing else of the protected
    set (``prov``, ``validate``, ``sem``, ``corpus``, ``cli``, ``views``, ``raw``, ``io``) is imported, and no benchmark package.
    """
    allowed_core = ("agentprov.ingest", "agentprov.aer", "agentprov.adapters", "agentprov.errors")
    package = REPO / "src" / "agentprov" / "adapters" / "foobench"
    files = sorted(package.glob("*.py"))
    assert [f.name for f in files] == ["__init__.py", "dialect.py", "mapper.py"]
    for path in files:
        for target in _imports(path):
            top = target.split(".")[0]
            if top == "agentprov":
                assert target == "agentprov" or target.startswith(allowed_core), f"{path.name} imports {target}"
            else:
                assert top in sys.stdlib_module_names or top == "__future__", f"{path.name} imports {target}"
    shared = ("agentprov.adapters.foobench", "agentprov.adapters.profiles", "agentprov.adapters.protocols", "agentprov.adapters.types")
    others = [t for p in files for t in _imports(p) if t.startswith("agentprov.adapters.") and not t.startswith(shared)]
    assert others == []  # no other adapter family (M.5.2(2))


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def test_the_commit_that_adds_the_adapter_changes_only_the_files_of_d121():
    """K.6.4 item 1: the diff of the commit that adds ``foobench`` touches nothing outside D.12.1's file list.

    The commit is found from the history (the oldest one that adds the package's ``__init__.py``), so this keeps passing
    after later commits change the core. It is skipped when there is no git history to read (an sdist, a shallow clone),
    the adapter is not committed yet, or the adding commit is a root commit (the public repository's fresh history starts
    with the whole tree, D-943 P-7). If the adapter is squashed together with other work, run it on the adapter's own commit.
    """
    added = _git("log", "--diff-filter=A", "--format=%H", "--", "src/agentprov/adapters/foobench/__init__.py")
    if added is None or not added.split():
        pytest.skip("no git history holds the commit that adds the foobench adapter")
    commit = added.split()[-1]
    if not (_git("show", "-s", "--format=%P", commit) or "").split():
        pytest.skip("the foobench adapter arrived in a root commit (an exported history): no diff of its own")
    changed = (_git("show", "--name-only", "--format=", commit) or "").split()
    assert changed, "the adding commit lists no files"
    outside = [p for p in changed if not (p.startswith(ALLOWED_PREFIXES) or p in ALLOWED_FILES)]
    assert outside == [], f"files outside the D.12.1 list changed in {commit[:10]}: {outside}"


def test_the_registry_holds_exactly_one_additive_foobench_entry():
    from agentprov.adapters.registry import MAPPERS, READERS, REGISTRY, get_source
    from agentprov.adapters.runner import resolve_factory

    assert [s.source_id for s in REGISTRY].count("foobench") == 1 and "adprov-v1" in [s.source_id for s in REGISTRY]  # one is added
    source = get_source("foobench")
    (part,) = source.capabilities
    assert part.import_status is None and part.live_status is None and part.caveat and "not a real source" in part.caveat
    assert READERS["foobench.jsonl"] == "agentprov.adapters.foobench.dialect:FooJsonlReader"
    assert MAPPERS["foobench.jsonl"] == "agentprov.adapters.foobench.mapper:FooMapper"
    assert resolve_factory(READERS["foobench.jsonl"]).dialect_id == "foobench.jsonl"
    assert resolve_factory(MAPPERS["foobench.jsonl"]).mapper_id == "foobench.jsonl"
    assert (source.family, part.profile, part.dialects, part.variants) == ("foobench", "foobench", ("foobench.jsonl",), ("v1",))


def _unpatched(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False, cwd=REPO)


def test_load_profile_resolves_foobench_without_a_core_change():
    done = _unpatched("from agentprov.adapters.profiles import load_profile; load_profile('foobench')")
    assert done.returncode == 0, done.stderr.strip().splitlines()[-1:]


def test_the_catalogue_homes_resolve_foobench_without_a_core_change():
    done = _unpatched("from agentprov.aer.rules import load_catalogue; load_catalogue('foobench', 1)")
    assert done.returncode == 0, done.stderr.strip().splitlines()[-1:]


def test_the_runner_context_opens_a_declared_auxiliary_file(foo, tmp_path):
    from agentprov.adapters.runner import MapContext
    from agentprov.aer.rules import RuleRegistry

    ctx = MapContext(foo.profile(), RuleRegistry.default(), "foobench.jsonl/foobench", "ex_x", {foo.SUB: foo.raw(foo.SUB)})
    assert ctx.open_auxiliary(foo.SUB) == foo.raw(foo.SUB)


# ------------------------------------------------------------------------------------------------ 2. specialised kinds first
def test_specialised_kinds_are_used_wherever_they_fit(mapped):
    kinds = [r["k"] for r in mapped.records]
    by = mapped.by_id()
    assert sum(k == "activity" for k in kinds) == 3 and sum(k == "artefact" for k in kinds) == 4
    assert [i for i, k in zip((r["id"] for r in mapped.records), kinds, strict=True) if k == "activity"] == ["ac0", "ac1", "ac2"]
    # model events -> model_call + message; tool events, the memory write, the hand-off, both approvals' executions and the
    # text action -> tool_execution; the guard and the approvals -> decision
    assert sorted(r["id"] for r in mapped.of_kind("tool_execution")) == [f"te{n}" for n in range(6)]
    assert {by[d]["actor"] for d in ("dc0", "dc3")} == {"def0"} and {by[d]["actor"] for d in ("dc1", "dc2")} == {"user"}
    assert {r["type"].split(":")[0] for r in mapped.of_kind("activity")} == {"foobench"}
    shadow = {"message", "model_call", "tool_execution", "decision", "state_change", "fixture", "judgement"}
    assert {r["type"].split(":", 1)[1] for r in mapped.records if r["k"] in ("activity", "artefact")}.isdisjoint(shadow)
    report = mapped.validate()
    assert "aer.activity.shadows_kind" not in {f.code for f in report.findings}


# ------------------------------------------------------------------------------------------------ 3. named statements
def test_llm_request_and_response(result):
    for index in range(7):
        one(result, "used", "aprov.use_context@1", prov__activity="x:mc3", prov__entity=f"x:m{index}", cls=(OBSERVED,))
    one(result, "wasGeneratedBy", "aprov.gen_message@1", prov__entity="x:m7", prov__activity="x:mc3")
    one(result, "wasAssociatedWith", "aprov.assoc_model_call@1", prov__activity="x:mc3", prov__agent="x:agent")
    one(result, "wasAssociatedWith", "aprov.assoc_model_call@1", prov__activity="x:mc1", prov__agent="x:agent")
    one(result, "used", "aprov.use_context@1", prov__activity="x:mc1", prov__entity="x:m0", cls=(OBSERVED,))


def test_tool_start_and_end(result):
    one(result, "used", "aprov.use_request@1", prov__activity="x:te0", prov__entity="x:m1-1")
    one(result, "wasGeneratedBy", "aprov.gen_result@1", prov__entity="x:m2-0", prov__activity="x:te0")
    one(result, "wasAssociatedWith", "aprov.assoc_tool@1", prov__activity="x:te0", prov__agent="x:env")


def test_guard_verdict_allow_and_deny(result):
    one(result, "wasAssociatedWith", "aprov.decision@1", prov__activity="x:dc0", prov__agent="x:def0")
    one(result, "used", "aprov.decision@1", prov__activity="x:dc0", prov__entity="x:m1-1")
    one(result, "wasAssociatedWith", "aprov.decision@1", prov__activity="x:dc3", prov__agent="x:def0")
    one(result, "used", "aprov.decision@1", prov__activity="x:dc3", prov__entity="x:m13-1")
    # a deny has no tool_execution: the only usage of the denied request is the decision's, and there is no te6 (NE-12)
    assert [u["prov:activity"] for u in find(result, "used", None, prov__entity="x:m13-1")] == ["x:dc3"]
    assert all(s.get("prov:activity") != "x:te6" and s.get("id") != "x:te6" for s in statements(result))
    assert find(result, "entity", "aprov.n_part@1", id="x:m13-1")[0]["apv:dispatchStatus"]["$"] == "apv:Denied"
    one(result, "wasGeneratedBy", "aprov.gen_result@1", prov__entity="x:m14-0", prov__activity="x:dc3")


def test_planner_step(result):
    one(result, "wasGeneratedBy", "aprov.gen_message@1", prov__entity="x:p0", prov__activity="x:mc0")
    one(result, "wasAssociatedWith", "aprov.assoc_model_call@1", prov__activity="x:mc0", prov__agent="x:planner")
    node = one(result, "activity", "aprov.g_act@1", id="x:ac0")
    assert types_of(node) == {"apv:GenericActivity"} and node["apv:activityType"] == "foobench:plan_step"
    use = one(result, "used", "aprov.g_use@1", prov__activity="x:ac0", prov__entity="x:p0", cls=(OBSERVED,))
    assert use["prov:role"]["$"] == "apv:ActivityInput"
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af0", prov__activity="x:ac0", cls=(OBSERVED,))
    assoc = one(result, "wasAssociatedWith", "aprov.g_assoc@1", prov__activity="x:ac0", prov__agent="x:harness")
    assert assoc["prov:role"]["$"] == "apv:PerformerRole"
    comm = one(result, "wasInformedBy", "aprov.comm@1", prov__informed="x:ac0", prov__informant="x:mc0")
    assert comm["apv:viaEntity"]["$"] == "x:p0" and {p["$"] for p in comm["apv:premise"]} == {
        s["id"] for s in find(result, "used", "aprov.g_use@1", prov__activity="x:ac0")
    } | {s["id"] for s in find(result, "wasGeneratedBy", "aprov.gen_message@1", prov__entity="x:p0")}
    assert find(result, "entity", "aprov.n_artefact@1", id="x:af0")[0]["apv:mediaType"] == "application/json"


def test_memory_write(result):
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af1", prov__activity="x:te1")
    state = one(result, "wasGeneratedBy", "aprov.state_patch@1", prov__entity="x:st0.after", prov__activity="x:te1")
    assert state["prov:activity"] == "x:te1"
    assert types_of(find(result, "entity", "aprov.n_artefact@1", id="x:af1")[0]) == {"apv:GenericArtefact"}
    assert find(result, "entity", "aprov.n_artefact@1", id="x:af1")[0]["apv:artefactType"] == "foobench:memory_item"


def test_memory_read_communicates_with_the_write_through_the_item(result):
    one(result, "used", "aprov.g_use@1", prov__activity="x:ac1", prov__entity="x:af1", cls=(DERIVED,))  # a key match: class D
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af2", prov__activity="x:ac1", cls=(OBSERVED,))
    one(result, "wasAssociatedWith", "aprov.g_assoc@1", prov__activity="x:ac1", prov__agent="x:harness")
    comm = one(result, "wasInformedBy", "aprov.comm@1", prov__informed="x:ac1", prov__informant="x:te1", cls=(DERIVED,))
    assert comm["apv:viaEntity"]["$"] == "x:af1"
    premises = {p["$"] for p in comm["apv:premise"]}
    both = {find(result, "used", "aprov.g_use@1", prov__activity="x:ac1")[0]["id"], find(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af1")[0]["id"]}
    assert premises == both and len(premises) == 2  # both premises: the read used the item, the write generated it


def test_screenshot_binds_the_blob_digest(mapped, result):
    node = one(result, "activity", "aprov.g_act@1", id="x:ac2")
    assert types_of(node) == {"apv:GenericActivity"} and node["apv:activityType"] == "foobench:observe"
    art = one(result, "entity", "aprov.n_artefact@1", id="x:af3")
    digest = mapped.by_id()["af3"]["content_ref"]["$blob"].removeprefix("sha256:")
    assert art["apv:contentSha256"] == digest == mapped.by_id()["af3"]["sha256"] and art["apv:mediaType"] == "image/png"
    one(result, "wasGeneratedBy", "aprov.g_gen@1", prov__entity="x:af3", prov__activity="x:ac2", cls=(OBSERVED,))
    one(result, "wasAssociatedWith", "aprov.g_assoc@1", prov__activity="x:ac2", prov__agent="x:env")
    assert find(result, "used", "aprov.g_use@1", prov__activity="x:ac2") == []  # inputs: []


def test_a_screenshot_digest_that_differs_from_the_blob_is_an_aer_error(mapped, foo):
    records = mapped.records
    next(r for r in records if r["id"] == "af3")["sha256"] = "0" * 64
    report = validate_records(records, store=mapped.store(), catalogues=foo.registry(), mode="dev")
    assert "aer.blob.digest" in {f.code for f in report.errors}


def test_hand_off_starts_the_sub_agent(result):
    start = one(result, "wasStartedBy", "aprov.spawn@1", prov__activity="x:sc0", prov__starter="x:te2")
    assert "prov:trigger" not in start
    one(result, "wasAssociatedWith", "aprov.assoc_model_call@1", prov__activity="x:mc2", prov__agent="x:researcher")
    one(result, "used", "aprov.use_request@1", prov__activity="x:te2", prov__entity="x:m1-3")
    assert types_of(one(result, "activity", "aprov.n_scope@1", id="x:sc0")) == {"apv:SubagentInvocation"}
    one(result, "wasGeneratedBy", "aprov.gen_result@1", prov__entity="x:m4-0", prov__activity="x:te2")  # the sub-agent's answer


def test_human_approval_approve(result):
    assoc = one(result, "wasAssociatedWith", "aprov.decision@1", prov__activity="x:dc1", prov__agent="x:user")
    assert assoc["prov:role"]["$"] == "apv:DeciderRole"
    one(result, "used", "aprov.decision@1", prov__activity="x:dc1", prov__entity="x:m7-1")
    start = one(result, "wasStartedBy", "aprov.authorise@1", prov__activity="x:te3", prov__starter="x:dc1")
    assert "prov:trigger" not in start and "AutoExecution" not in json.dumps(start)  # no apv:AutoExecution premise
    assert find(result, "wasStartedBy", "aprov.start_tool@1") == []  # authorise replaces start_tool for the execution
    one(result, "used", "aprov.use_request@1", prov__activity="x:te3", prov__entity="x:m7-1")


def test_human_approval_edit_is_a_disclosed_gap_ne18(result):
    assoc = one(result, "wasAssociatedWith", "aprov.decision@1", prov__activity="x:dc2", prov__agent="x:user")
    assert assoc["prov:role"]["$"] == "apv:DeciderRole"
    one(result, "used", "aprov.decision@1", prov__activity="x:dc2", prov__entity="x:m9-1")
    one(result, "wasStartedBy", "aprov.authorise@1", prov__activity="x:te4", prov__starter="x:dc2")


def test_text_parsed_action(result):
    one(result, "wasAssociatedWith", "aprov.assoc_tool@1", prov__activity="x:te5", prov__agent="x:env")
    deleg = one(result, "actedOnBehalfOf", "aprov.assoc_tool@1", prov__delegate="x:env", prov__responsible="x:agent", prov__activity="x:te5")
    assert "requested_by" in json.dumps(deleg["apv:rulePointer"])
    # the tool name is reconstructed (class I): the inference bundle holds it, the core activity does not
    core = find(result, "activity", "aprov.n_tool_execution@1", id="x:te5")[0]
    assert core["bundle"] == "core" and "apv:toolName" not in core
    (labelled,) = [s for s in statements(result) if s["bundle"] == "inf" and s["section"] == "entity"]
    assert labelled["apv:subject"]["$"] == "x:te5" and labelled["apv:toolName"] == "scroll" and labelled["apv:method"] == "foobench.text_action_parse@1"
    inference = [b for b in result.bundles if b.kind == "inference"]
    assert [b.methods for b in inference] == [("foobench.text_action_parse@1",)] and dict(inference[0].statements) == {"I": 1}


def test_core_holds_only_observed_and_derived_and_the_one_inference_bundle_only_inferred(result):
    for s in statements(result):
        cls = s.get("apv:evidenceClass", {}).get("$")
        if s["bundle"] == "core":
            assert cls in (None, OBSERVED, DERIVED), s["id"]
        else:
            assert cls in (None, INFERRED), s["id"]
    assert [b.kind for b in result.bundles] == ["core", "inference"]


# ------------------------------------------------------------------------------------------------ 4. disclosed gaps
def test_gap_ne18_on_the_edited_request_emits_no_used_statement(result):
    assert find(result, "used", "aprov.use_request@1", prov__activity="x:te4") == []
    assert [u["prov:activity"] for u in find(result, "used", None, prov__entity="x:m9-1")] == ["x:dc2"]  # only the decision used it
    assert gaps(result, "x:te4") == [("/call", "apv:NotRecorded")]  # recorded as a status
    ne18 = [d for d in result.report.disclosed if d["code"] == "ne18_modified_request"]
    assert [d["id"] for d in ne18] == ["te4"]


def test_gap_the_text_action_has_no_request_part_so_no_used_statement(result):
    assert find(result, "used", None, prov__activity="x:te5") == []
    assert gaps(result, "x:m12") == [] and ("m12/parts/0/responds_to", "apv:NotApplicable") in [
        (d["id"], d["detail"]) for d in result.report.disclosed
    ]


def test_gap_restore_and_telemetry_emit_no_statement_at_all(result, mapped):
    text = result.prov_json.decode("utf-8")
    for needle in ("telemetry", "checkpoint", "cp-1", "latency_ms", "counters"):  # the kept content never reaches PROV
        assert needle not in text, needle
    # the only trace of the two events is their seal issue code, listed on the capture-profile entity (apv:issue)
    mentioning = [s for s in statements(result) if "restore_unmodelled" in json.dumps(s) or "unmapped_event_type" in json.dumps(s)]
    assert [s["id"] for s in mentioning] == ["x:capture-profile"]
    assert {"foobench.restore_unmodelled", "foobench.unmapped_event_type"} <= set(mentioning[0]["apv:issue"])
    assert all("/ext" not in json.dumps(s.get("apv:sourcePointer", "")) for s in statements(result))  # ext is opaque to PROV
    codes = [i["code"] for i in mapped.issues]
    assert codes.count("foobench.restore_unmodelled") == 1 and codes.count("foobench.unmapped_event_type") == 1
    assert "ext" in mapped.by_id()["af0"] and "ext" in mapped.by_id()["m8"]  # kept in the AER, opaque to PROV


def test_gap_observation_messages_m5_and_m6_are_not_linked_to_their_artefacts(result, mapped):
    by = mapped.by_id()
    for message, artefact in (("m5", "af2"), ("m6", "af3")):
        assert by[message]["unk"] == {"/generated_by": "not_recorded"}
        assert gaps(result, f"x:{message}") == [("/generated_by", "apv:NotRecorded")]
        assert find(result, "wasGeneratedBy", None, prov__entity=f"x:{message}") == []
        related = [s for s in statements(result) if f'"x:{message}"' in json.dumps(s) and f'"x:{artefact}"' in json.dumps(s)]
        assert related == []  # no relation of the message to the artefact is asserted
    issues = [(i["code"], tuple(i["ids"])) for i in mapped.issues if i["code"] == "foobench.observation_unlinked"]
    assert issues == [("foobench.observation_unlinked", ("m5",)), ("foobench.observation_unlinked", ("m6",))]


# ------------------------------------------------------------------------------------------------ 5. validation
def test_the_aer_validates_tier_2_against_the_raw_files_and_the_blob(mapped):
    report = mapped.validate("release")
    assert report.passed and report.findings == ()
    assert {a["sha256"] for a in mapped.records[0]["artifacts"]} == {
        hashlib.sha256(mapped.primary).hexdigest(),
        hashlib.sha256(mapped.sub).hexdigest(),
    }


def test_the_prov_bundles_pass_tier_4(result, doc, foo):
    report = validate_prov(result.prov_json, doc, registry=foo.registry())
    failures = [(o.id, [f.code for f in o.findings]) for o in report.outcomes if o.status == "fail"]
    assert failures == [] and report.passed


def test_the_derivation_is_deterministic(doc, result, foo):
    again = derive(doc, registry=foo.registry())
    assert again.prov_json == result.prov_json and dict(again.digests) == dict(result.digests)


def test_the_protected_validators_accept_the_aer_without_the_store_too(doc, foo):
    report = validate_records([*doc.records, doc.seal], store=None, catalogues=foo.registry(), mode="dev")
    assert report.ok


# ------------------------------------------------------------------------------------------------ 6. phase 7: SEM and assessment
@pytest.fixture(scope="module")
def toy():
    from agentprov.adapters.semantics_profiles import load_semantics_profile

    return load_semantics_profile("foobench.toy", 1)


@pytest.fixture(scope="module")
def sem(doc, toy):
    from agentprov.sem.engine import annotate

    return annotate(doc, toy)


@pytest.fixture(scope="module")
def assessed(doc, sem, toy, foo) -> ProvDerivation:
    return derive(doc, [sem], registry=foo.registry(), sem_profiles={(toy.id, toy.version): toy})


def assessment(result: ProvDerivation) -> list[dict[str, Any]]:
    (iri,) = [i for i in result.document["bundle"] if ".assess." in i]
    return [{"section": section, "id": ident, **body}
            for section, items in result.document["bundle"][iri].items() for ident, body in items.items()]


def claims(result: ProvDerivation, claim: str) -> list[dict[str, Any]]:
    return [s for s in assessment(result) if s.get("apv:claim", {}).get("$") == claim]


def test_the_sem_file_passes_tier_3(sem, doc, toy, foo):
    from agentprov.sem.validate import validate_sem_document

    report = validate_sem_document(sem, doc, catalogues=foo.registry(), mode="release", profile=toy)
    assert report.ok and not report.errors, [f.code for f in report.errors]


def test_the_assessment_bundle_is_the_one_new_bundle_and_core_is_unchanged(result, assessed):
    kinds = sorted(b.kind for b in assessed.bundles)
    assert kinds == sorted([*(b.kind for b in result.bundles), "assessment"])
    (bundle,) = [b for b in assessed.bundles if b.kind == "assessment"]
    assert bundle.profile == "foobench.toy@1"
    core = {b.kind: dict(b.statements) for b in result.bundles}
    assert {b.kind: dict(b.statements) for b in assessed.bundles if b.kind != "assessment"} == core


def test_text_parsed_action_is_labelled_but_has_no_exposure_d16(assessed):
    labelled = [s for s in claims(assessed, "apv:Labelled") if s["apv:subject"]["$"] == "x:te5"]
    assert len(labelled) == 1 and labelled[0]["apv:securityRole"]["$"] == "apv:Neutral"
    for claim in ("apv:ExposedTo", "apv:PotentiallyInfluencedBy"):
        assert not [s for s in claims(assessed, claim) if "te5" in json.dumps(s["apv:subject"])], claim
    (counts,) = assessed.report.assessment.values()
    assert counts["exposure_no_request"] >= 1  # te5 and the other request-less executions, counted (EF E.7.3)


def test_exposures_and_taints_are_materialised_for_requests_with_context(assessed):
    exposures, taints = claims(assessed, "apv:ExposedTo"), claims(assessed, "apv:PotentiallyInfluencedBy")
    assert exposures and all(s["apv:subject"]["$"].startswith("x:m") for s in exposures)  # request parts, never executions
    assert all(s["apv:policy"] == "foobench.taint_sink_untrusted@1" for s in taints)
    assert {s["apv:evidenceClass"]["$"] for s in taints} <= {INFERRED}


def test_the_assessment_bundle_uses_only_the_allowed_forms(assessed):
    allowed = {"entity", "activity", "agent", "wasGeneratedBy", "wasAssociatedWith", "mentionOf"}
    assert {s["section"] for s in assessment(assessed)} <= allowed


def test_every_bundle_passes_tier_4_with_the_sem(assessed, doc, sem, foo):
    report = validate_prov(assessed.prov_json, doc, registry=foo.registry(), sems=[sem])
    failures = [(o.id, [f.code for f in o.findings]) for o in report.outcomes if o.status == "fail"]
    assert failures == [] and report.passed


def test_the_derivation_with_sem_is_deterministic(doc, sem, toy, foo, assessed):
    again = derive(doc, [sem], registry=foo.registry(), sem_profiles={(toy.id, toy.version): toy})
    assert again.prov_json == assessed.prov_json
