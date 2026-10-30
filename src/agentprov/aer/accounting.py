"""Accounting checks recorded in the seal (C.12): the generalised capture gate.

Accounting is computed **once**, here, by the writer and recomputed by the validator (C.12.4). Each check yields
``consistent``, ``inconsistent`` or ``unverifiable``; the seal's ``accounting.status`` is ``inconsistent`` if any
check is, else ``unverifiable`` if any is, else ``consistent``. Inconsistent executions are sealed and kept.

Six checks are computable from the records alone (:data:`CORE_CHECK_IDS`, C.12.2 order). The four live checks
(``passes_closed``, ``dispatch_vs_results``, ``env_recorded``, ``capture_chain``) belong to the capture mapper,
which passes them as ``extra_checks``; they are recorded and never recomputed here.

Population definitions (the specification leaves them implicit; these are the ones the C.16 vectors fix):

* an *assistant message* of the accounting is a ``message`` with ``role: "assistant"`` whose ``actor`` is an
  ``llm_agent`` actor (scripted turns authored by an ``attacker`` are not agent output);
* a *held agent call* is a ``model_call`` with ``role: "agent"`` and ``status: "kept"``; a *lost call* has
  ``unk {"/status": "lost"}`` (C.7.4);
* an *answering agent call* is a held call or a ``cached`` one: a cache read answers the agent without inference, so it
  pairs with the assistant message it generates in ``agent_calls_vs_assistant`` (C.20(1)); provider-reported counts
  (``reported_counts``) still count held calls only, because a cache read never reaches the provider;
* a check is recorded for every scope that contains at least one item for it; ``denied`` appears in the
  ``tool_calls_dispatched`` observation only when non-zero.

``compute`` needs the seal issues (``unexecuted_tool_call``, ``orphan_tool_result``, ``missing_tool_result``,
``missing_generated_by``): a listed item is accounted for, an unlisted one makes the check ``inconsistent``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from agentprov.aer.types import ACCOUNTING_VERDICTS, Json

__all__ = [
    "CORE_CHECK_IDS",
    "Accounting",
    "AccountingTally",
    "compute",
    "fold_status",
    "mirror_issues",
]

AGENT_CALLS: Final = "aer.acc.agent_calls_vs_assistant@1"
REPORTED: Final = "aer.acc.reported_counts@1"
DISPATCHED: Final = "aer.acc.tool_calls_dispatched@1"
LINKED: Final = "aer.acc.tool_results_linked@1"
HAVE_RESULTS: Final = "aer.acc.executions_have_results@1"
GENERATED_BY: Final = "aer.acc.assistant_generated_by@1"
#: The checks computable from the records, in the order they appear in the seal (C.12.2).
CORE_CHECK_IDS: Final = (AGENT_CALLS, REPORTED, DISPATCHED, LINKED, HAVE_RESULTS, GENERATED_BY)
_SEVERITY: Final = {verdict: rank for rank, verdict in enumerate(ACCOUNTING_VERDICTS)}


@dataclass(frozen=True, slots=True)
class Accounting:
    """The seal's ``accounting`` object: a fold status and the ordered checks."""

    status: str
    checks: tuple[dict[str, Json], ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Json]:
        checks: list[Json] = [dict(c) for c in self.checks]
        return {"status": self.status, "checks": checks}


def fold_status(verdicts: Iterable[str]) -> str:
    """``inconsistent`` if any verdict is, else ``unverifiable`` if any is, else ``consistent``."""
    worst = "consistent"
    for verdict in verdicts:
        if _SEVERITY[verdict] > _SEVERITY[worst]:
            worst = verdict
    return worst


def mirror_issues(accounting: Accounting) -> list[dict[str, Json]]:
    """The seal issues that mirror non-consistent verdicts (C.12.3): one per such check, citing the check."""
    out: list[dict[str, Json]] = []
    for check in accounting.checks:
        verdict = check.get("verdict")
        if verdict in ("inconsistent", "unverifiable"):
            scope = check["scope"]
            assert isinstance(scope, str)
            out.append({"code": f"accounting_{verdict}", "ids": [scope], "rule": check["id"]})
    return out


class _Scope:
    __slots__ = ("parent",)

    def __init__(self, parent: str | None) -> None:
        self.parent = parent


class AccountingTally:
    """Single-pass accumulator behind :func:`compute` and the streaming validator (holds ids, not records)."""

    def __init__(self) -> None:
        self._scopes: dict[str, _Scope] = {}
        self._usage_calls: dict[str, int] = {}
        self._actor_kind: dict[str, str] = {}
        # per scope: ordered first-appearance of scope ids per check family (scope order = first item seen)
        self._call_parts: dict[str, list[int]] = {}  # part id -> [executions, denials, results]
        self._call_scope: dict[str, str] = {}
        self._results: list[tuple[str, str, str, str | None, bool]] = []  # scope, part id, message id, responds_to, unk
        self._executions: dict[str, dict[str, object]] = {}
        self._decisions: dict[str, tuple[str, str]] = {}  # id -> (verdict, subject)
        self._agent_calls: list[dict[str, object]] = []
        self._call_outputs: dict[str, int] = {}  # model_call id -> assistant messages generated by it
        self._assistants: list[dict[str, object]] = []
        self._order: dict[str, int] = {}
        self._calls_seen: dict[str, str] = {}

    # -------------------------------------------------------------------------------------------- feed
    def feed(self, record: Mapping[str, object]) -> None:
        kind = record.get("k")
        rid = record.get("id")
        if not isinstance(rid, str):
            return
        if kind == "actor":
            if isinstance(record.get("kind"), str):
                self._actor_kind[rid] = str(record["kind"])
        elif kind == "scope":
            parent = record.get("parent")
            self._scopes[rid] = _Scope(parent if isinstance(parent, str) else None)
            self._order.setdefault(rid, len(self._order))
            usage = record.get("usage")
            if isinstance(usage, Mapping) and isinstance(usage.get("calls"), int) and not isinstance(usage["calls"], bool):
                self._usage_calls[rid] = usage["calls"]
        elif kind == "message":
            self._feed_message(rid, record)
        elif kind == "model_call":
            self._feed_model_call(rid, record)
        elif kind == "tool_execution":
            self._feed_execution(rid, record)
        elif kind == "decision":
            verdict, subject = record.get("verdict"), record.get("subject")
            self._decisions[rid] = (str(verdict), str(subject))
            if verdict == "deny" and isinstance(subject, str) and subject in self._call_parts:
                self._call_parts[subject][1] += 1

    def _scope_of(self, record: Mapping[str, object]) -> str:
        scope = record.get("scope")
        return scope if isinstance(scope, str) else ""

    def _feed_message(self, rid: str, record: Mapping[str, object]) -> None:
        scope = self._scope_of(record)
        unk = record.get("unk")
        unk_keys = set(unk) if isinstance(unk, Mapping) else set()
        parts = record.get("parts")
        if isinstance(parts, list):
            for k, part in enumerate(parts):
                if not isinstance(part, Mapping):
                    continue
                part_id = f"{rid}#{k}"
                if part.get("t") == "tool_call":
                    self._call_parts[part_id] = [0, 0, 0]
                    self._call_scope[part_id] = scope
                elif part.get("t") == "tool_result":
                    target = part.get("responds_to")
                    linked = isinstance(target, str) and target in self._call_parts
                    if linked:
                        assert isinstance(target, str)
                        self._call_parts[target][2] += 1
                    self._results.append((scope, part_id, rid, str(target) if linked else None, True))
        generated_by = record.get("generated_by")
        if isinstance(generated_by, str):
            if generated_by in self._executions:
                self._executions[generated_by]["has_result"] = True
            elif generated_by in self._decisions:
                _verdict, subject = self._decisions[generated_by]
                if subject in self._executions:
                    self._executions[subject]["has_result"] = True
        actor = record.get("actor")
        if record.get("role") == "assistant" and isinstance(actor, str) and self._actor_kind.get(actor) == "llm_agent":
            self._assistants.append(
                {
                    "id": rid,
                    "scope": scope,
                    "generated_by": generated_by if isinstance(generated_by, str) else None,
                    "unk_generated_by": "/generated_by" in unk_keys,
                }
            )
            if isinstance(generated_by, str) and generated_by in self._call_outputs:
                self._call_outputs[generated_by] += 1
            self._order.setdefault(scope, len(self._order))

    def _feed_model_call(self, rid: str, record: Mapping[str, object]) -> None:
        if record.get("role") != "agent":
            return
        scope = self._scope_of(record)
        unk = record.get("unk")
        lost = isinstance(unk, Mapping) and unk.get("/status") == "lost"
        self._order.setdefault(scope, len(self._order))
        self._agent_calls.append(
            {
                "id": rid,
                "scope": scope,
                "kept": record.get("status") == "kept",
                "answering": record.get("status") in ("kept", "cached"),
                "lost": lost,
                "observed": record.get("ev") == "O",
                # A reported finish-reason entry exists when the value is recorded or is a recorded unknown (a
                # provider null mapped to `unk /finish_reason`): C.12.2 counts entries, not known values (C.19(15)).
                "finish": "finish_reason" in record or (isinstance(unk, Mapping) and "/finish_reason" in unk),
            }
        )
        if record.get("status") in ("kept", "cached"):
            self._call_outputs[rid] = 0

    def _feed_execution(self, rid: str, record: Mapping[str, object]) -> None:
        scope = self._scope_of(record)
        self._executions[rid] = {"scope": scope, "has_result": False}
        self._order.setdefault(scope, len(self._order))
        call = record.get("call")
        if isinstance(call, str) and call in self._call_parts:
            self._call_parts[call][0] += 1

    # -------------------------------------------------------------------------------------------- finish
    def _subtree(self, scope: str) -> set[str]:
        members = set()
        for sid in self._scopes:
            cursor: str | None = sid
            seen: set[str] = set()
            while cursor is not None and cursor not in seen:
                if cursor == scope:
                    members.add(sid)
                    break
                seen.add(cursor)
                node = self._scopes.get(cursor)
                cursor = node.parent if node else None
        members.add(scope)
        return members

    def _scopes_in_order(self, used: Iterable[str]) -> list[str]:
        return sorted(set(used), key=lambda s: (self._order.get(s, len(self._order)), s))

    def finish(
        self,
        issues: Sequence[Mapping[str, object]] = (),
        extra_checks: Sequence[Mapping[str, Json]] = (),
    ) -> Accounting:
        listed: dict[str, set[str]] = {}
        for issue in issues:
            code, ids = issue.get("code"), issue.get("ids")
            if isinstance(code, str) and isinstance(ids, list):
                listed.setdefault(code, set()).update(i for i in ids if isinstance(i, str))
        checks: list[dict[str, Json]] = []
        checks += self._agent_calls_checks()
        checks += self._reported_checks()
        checks += self._dispatched_checks(listed.get("unexecuted_tool_call", set()))
        checks += self._linked_checks(listed.get("orphan_tool_result", set()))
        checks += self._have_results_checks(listed.get("missing_tool_result", set()))
        checks += self._generated_by_checks(listed.get("missing_generated_by", set()))
        checks += [dict(c) for c in extra_checks]
        verdicts = [str(c["verdict"]) for c in checks]
        return Accounting(fold_status(verdicts), tuple(checks))

    @staticmethod
    def _entry(
        check_id: str, scope: str, verdict: str, observed: dict[str, int], reason: str | None = None
    ) -> dict[str, Json]:
        entry: dict[str, Json] = {"id": check_id, "scope": scope, "verdict": verdict}
        if reason is not None:
            entry["reason"] = reason
        counts: dict[str, Json] = {k: observed[k] for k in sorted(observed)}
        entry["observed"] = counts
        return entry

    def _reported_scopes(self) -> list[str]:
        return [s for s in self._scopes_in_order(self._usage_calls) if s in self._usage_calls]

    def _covered_by_reported(self, scope: str) -> bool:
        cursor: str | None = scope
        seen: set[str] = set()
        while cursor is not None and cursor not in seen:
            if cursor in self._usage_calls:
                return True
            seen.add(cursor)
            node = self._scopes.get(cursor)
            cursor = node.parent if node else None
        return False

    def _agent_calls_checks(self) -> list[dict[str, Json]]:
        scopes = {c["scope"] for c in self._agent_calls if c["answering"]} | {str(a["scope"]) for a in self._assistants}
        out = []
        for scope in self._scopes_in_order(str(s) for s in scopes):
            if self._covered_by_reported(scope):
                continue
            calls = [c for c in self._agent_calls if c["scope"] == scope and c["answering"]]
            msgs = [a for a in self._assistants if a["scope"] == scope]
            observed = {"assistant_messages": len(msgs), "model_calls": len(calls)}
            if not any(c["observed"] for c in calls):
                out.append(self._entry(AGENT_CALLS, scope, "unverifiable", observed, "model_calls_derived_from_messages"))
                continue
            ok = len(calls) == len(msgs) and all(self._call_outputs.get(str(c["id"]), 0) == 1 for c in calls)
            out.append(
                self._entry(
                    AGENT_CALLS,
                    scope,
                    "consistent" if ok else "inconsistent",
                    observed,
                    None if ok else "calls_and_assistant_messages_differ",
                )
            )
        return out

    def _reported_checks(self) -> list[dict[str, Json]]:
        out = []
        # C.20(1): a cache read never reaches the provider, so the message it generates is not provider-counted.
        cached = {c["id"] for c in self._agent_calls if c["answering"] and not c["kept"]}
        for scope in self._reported_scopes():
            subtree = self._subtree(scope)
            held = [c for c in self._agent_calls if c["scope"] in subtree and c["kept"]]
            lost = sum(1 for c in self._agent_calls if c["scope"] in subtree and c["lost"])
            messages = sum(1 for a in self._assistants if a["scope"] in subtree and a["generated_by"] not in cached)
            finish = sum(1 for c in held if c["finish"])
            reported = self._usage_calls[scope]
            observed = {"assistant_messages": messages, "lost_calls": lost, "reported_calls": reported}
            if finish:
                observed["finish_reasons"] = finish
            reason = None
            if reported != messages + lost:
                reason = "reported_calls_differ"
            elif finish and finish != len(held):
                reason = "finish_reasons_differ"
            out.append(self._entry(REPORTED, scope, "consistent" if reason is None else "inconsistent", observed, reason))
        return out

    def _dispatched_checks(self, unexecuted_listed: set[str]) -> list[dict[str, Json]]:
        by_scope: dict[str, list[str]] = {}
        for part_id, scope in self._call_scope.items():
            by_scope.setdefault(scope, []).append(part_id)
        out = []
        for scope in self._scopes_in_order(by_scope):
            parts = by_scope[scope]
            executed = sum(self._call_parts[p][0] for p in parts)
            denied = sum(self._call_parts[p][1] for p in parts)
            unexecuted = sum(1 for p in parts if self._call_parts[p][0] + self._call_parts[p][1] == 0)
            bad = False
            for p in parts:
                handled = self._call_parts[p][0] + self._call_parts[p][1] + (1 if p in unexecuted_listed else 0)
                bad = bad or handled != 1
            observed = {"tool_calls": len(parts), "tool_executions": executed, "unexecuted": unexecuted}
            if denied:
                observed["denied"] = denied
            out.append(
                self._entry(
                    DISPATCHED, scope, "inconsistent" if bad else "consistent", observed, "call_not_handled_exactly_once" if bad else None
                )
            )
        return out

    def _linked_checks(self, orphans_listed: set[str]) -> list[dict[str, Json]]:
        by_scope: dict[str, list[tuple[str, str, str | None]]] = {}
        for scope, part_id, message_id, target, _ in self._results:
            by_scope.setdefault(scope, []).append((part_id, message_id, target))
        out = []
        for scope in self._scopes_in_order(by_scope):
            rows = by_scope[scope]
            linked = sum(1 for _, _, t in rows if t is not None)
            bad = any(t is None and not ({p, m} & orphans_listed) for p, m, t in rows)
            multi = any(t is not None and self._call_parts[t][2] > 1 for _, _, t in rows)
            observed = {"linked": linked, "tool_results": len(rows)}
            reason = "tool_result_without_call" if bad else ("call_has_several_results" if multi else None)
            out.append(self._entry(LINKED, scope, "consistent" if reason is None else "inconsistent", observed, reason))
        return out

    def _have_results_checks(self, missing_listed: set[str]) -> list[dict[str, Json]]:
        by_scope: dict[str, list[str]] = {}
        for ex_id, row in self._executions.items():
            by_scope.setdefault(str(row["scope"]), []).append(ex_id)
        out = []
        for scope in self._scopes_in_order(by_scope):
            ids = by_scope[scope]
            with_result = sum(1 for i in ids if self._executions[i]["has_result"])
            bad = any(not self._executions[i]["has_result"] and i not in missing_listed for i in ids)
            observed = {"tool_executions": len(ids), "with_result": with_result}
            out.append(self._entry(HAVE_RESULTS, scope, "inconsistent" if bad else "consistent", observed, "execution_without_result" if bad else None))
        return out

    def _generated_by_checks(self, missing_listed: set[str]) -> list[dict[str, Json]]:
        by_scope: dict[str, list[dict[str, object]]] = {}
        for msg in self._assistants:
            by_scope.setdefault(str(msg["scope"]), []).append(msg)
        out = []
        for scope in self._scopes_in_order(by_scope):
            msgs = by_scope[scope]
            with_gen = sum(1 for m in msgs if m["generated_by"] is not None)
            bad = any(m["generated_by"] is None and not (m["unk_generated_by"] and m["id"] in missing_listed) for m in msgs)
            observed = {"assistant_messages": len(msgs), "with_generated_by": with_gen}
            out.append(self._entry(GENERATED_BY, scope, "inconsistent" if bad else "consistent", observed, "assistant_without_generated_by" if bad else None))
        return out


def compute(
    records: Iterable[Mapping[str, object]],
    issues: Sequence[Mapping[str, object]] = (),
    extra_checks: Sequence[Mapping[str, Json]] = (),
) -> Accounting:
    """Accounting of ``records`` (any order the file has, header and seal ignored), given the seal ``issues``."""
    tally = AccountingTally()
    for record in records:
        tally.feed(record)
    return tally.finish(issues, extra_checks)
