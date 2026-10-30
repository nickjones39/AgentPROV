"""Synthetic AERs for the provenance-engine tests (EF F.2.6; C.3.15; K.6.4 constructs on the ``tst`` namespace).

Built on ``aer_support`` (the AER unit-test helpers): the header, the ``tst`` catalogue and the seal come from there; this
module adds the generic-kind constructs and a registry whose ``tst`` catalogue declares their types and assumptions.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aer"))

from aer_support import derived, example_records, observed, seal_record  # noqa: E402

from agentprov.aer.canon import dumps_line  # noqa: E402
from agentprov.aer.reader import AerDocument, load_aer  # noqa: E402
from agentprov.aer.rules import RuleCatalogue, RuleEntry, RuleRegistry, Verification, load_catalogue  # noqa: E402
from agentprov.aer.validate import validate_records  # noqa: E402

BLOB_SHA = "a4d4c009619311d9b83904acfd62fe3b7f918c312522bbcc6ad51cdec4fd1edf"
BLOB = {"$blob": "sha256:" + BLOB_SHA, "bytes": 67, "media": "image/png"}
TYPES = frozenset({"tst:plan", "tst:note", "tst:memory_write", "tst:memory_item", "tst:memory_read", "tst:observe",
                   "tst:screenshot", "tst:model_call", "tst:message"})


def registry(extra: dict[str, RuleEntry] | None = None) -> RuleRegistry:
    """``aer`` plus a ``tst`` catalogue with D/I rules, the fixture's types and assumption-declaring rules."""
    reg = RuleRegistry([load_catalogue("aer", 1)], autoload=False)
    verified = Verification("apv:AutoExecution", "verified", ("tst@" + "0" * 40,), "tst", "tst")
    rules = {
        "tst.d@1": RuleEntry("tst.d", 1, "D", "active", "test D rule"),
        "tst.d2@1": RuleEntry("tst.d2", 1, "D", "active", "second test D rule"),
        "tst.i@1": RuleEntry("tst.i", 1, "I", "active", "test I rule"),
        "tst.auto@1": RuleEntry("tst.auto", 1, "D", "active", "auto-execution", assumptions=("apv:AutoExecution",),
                                verification=(verified,)),
        "tst.auto_i@1": RuleEntry("tst.auto_i", 1, "I", "active", "auto-execution, asserted",
                                  assumptions=("apv:AutoExecution",),
                                  verification=(Verification("apv:AutoExecution", "asserted"),)),
        **(extra or {}),
    }
    reg.add(RuleCatalogue("tst", 1, "agentprov-rule-catalogue/0.1", frozenset({"odd_thing"}), frozenset({"tst.sub"}),
                          TYPES, rules))
    return reg


def generic_records() -> list[dict[str, Any]]:
    """The F.2.6 constructs in one execution (all D/O links; serialisation order respects backward references)."""
    header = copy.deepcopy(example_records()[0])
    o = observed
    return [
        header,
        derived({"k": "actor", "id": "agent", "kind": "llm_agent", "name": "agent-under-test",
                 "model": {"requested": "tst-model"}}),
        derived({"k": "actor", "id": "env", "kind": "tool_runtime", "on_behalf_of": "agent"}),
        derived({"k": "actor", "id": "user", "kind": "simulated_user"}),
        derived({"k": "actor", "id": "human", "kind": "user"}),
        derived({"k": "actor", "id": "sub", "kind": "llm_agent"}),
        derived({"k": "scope", "id": "run", "kind": "run", "actor": "agent"}),
        derived({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "scored": True, "actor": "agent"}),
        o({"k": "message", "id": "m0", "scope": "att0", "role": "user", "actor": "user",
           "parts": [{"t": "text", "text": "hello"}]}, 0),
        derived({"k": "model_call", "id": "mc0", "actor": "agent", "role": "agent", "scope": "att0", "input": ["m0"],
                 "status": "kept"}),
        o({"k": "message", "id": "m1", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc0",
           "parts": [{"t": "text", "text": "plan"},
                     {"t": "tool_call", "name": "lookup", "args": {"q": "x"}},
                     {"t": "tool_call", "name": "send", "args": {"to": "y"}},
                     {"t": "tool_call", "name": "delete", "args": {"id": 1}}]}, 1),
        # planner step: a code planner over the assistant message, producing a plan artefact
        derived({"k": "activity", "id": "ac0", "type": "tst:plan", "actor": "agent", "scope": "att0", "inputs": ["m1"],
                 "status": "ok", "label": "plan"}),
        derived({"k": "artefact", "id": "af0", "type": "tst:note", "content": {"steps": ["a"]}, "generated_by": "ac0",
                 "media": "application/json"}),
        # human approval (allow) and the approved execution
        derived({"k": "decision", "id": "dc0", "actor": "human", "scope": "att0", "subject": "m1#1", "verdict": "allow"}),
        derived({"k": "tool_execution", "id": "te0", "actor": "env", "scope": "att0", "call": "m1#1",
                 "authorised_by": "dc0", "name": "lookup", "status": "ok"}),
        o({"k": "message", "id": "m2", "scope": "att0", "role": "tool", "actor": "env", "generated_by": "te0",
           "parts": [{"t": "tool_result", "responds_to": "m1#1", "text": "result"}]}, 2),
        # hand-off to a sub-agent spawned by the execution
        derived({"k": "scope", "id": "sc0", "kind": "subagent", "parent": "att0", "actor": "sub", "spawned_by": "te0"}),
        # approval with edit (modify): NE-18
        derived({"k": "decision", "id": "dc1", "actor": "human", "scope": "att0", "subject": "m1#2", "verdict": "modify"}),
        derived({"k": "tool_execution", "id": "te1", "actor": "env", "scope": "att0", "call": "m1#2",
                 "authorised_by": "dc1", "name": "send", "status": "ok"}),
        o({"k": "message", "id": "m3", "scope": "att0", "role": "tool", "actor": "env", "generated_by": "te1",
           "parts": [{"t": "tool_result", "responds_to": "m1#2", "text": "sent"}]}, 3),
        # denial: a decision only, no execution
        derived({"k": "decision", "id": "dc2", "actor": "human", "scope": "att0", "subject": "m1#3", "verdict": "deny"}),
        o({"k": "message", "id": "m4", "scope": "att0", "role": "tool", "actor": "human", "generated_by": "dc2",
           "parts": [{"t": "tool_result", "responds_to": "m1#3", "text": "denied"}]}, 4),
        # text-parsed action: an execution with no request part
        derived({"k": "tool_execution", "id": "te2", "actor": "env", "scope": "att0", "requested_by": "agent",
                 "name": "click", "status": "ok"}),
        # memory write, then a later read of the written item
        derived({"k": "activity", "id": "ac1", "type": "tst:memory_write", "actor": "agent", "scope": "att0",
                 "inputs": ["m1#0"], "status": "ok"}),
        derived({"k": "artefact", "id": "af1", "type": "tst:memory_item", "content": {"key": "plan"}, "generated_by": "ac1"}),
        derived({"k": "activity", "id": "ac2", "type": "tst:memory_read", "actor": "agent", "scope": "att0",
                 "inputs": ["af1"], "status": "ok"}),
        # a harness observation step saving a screenshot outside the conversation
        derived({"k": "activity", "id": "ac3", "type": "tst:observe", "actor": "agent", "scope": "att0", "inputs": []}),
        derived({"k": "artefact", "id": "af2", "type": "tst:screenshot", "content_ref": BLOB, "sha256": BLOB_SHA,
                 "media": "image/png", "generated_by": "ac3"}),
        derived({"k": "model_call", "id": "mc1", "actor": "agent", "role": "agent", "scope": "att0",
                 "input": ["m0", "m1", "m2", "m3", "m4"], "status": "kept"}),
        o({"k": "message", "id": "m5", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc1",
           "parts": [{"t": "text", "text": "done"}],
           "ext": {"tst": {"telemetry": {"tokens": 3}}}}, 5),  # an unknown event kept in ext only
    ]


def write_aer(records: list[dict[str, Any]], path: Path, *, issues: list[dict[str, Any]] | None = None) -> AerDocument:
    seal = seal_record(records, issues)
    path.write_bytes(b"".join(dumps_line(r) for r in [*records, seal]))
    return load_aer(path)


def check_valid(doc: AerDocument, reg: RuleRegistry) -> list[str]:
    report = validate_records([*doc.records, doc.seal], store=None, catalogues=reg, mode="dev")
    return sorted({f.code for f in report.errors})
