"""Hand-built SEM documents and fake semantics profiles for the assessment-bundle tests (EF E.7; C.14).

A :class:`~agentprov.sem.types.SemDocument` is built exactly as the SEM engine seals one: header (C.14.1), the
annotations numbered ``a0, a1, …`` in order (C.14.2), and the seal whose ``records_sha256`` is the SHA-256 over every
line before it, each line written with :func:`agentprov.aer.canon.dumps_line` (C.11.6). Profiles are passed to
``derive`` directly (the engine never discovers them). The ``semtest`` catalogue holds the rules the annotations cite.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agentprov.aer.canon import dumps_line
from agentprov.aer.reader import AerDocument
from agentprov.aer.rules import RuleCatalogue, RuleEntry, RuleRegistry, Verification
from agentprov.io.canonical import sha256_hex
from agentprov.sem.types import Annotation, Premise, SemDocument, TaintPolicy

PROFILE_ID = "semtest.suites"
NS = "semtest"


def _rule(name: str, cls: str, **kw: Any) -> tuple[str, RuleEntry]:
    return f"{NS}.{name}@1", RuleEntry(f"{NS}.{name}", 1, cls, "active", f"test rule {name}", **kw)


def semtest_catalogue() -> RuleCatalogue:
    rules = dict([
        _rule("integrity_table", "I"),
        _rule("read_tools", "I"),
        _rule("sink_tools", "I"),
        _rule("channel_table", "I"),
        _rule("marker", "D"),
        _rule("norm", "D"),
        _rule("polarity", "D"),
        _rule("author_field", "D"),
        _rule("ns_label", "D"),
        _rule("taint_sink_untrusted", "I"),
        _rule("normaliser_faith", "I", assumptions=("semtest:NormaliserFaithful",),
              verification=(Verification("semtest:NormaliserFaithful", "asserted"),)),
    ])
    return RuleCatalogue(NS, 1, "agentprov-rule-catalogue/0.1", frozenset(), frozenset(), frozenset(), rules,
                         assumptions=frozenset({"semtest:NormaliserFaithful"}))


def with_semtest(registry: RuleRegistry | None = None) -> RuleRegistry:
    """``registry`` (default: package autoload) with the ``semtest`` catalogue added."""
    reg = registry or RuleRegistry()
    reg.add(semtest_catalogue())
    return reg


V23_POLICY = TaintPolicy(f"{NS}.taint_sink_untrusted@1", frozenset({"write_sink", "send_sink", "execute_sink", "unknown"}),
                         frozenset({"untrusted", "unknown"}))


@dataclass(frozen=True)
class FakeProfile:
    """A :class:`~agentprov.sem.types.SemanticsProfile` whose annotations are given, not computed."""

    id: str = PROFILE_ID
    version: int = 1
    sha256: str = "5" * 64
    rules: Mapping[str, int] = field(default_factory=lambda: {NS: 1})
    ns: Mapping[str, Any] = field(default_factory=dict)
    taint_policy: TaintPolicy | None = V23_POLICY
    given: tuple[Annotation, ...] = ()

    def annotate(self, aer: AerDocument) -> Iterable[Annotation]:
        return iter(self.given)


def sem_document(aer: AerDocument, annotations: Sequence[Annotation | Mapping[str, Any]], *,
                 profile: FakeProfile | None = None, aer_digest: str | None = None, ex: str | None = None) -> SemDocument:
    """Seal ``annotations`` over ``aer`` as the SEM engine would (C.14.1, C.11.6)."""
    profile = profile or FakeProfile()
    header: dict[str, Any] = {
        "k": "sem", "id": "sem", "sem": "0.1", "ex": ex or aer.ex,
        "aer_digest": "sha256:" + (aer_digest or str(aer.seal["records_sha256"])),
        "profile": {"id": profile.id, "version": profile.version}, "rules": dict(profile.rules), "ns": dict(profile.ns),
        "canon": "jcs-rfc8785", "hash": "sha256",
    }
    records: list[dict[str, Any]] = [header]
    for n, a in enumerate(annotations):
        record = a.to_record(f"a{n}") if isinstance(a, Annotation) else {"k": "ann", "id": f"a{n}", **a}
        records.append(record)
    body = b"".join(dumps_line(r) for r in records)
    digest = sha256_hex(body)
    seal = {"k": "seal", "id": "seal", "n_records": len(records) + 1, "records_sha256": digest}
    return SemDocument(header, records, seal, digest, sha256_hex(body + dumps_line(seal)))


def ann(target: str, type_: str, value: Any, ev: str, rule: str, premises: Sequence[tuple[str, str]] = (),
        **kw: Any) -> Annotation:
    return Annotation(target, type_, value, ev, (f"{NS}.{rule}@1",) if "@" not in rule else (rule,),  # type: ignore[arg-type]
                      tuple(Premise(i, p) for i, p in premises), **kw)


ROLE_TABLE = {
    "read_file": ["content_source"], "get_most_recent_transactions": ["content_source"],
    "update_scheduled_transaction": ["write_sink"], "send_money": ["send_sink"], "get_balance": ["neutral"],
}


def suite_annotations(aer: AerDocument) -> list[Annotation]:
    """A v2.3-like labelling of an AgentDojo-family AER: tool results untrusted, user and system text trusted,
    roles from a table (unknown tools ``["unknown"]``), channels, YAML-style markers against the payload fixtures
    (present with a span, else absent), outcome polarity on checker judgements."""
    out: list[Annotation] = []
    fixtures = [r for r in aer.records if r.get("k") == "fixture" and r.get("kind") == "injection_payload"]
    executions = {r["call"]: r for r in aer.records if r.get("k") == "tool_execution" and "call" in r}
    for r in aer.records:
        if r.get("k") == "message":
            for k, part in enumerate(r.get("parts", [])):
                pid = f"{r['id']}#{k}"
                if part.get("t") == "tool_result":
                    te = r.get("generated_by", r["id"])
                    out.append(ann(pid, "integrity", "untrusted", "I", "integrity_table", [(te, "")]))
                    out.append(ann(pid, "channel", "tool", "I", "channel_table", [(te, "")]))
                    text = part.get("text") or ""
                    for fx in fixtures:
                        at = text.find(fx.get("content", "\0")) if isinstance(fx.get("content"), str) else -1
                        if at >= 0:
                            span = (len(text[:at]), len(text[:at]) + len(fx["content"]))
                            out.append(ann(pid, "injection_marker", {"fixture": fx["id"], "status": "present",
                                           "normaliser": f"{NS}.norm@1"}, "D", "marker",
                                           [(r["id"], f"/parts/{k}/text"), (fx["id"], "/content")], at="/text",
                                           span=span))
                        else:
                            out.append(ann(pid, "injection_marker", {"fixture": fx["id"], "status": "absent",
                                           "normaliser": f"{NS}.norm@1"}, "D", "marker", [(fx["id"], "/content")]))
                elif r.get("role") in ("user", "system") and part.get("t") == "text":
                    out.append(ann(pid, "integrity", "trusted", "I", "integrity_table", [(r["id"], "/role")]))
                elif part.get("t") == "tool_call" and pid not in executions:
                    out.append(ann(pid, "role", ROLE_TABLE.get(part.get("name"), ["unknown"]), "I", "sink_tools",
                                   [(r["id"], f"/parts/{k}/name")]))
        elif r.get("k") == "tool_execution":
            name = r.get("name")
            rule = "read_tools" if ROLE_TABLE.get(name) == ["content_source"] else "sink_tools"
            out.append(ann(r["id"], "role", ROLE_TABLE.get(name, ["unknown"]), "I", rule, [(r["id"], "/name")]))
        elif r.get("k") == "judgement" and r.get("origin") == "checker":
            claim = "user_task_solved" if r.get("name") == "utility" else "attack_succeeded"
            out.append(ann(r["id"], "outcome", {"claim": claim, "holds": bool(r.get("value"))}, "D", "polarity",
                           [(r["id"], "/value")]))
    return out
