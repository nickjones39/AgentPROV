"""The pre-check's Level-2 checks (``tools/precheck/l2_check.py``) on synthetic in-memory data only: the A3 PI classes of
a hand-made PROV document, the evidence-class census, identity pairs against L1 facets, outcome rates with Wilson
intervals, the label resolver over origins, and the redaction scan (counts and pointers, never values)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "precheck"
CORE = "xd:bundle.core." + "a" * 26
INF = "xd:bundle.inf.fam-thing_unverified-v1." + "b" * 26
ASSESS = "xd:bundle.assess.fam-v1." + "c" * 26


@pytest.fixture(scope="module")
def lc():
    sys.path.insert(0, str(TOOLS))
    try:
        import l2_check

        yield l2_check
    finally:
        sys.path.remove(str(TOOLS))


def q(name: str) -> dict[str, str]:
    return {"$": name, "type": "prov:QUALIFIED_NAME"}


def ev(letter: str) -> dict[str, Any]:
    return {"apv:evidenceClass": q({"O": "apv:Observed", "D": "apv:Derived", "I": "apv:Inferred"}[letter])}


class FakeAer:
    def __init__(self, records: list[dict[str, Any]], issues: list[dict[str, Any]] | None = None,
                 task: dict[str, Any] | None = None) -> None:
        self.header = {"k": "execution", "id": "exec", "rules": {}, "task": task or {}, "dialect": {"id": "agentdojo.tracelogger"}}
        self.records = [self.header, *records]
        self.seal = {"k": "seal", "issues": issues or []}

    def get(self, rid: str) -> dict[str, Any] | None:
        return next((r for r in self.records if r.get("id") == rid), None)

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("k") == kind]


def _doc() -> dict[str, Any]:
    core = {
        "entity": {"x:m1": {**ev("O"), "apv:rule": "aprov.n_message@1"},
                   "x:te0": {**ev("D"), "apv:rule": "aprov.n_tool_execution@1", "prov:startTime": "2026-01-01T00:00:00Z"}},
        "activity": {"x:mc0": {**ev("O"), "apv:rule": "aprov.n_model_call@1"},
                     "x:run": {**ev("O"), "apv:rule": "aprov.n_scope@1", "prov:startTime": "2026-01-01T00:00:00Z"}},
        "wasGeneratedBy": {"x:g1": {**ev("D"), "apv:rule": "aprov.gen_message@1", "prov:entity": "x:m1",
                                    "prov:activity": "x:mc0", "apv:basisRule": "zzz.not_declared@1"}},
        "used": {"x:u1": {**ev("D"), "apv:rule": "aprov.use_request@1", "prov:activity": "x:te0", "prov:entity": "x:nope"}},
        "wasInfluencedBy": {"x:w1": {**ev("I"), "apv:rule": "aprov.made_up@1", "prov:influencee": "x:m1",
                                     "prov:influencer": "x:mc0"}},
    }
    inference = {"wasInformedBy": {"x:c1": {**ev("I"), "apv:rule": "aprov.comm@1", "prov:informed": "x:mc0",
                                            "prov:informant": "x:mc0"}}}
    assess = {"used": {"x:a1": {**ev("I"), "apv:rule": "aprov.a_label@1", "prov:activity": "x:mc0", "prov:entity": "x:m1"}}}
    return {"prefix": {}, "entity": {CORE: {"prov:type": q("apv:CoreBundle")}, INF: {"prov:type": q("apv:InferenceBundle")},
                                     ASSESS: {"prov:type": q("apv:AssessmentBundle")}},
            "bundle": {CORE: core, INF: inference, ASSESS: assess}}


def _aer() -> FakeAer:
    return FakeAer([
        {"k": "scope", "id": "run", "kind": "run", "ev": "O"},
        {"k": "message", "id": "m1", "role": "assistant", "generated_by": "mc0"},
        {"k": "message", "id": "m2", "role": "assistant", "generated_by": "mc0"},
        {"k": "model_call", "id": "mc0", "input": ["m0"]},
        {"k": "tool_execution", "id": "te0", "call": "m1#0", "ev": "D", "evf": {"/t/start": "I"}},
    ], issues=[{"code": "unexecuted_tool_call", "ids": ["m1#1"], "rule": "aer.x@1"}])


def test_pi_classes_of_a_synthetic_document(lc) -> None:
    from agentprov.aer.rules import RuleRegistry
    from agentprov.prov.specs import load_spec

    stats = lc.ProvStats(set(load_spec().rules), RuleRegistry.default())
    stats.add("ex_test", "runs/a.json", _doc(), _aer())
    out = stats.to_json()
    a3 = out["a3"]
    assert a3["dangling"]["by"] == {"used:prov:entity": 1}
    assert a3["missing_generation"]["count"] == 1  # m2 has generated_by but no wasGeneratedBy
    assert a3["missing_use_input"]["count"] == 1  # mc0 has inputs, no used by x:mc0
    assert "missing_use_request" not in a3  # te0 is used
    assert a3["forbidden"]["by"] == {"wasInfluencedBy": 1, "assessment:used": 1}
    assert a3["invented"]["by"] == {"rule:aprov.made_up@1": 1, "basis_unresolved:zzz.not_declared@1": 1}
    assert a3["time_not_run_scope"]["by"] == {"entity:tool_execution": 1}
    assert a3["time_inferred"]["count"] == 1  # the AER start of te0 is class I: never a PROV time
    assert a3["time_run_scope"]["count"] == 1
    assert a3["unexecuted_missing"]["by"] == {"no_node": 1}
    assert out["checked"]["messages_with_generated_by"] == 2 and out["checked"]["unexecuted_call_parts"] == 1
    assert out["evidence_by_bundle_class"]["core:O"] == 3
    # CC-08: "fam-thing_unverified" restates no catalogued D rule, so it counts as a native _unverified rule
    assert out["unverified_twin_by_bundle_class"] == {}
    assert out["native_unverified_rule_by_bundle_class"] == {"inference:I": 1}


def test_unexecuted_part_represented(lc) -> None:
    from agentprov.aer.rules import RuleRegistry
    from agentprov.prov.specs import load_spec

    doc = _doc()
    doc["bundle"][CORE]["entity"]["x:m1-1"] = {**ev("O"), "apv:rule": "aprov.n_part@1",
                                                "apv:dispatchStatus": q("apv:NotDispatched")}
    stats = lc.ProvStats(set(load_spec().rules), RuleRegistry.default())
    stats.add("ex_test", None, doc, _aer())
    assert "unexecuted_missing" not in stats.to_json()["a3"] and stats.pi["unexecuted_represented"] == 1
    assert stats.to_json()["a3"]["unexecuted_represented"]["by"] == {"core": 1}


def test_unexecuted_part_represented_in_an_inference_mention(lc) -> None:
    """POST-tool-01: after D-80 addendum (d) the status sits in an inference-bundle mention of a node the core declares
    without it (the unexecuted rule's ``_unverified`` twin); before the fix A3 read only the first (core) element."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.prov.specs import load_spec

    doc = _doc()
    doc["bundle"][CORE]["entity"]["x:m1-1"] = {**ev("O"), "apv:rule": "aprov.n_part@1"}
    doc["bundle"][INF]["entity"] = {"x:m1-1": {"apv:dispatchStatus": q("apv:NotDispatched")}}
    stats = lc.ProvStats(set(load_spec().rules), RuleRegistry.default())
    stats.add("ex_test", None, doc, _aer())
    a3 = stats.to_json()["a3"]
    assert "unexecuted_missing" not in a3 and a3["unexecuted_represented"]["by"] == {"inference": 1}


def test_unexecuted_status_elsewhere_is_still_missing(lc) -> None:
    """Only core and inference bundles represent dispatch; an assessment mention or another status does not."""
    from agentprov.aer.rules import RuleRegistry
    from agentprov.prov.specs import load_spec

    doc = _doc()
    doc["bundle"][CORE]["entity"]["x:m1-1"] = {**ev("O"), "apv:rule": "aprov.n_part@1",
                                                "apv:dispatchStatus": q("apv:Dispatched")}
    doc["bundle"][ASSESS]["entity"] = {"x:m1-1": {"apv:dispatchStatus": q("apv:NotDispatched")}}
    stats = lc.ProvStats(set(load_spec().rules), RuleRegistry.default())
    stats.add("ex_test", None, doc, _aer())
    a3 = stats.to_json()["a3"]
    assert a3["unexecuted_missing"]["by"] == {"apv:Dispatched": 1} and "unexecuted_represented" not in a3


def test_identity_of_and_census(lc) -> None:
    aer = FakeAer([{"k": "actor", "id": "agent", "kind": "llm_agent", "model": {"requested": "gpt-4o-2024-05-13"}}],
                  task={"suite": "banking", "attack_id": "important_instructions", "defense_id": None, "task_id": "user_task_1"})
    ident = lc.identity_of(aer)
    assert ident == {"model": "gpt-4o-2024-05-13", "defence": "none", "attack": "important_instructions",
                     "suite": "banking", "task": "user_task_1", "benchmark": "none"}
    info = lc.SampleInfo(None, None)
    info.rows = {
        "a.json": {"facets": {"suite": "banking", "attack_dir": "important_instructions", "pipeline_dir": "gpt-4o-x"}},
        "b.json": {"facets": {"suite": "slack", "attack_dir": "<none>", "pipeline_dir": "gpt-4o-x"}},
    }
    other = dict(ident, suite="banking", attack="none", model="gpt-4o-mini")
    census = lc.identity_census([("a.json", ident), ("b.json", other)], info)
    assert census["direct_mismatches"]["counts"] == {"suite": 1}  # attack <none> == none
    assert census["pairs_l1_to_aer"]["model<-pipeline_dir"] == {"gpt-4o-x -> gpt-4o-2024-05-13": 1,
                                                               "gpt-4o-x -> gpt-4o-mini": 1}
    assert census["l1_values_mapping_to_several_aer_values"]["model<-pipeline_dir"] == {"gpt-4o-x": 2}


def test_local_path_model_is_masked(lc) -> None:
    aer = FakeAer([{"k": "actor", "id": "agent", "kind": "llm_agent", "model": {"requested": "vllm//home/someone/ckpt"}}])
    assert lc.identity_of(aer)["model"] == "<account-path>"


def test_outcomes_and_wilson(lc) -> None:
    out = lc.Outcomes()
    base = {"model": "m", "defence": "none", "attack": "important_instructions", "suite": "s", "task": "user_task_0"}
    for i in range(10):
        out.add(base, "agentdojo.tracelogger", {"utility": i < 4, "security": i < 2}, 0)
    out.add(dict(base, task="injection_task_1"), "agentdojo.tracelogger", {"utility": True, "security": True}, 0)
    out.add(dict(base, attack="none"), "agentdojo.tracelogger", {"utility": True}, 1)
    arms = out.to_json()["arms"]
    attacked = arms["m|none|important_instructions"]
    assert attacked["attack_success"]["k"] == 2 and attacked["attack_success"]["n"] == 10
    assert attacked["utility_user_tasks"]["n"] == 10 and attacked["prepass_runs"] == 1
    low, high = attacked["attack_success"]["wilson95"]
    assert 0.05 < low < 0.06 and 0.50 < high < 0.52
    assert "attack_success" not in arms["m|none|none"]
    assert out.to_json()["harness_default_judgements_excluded"] == 1


def test_judgements_latest_and_defaults(lc) -> None:
    aer = FakeAer([
        {"k": "judgement", "id": "j0", "name": "utility", "value": False, "origin": "checker"},
        {"k": "judgement", "id": "j1", "name": "utility", "value": True, "origin": "recomputed", "revises": "j0"},
        {"k": "judgement", "id": "j2", "name": "security", "value": True, "origin": "harness_default"},
        {"k": "judgement", "id": "j3", "name": "score", "value": 0.5, "origin": "checker"},
    ])
    values, defaults = lc.judgements_of(aer)
    assert values == {"utility": True} and defaults == 1


def test_label_resolver(lc) -> None:
    def origin(kind: str, **data: Any) -> Any:
        return SimpleNamespace(kind=kind, data=data)

    rows = [
        SimpleNamespace(sha256="c" * 64, origin=origin("git", path="logs/run.eval")),
        SimpleNamespace(sha256="d" * 64, origin=origin("member", container="c" * 64, label="samples/1_epoch_1.json")),
        SimpleNamespace(sha256="e" * 64, origin=origin("zenodo", doi="10.5281/x", file="deposit.zip")),
        SimpleNamespace(sha256="f" * 64, origin=origin("member", container="e" * 64, label="a/runs.jsonl")),
        SimpleNamespace(sha256="1" * 64, origin=origin("local", path="/tmp/tree/x/y.json")),
    ]
    info = lc.SampleInfo(None, None)
    info.labels = {"logs/run.eval", "a/runs.jsonl", "x/y.json"}
    resolve = lc.LabelResolver(rows, info)
    assert resolve("d" * 64) == "logs/run.eval"  # a sample member of a container unit
    assert resolve("f" * 64) == "a/runs.jsonl"  # a member of a top-level archive input: its own label
    assert resolve("1" * 64) == "x/y.json"
    info.by_sha["9" * 64] = "from/l1.json"
    assert resolve("9" * 64) == "from/l1.json"


def test_redaction_counts_pointers_only(lc, tmp_path: Path) -> None:
    aer = tmp_path / "ex.aer.jsonl"
    record = {"k": "message", "id": "m0", "parts": [{"t": "text", "text": "see /home/sandbox/x and AKIA" + "A" * 16}]}
    aer.write_text(json.dumps(record) + "\n", encoding="utf-8")
    prov = tmp_path / "ex.prov.json"
    prov.write_text(json.dumps({"bundle": {"xd:b1": {"entity": {"x:m0": {"apv:path": "/Users/someone/tmp/f"}}}}}),
                    encoding="utf-8")
    red = lc.Redaction()
    red.scan_file("aer", aer, "ex_aaaaaaaaaaaaaaaaaaaaaaaaaa")
    red.scan_file("prov", prov, None)
    out = red.to_json()
    assert out["hits"]["aer"] == {"account-path message:/parts/*/text": 1,
                                  "secret:aws-access-key-id message:/parts/*/text": 1}
    assert out["hits"]["prov"] == {"account-path /bundle/{k}/entity/{k}/apv:path": 1}
    assert out["executions_hit"] == {"aer": 1}
    assert "/home/sandbox" not in json.dumps(out) and "AKIA" not in json.dumps(out)


def test_degenerate_codes(lc) -> None:
    assert lc.degenerate_of(["map.adapter_defect"]) and lc.degenerate_of(["unparseable_artefact"])
    assert not lc.degenerate_of(["map.accounting_unverifiable", "incomplete_run"])


@pytest.mark.parametrize(("ref", "twin"), [
    ("agentdojo.functions_runtime_unverified@1", True),       # the c6 twin of a D rule
    ("agentdojo.environment_loaded_with_injections_unverified@1", True),
    ("apv:rules/agentdojo.messages_append_ordered_unverified@1", True),
    ("agentdojo.auto_execution_unverified@1", False),         # native class-I rule (CC-08, agentdojo-upstream PC-07)
    ("agentdojo.checker_inputs_unverified@1", False),
    ("agentdojo.messages_append_ordered@1", False),
    ("nosuchns.x_unverified@1", False),
])  # fmt: skip
def test_is_twin_cc08(ref: str, twin: bool) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "precheck"))
    import l2_check

    assert l2_check.is_twin(ref) is twin


def test_bundle_rules_decodes_engine_slugs() -> None:
    """CC-08 follow-up (wave-2 critic): an inference-bundle id joins rule slugs with '--'; each decodes to a rule ref."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "precheck"))
    import l2_check

    iri = ("xd:bundle.inf.agentdojo-assistant_msg_has_one_call_unverified-v1--agentdojo-auto_execution_unverified-v1"
           "--agentdojo-functions_runtime_unverified-v1.7b62kqwwjcujtzuyfadikx7bms")
    refs = l2_check.bundle_rules(iri)
    assert refs == ["agentdojo.assistant_msg_has_one_call_unverified@1", "agentdojo.auto_execution_unverified@1",
                    "agentdojo.functions_runtime_unverified@1"]
    assert [l2_check.is_twin(r) for r in refs] == [True, False, True]
    assert l2_check.bundle_rules("xd:bundle.core.abc") == [] and l2_check.bundle_rules(None) == []


@pytest.mark.parametrize("mode", ["import", "live"])
def test_scratch_card_passes_the_card_lint(lc, mode: str) -> None:
    """The sealed copy's card has the front matter ``package`` compares with ``corpus.json`` (H.9(5)) and no literal
    number (H.9(3)) (pre-round review: the old one-line card made ``--seal`` refuse with ``corpus.datasheet.mode``)."""
    from agentprov.adapters.registry.claims import lint_card
    from agentprov.corpus.datasheet import card_mode

    card = lc.scratch_card(mode)
    assert card_mode(card) == mode
    assert lint_card(card) == []


def test_pin_origins_are_the_product_s(lc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The scratch spec's origin is what ``package`` derives from the recorded pin (D-33): a seeded git pin whose working
    origin records covering pathspecs seals with the pin's tree as ``subtree``; a snapshot the product refuses is left
    out (the fallback then lets ``package`` record the refusal)."""
    from agentprov.corpus import reader as reader_mod
    from agentprov.corpus.manifest import snapshot_origin_from_pin
    from agentprov.raw.origins import Origin

    commit, repo = "c" * 40, "https://example.invalid/r.git"
    sha = "a" * 64
    rows = [SimpleNamespace(snapshot_ids=("s1", "s2"), raw=[SimpleNamespace(sha256=sha, role="primary")])]
    origin = Origin.git(repo, commit, "logs/x.json", "b" * 40)
    fake = SimpleNamespace(origins=lambda: [SimpleNamespace(sha256=sha, origin=origin)], index=lambda: rows,
                           derivation=lambda: {"stages": [{"stage": "aer", "format": "aer/0.1"}]})
    monkeypatch.setattr(reader_mod.CorpusReader, "open", classmethod(lambda cls, root: fake))
    pin = {"kind": "git", "repo": repo, "commit": commit, "tree": "logs/"}
    manifest = {"sources": [{"snapshots": [
        {"snapshot_id": "s1", "pin": pin, "origin": {"kind": "git", "repo": repo, "commit": commit, "subtree": "logs/,meta/"}},
        {"snapshot_id": "s2", "pin": {"kind": "git", "commit": "d" * 40}}]}]}
    out = lc.pin_origins(tmp_path, manifest)
    assert out == {"s1": snapshot_origin_from_pin(pin, [{"kind": "git", **origin.data}])}
    assert out["s1"]["subtree"] == "logs" and lc._spec_origin(manifest["sources"][0]["snapshots"][0])["subtree"] == ""

    # PR-2 (re-check RC-12): an R3 pinned object (an LFS object, hf origin) is a primary with its own pin's origin; the
    # seal's shared helper leaves out the (object, origin) pairs the snapshot records, so the git pin still gives its origin
    lfs_sha, lfs = "e" * 64, Origin.hf("org/data", "f" * 40, "logs/y.json")
    rows.append(SimpleNamespace(snapshot_ids=("s1",), raw=[SimpleNamespace(sha256=lfs_sha, role="primary")]))
    listed = [SimpleNamespace(sha256=sha, origin=origin), SimpleNamespace(sha256=lfs_sha, origin=lfs)]
    fake.origins = lambda: listed
    snap = dict(manifest["sources"][0]["snapshots"][0])
    one = {"sources": [{"snapshots": [snap]}]}
    assert lc.pin_origins(tmp_path, one) == {}  # without the record: mixed kinds, refused (the fallback then applies)
    snap["pinned_objects"] = [{"label": "logs/y.json", "origin": lfs.to_json(), "sha256": "sha256:" + lfs_sha, "bytes": 1}]
    assert lc.pin_origins(tmp_path, one) == {"s1": out["s1"]}


def test_root_digest_is_read_from_stderr(lc, monkeypatch: pytest.MonkeyPatch) -> None:
    """``package`` prints its human lines, "root digest ..." among them, to stderr (re-check RC-12: ``--seal`` never ran
    ``verify --release`` because only stdout was searched)."""
    digest = "sha256:" + "1" * 64
    done = SimpleNamespace(returncode=0, stdout=b"", stderr=f"sealed c 0.1.0\nroot digest {digest}\n".encode())
    monkeypatch.setattr(lc.subprocess, "run", lambda *a, **k: done)
    assert lc._cli(["package"], 5)["root_digest"] == digest
