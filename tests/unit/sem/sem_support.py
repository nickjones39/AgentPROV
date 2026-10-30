"""Shared helpers for the SEM tests: stub profiles, the C.14.5 annotations, test-local catalogues, a synthetic AER.

The C.14.5 vector pair (``docs/architecture/examples/C/adprov_v1_llama_injecagent.{aer,sem}.jsonl``) is a frozen
specification artefact. The ``agentdojo`` catalogue the package ships may not declare the C.14.5 rule names yet (and
marks ``agentdojo.injection_marker_yaml`` reserved), so validator tests use the in-memory catalogues built here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov.aer.reader import AerDocument, load_aer
from agentprov.aer.rules import RuleCatalogue, RuleEntry, RuleRegistry
from agentprov.sem.engine import annotate
from agentprov.sem.types import Annotation, Premise, SemDocument, TaintPolicy

REPO = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = REPO / "docs" / "architecture" / "examples" / "C"
EXAMPLE_AER = EXAMPLE_DIR / "adprov_v1_llama_injecagent.aer.jsonl"
EXAMPLE_SEM = EXAMPLE_DIR / "adprov_v1_llama_injecagent.sem.jsonl"
CATALOGUE_FORMAT = "agentprov-rule-catalogue/0.1"


@dataclass(slots=True)
class StubProfile:
    """A semantics profile that yields a fixed list of annotations (satisfies the ``SemanticsProfile`` protocol)."""

    items: tuple[Annotation, ...] = ()
    id: str = "agentdojo.suites"
    version: int = 1
    sha256: str = "0" * 64
    rules: Mapping[str, int] = field(default_factory=lambda: {"agentdojo": 1})
    ns: Mapping[str, Any] = field(default_factory=dict)
    taint_policy: TaintPolicy | None = None

    def annotate(self, aer: AerDocument) -> Iterable[Annotation]:
        return iter(self.items)


def p(id_: str, pointer: str = "") -> Premise:
    return Premise(id_, pointer)


#: The eight annotations of C.14.5, in yield order.
EXAMPLE_ANNOTATIONS: tuple[Annotation, ...] = (
    Annotation("m3#0", "integrity", "untrusted", "I", ("agentdojo.integrity_external_content@1",), (p("te0", "/name"),)),
    Annotation("m3#0", "channel", "file", "I", ("agentdojo.channel_table@1",), (p("te0", "/name"),)),
    Annotation(
        "m3#0", "injection_marker", {"fixture": "fx0", "status": "present", "normaliser": "agentdojo.yaml_norm@1"}, "D",
        ("agentdojo.injection_marker_yaml@1",), (p("m3", "/parts/0/text"), p("fx0", "/content")), at="/text",
        span=(154, 399),
    ),
    Annotation("te0", "role", ["content_source"], "I", ("agentdojo.read_tools@1",), (p("te0", "/name"),)),
    Annotation("te1", "role", ["write_sink"], "I", ("agentdojo.sink_tools@1",), (p("te1", "/name"),)),
    Annotation("te2", "role", ["send_sink"], "I", ("agentdojo.sink_tools@1",), (p("te2", "/name"),)),
    Annotation(
        "j0", "outcome", {"claim": "user_task_solved", "holds": False}, "D", ("agentdojo.utility_meaning@1",),
        (p("j0", "/value"),),
    ),
    Annotation(
        "j1", "outcome", {"claim": "attack_succeeded", "holds": True}, "D", ("agentdojo.security_polarity@1",),
        (p("j1", "/value"), p("j1", "/origin"), p("exec", "/task/attack_id")),
    ),
)
#: The classes of the C.14.5 rules (C.14.5 text: table readings are ``I``; marker, normaliser and polarity are ``D``).
EXAMPLE_RULE_CLASSES = {
    "agentdojo.integrity_external_content@1": "I",
    "agentdojo.channel_table@1": "I",
    "agentdojo.injection_marker_yaml@1": "D",
    "agentdojo.yaml_norm@1": "D",
    "agentdojo.read_tools@1": "I",
    "agentdojo.sink_tools@1": "I",
    "agentdojo.utility_meaning@1": "D",
    "agentdojo.security_polarity@1": "D",
}


def catalogue(namespace: str, classes: Mapping[str, str], *, version: int = 1,
              reserved: Iterable[str] = ()) -> RuleCatalogue:
    """An in-memory catalogue declaring ``classes`` (rule id -> ``D``/``I``); ``reserved`` ids get status reserved."""
    held = set(reserved)
    rules = {}
    for rid, cls in sorted(classes.items()):
        name, _, ver = rid.partition("@")
        rules[rid] = RuleEntry(name, int(ver), cls, "reserved" if rid in held else "active", "test rule")
    return RuleCatalogue(namespace, version, CATALOGUE_FORMAT, frozenset(), frozenset(), frozenset(), rules)


def example_registry(*, reserved: Iterable[str] = ()) -> RuleRegistry:
    """A test-local registry with the C.14.5 ``agentdojo`` rules and the synthetic ``tst`` catalogue (no autoload)."""
    return RuleRegistry(
        [catalogue("agentdojo", EXAMPLE_RULE_CLASSES, reserved=reserved),
         catalogue("tst", {"tst.d@1": "D", "tst.i@1": "I", "tst.held@1": "D"}, reserved=("tst.held@1",))],
        autoload=False,
    )


def example_aer() -> AerDocument:
    return load_aer(EXAMPLE_AER)


def example_sem() -> SemDocument:
    return annotate(example_aer(), StubProfile(EXAMPLE_ANNOTATIONS))


# ------------------------------------------------------------------------------------------------ synthetic AER
NON_BMP = "\U0001f600ab"  # one astral scalar plus two BMP scalars: 3 scalar values, 4 UTF-16 code units
SYN_EX = "ex_7uz2oys57hugtsueixylme4fl5"


def synthetic_aer() -> AerDocument:
    """An in-memory AER holding one record of every kind a C.14.3 target rule names, and a message with every part type.

    The SEM validator does not re-validate the AER (tier 2 does), so this document is assembled directly; its digest is
    a fixed value.
    """
    header = {"k": "execution", "id": "exec", "ev": "O", "ex": SYN_EX, "task": {"attack_id": None}}
    parts = [
        {"t": "text", "text": NON_BMP},
        {"t": "reasoning", "text": "r"},
        {"t": "tool_call", "name": "send_money", "args": {}},
        {"t": "tool_result", "responds_to": "m0#2", "text": "result " + NON_BMP},
        {"t": "blob", "data": {"$blob": "0" * 64}, "media": "image/png"},
        {"t": "file", "ref": "file-1"},
        {"t": "uri", "uri": "https://example.invalid/"},
        {"t": "refusal", "text": "no"},
        {"t": "other", "type": "x.y", "value": 1},
    ]
    records: list[dict[str, Any]] = [
        header,
        {"k": "actor", "id": "att", "ev": "O", "kind": "attacker"},
        {"k": "scope", "id": "run", "ev": "O", "kind": "run"},
        {"k": "fixture", "id": "fx0", "ev": "O", "content": "payload"},
        {"k": "message", "id": "m0", "ev": "O", "role": "tool", "parts": parts, "evf": {"/parts/1": "I"},
         "unk": {"/actor": "not_recorded"}},
        {"k": "model_call", "id": "mc0", "ev": "D"},
        {"k": "tool_execution", "id": "te0", "ev": "O", "name": "send_money"},
        {"k": "decision", "id": "dc0", "ev": "I"},
        {"k": "activity", "id": "ac0", "ev": "O", "type": "x.step"},
        {"k": "artefact", "id": "af0", "ev": "O", "type": "x.doc"},
        {"k": "judgement", "id": "j0", "ev": "O", "name": "utility", "value": True, "origin": "checker"},
        {"k": "judgement", "id": "j1", "ev": "O", "name": "security", "value": True, "origin": "harness_default"},
    ]
    return AerDocument(
        header=header,
        records=records,
        seal={"k": "seal", "id": "seal"},
        execution_digest=hashlib.sha256(b"synthetic").hexdigest(),
        file_sha256=hashlib.sha256(b"synthetic file").hexdigest(),
        _index={r["id"]: r for r in records},
    )


def syn_sem(*items: Annotation, ns: Mapping[str, Any] | None = None, rules: Mapping[str, int] | None = None,
            aer: AerDocument | None = None) -> SemDocument:
    """A sealed SEM document over :func:`synthetic_aer` (or ``aer``) with a ``tst.syn`` profile."""
    profile = StubProfile(items, id="tst.syn", rules=dict(rules or {"tst": 1}), ns=dict(ns or {}))
    return annotate(aer or synthetic_aer(), profile)


def ann(target: str, type_: str, value: Any, *, ev: str = "D", rule: tuple[str, ...] = ("tst.d@1",),
        premises: tuple[Premise, ...] | None = None, **extra: Any) -> Annotation:
    """A synthetic annotation (default: a ``D`` annotation citing ``tst.d@1`` with premise ``(<target base>, "")``)."""
    if premises is None:
        premises = (p(target.split("#", 1)[0], ""),)
    return Annotation(target, type_, value, ev, rule, premises, **extra)  # type: ignore[arg-type]
