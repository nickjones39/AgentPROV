"""The generic detectors of the safety net (D.15.3): pure functions over the records of one sealed AER.

Each detector reads only the records it is given and reports **hits**: a detector name (``artefact.generic.<name>``), a
*variant* (a short token that keeps different causes apart), the record or part ids that are the locators, the rule ids
the evidence cites, and the seal-issue codes that correspond to it. A hit never carries source content: ids, tokens and
counts only (D.2.7).

Implemented here (everything computable from an AER alone):

=====================================  ======================================================  =====
detector                               condition                                               class
=====================================  ======================================================  =====
``empty_execution``                    ``unit = outcome_only``, or no ``message`` record       O
``harness_imposed_outcome``            ``judgement.origin`` is ``harness_default``/``_rule``   O
``sentinel_time``                      ``t.raw`` or typed time holds a sentinel, or ``unk``    O
                                       declares a ``/t`` pointer unknown
``provider_id_anomaly``                a ``tool_call`` part without id, with ``""``, or an     O
                                       id repeated inside the execution; seal issue
                                       ``call_result_link_conflict``
``unexecuted_call``                    a ``tool_call`` part with no execution and no deny      D
``abnormal_finish``                    ``model_call.finish_reason`` outside the normal set     O
``text_encoded_call``                  an assistant message with no ``tool_call`` part whose   I
                                       text holds a call marker or names a tool of the run
                                       (heuristic: counts are never exact, D.15.5)
``pass_loss``                          an ``attempt`` scope with an ``unk`` reason ``lost`` or  D
                                       evidence class ``I``; seal issues
                                       ``earlier_attempts_unobservable`` and
                                       ``retry_passes_inferred``
``accounting_inconsistent``            a seal accounting check with verdict ``inconsistent``   O
``accounting_unverifiable``            a seal accounting check with verdict ``unverifiable``   O
``seal_issue``                         any other seal issue (variant: its code)               O
``payload_not_reaching_agent``         an attacked ``agent_execution`` whose SEM has no        D
                                       ``present`` injection marker (needs the SEM records;
                                       skipped without them)
=====================================  ======================================================  =====

``payload_not_reaching_agent`` (phase-10 analysis B5) is the one detector that reads SEM. It reports what the SEM
annotations say and nothing else: an execution is *attacked* when the AER header names an ``attack_id`` and the unit is an
``agent_execution`` (an outcome-only record is the ``empty_execution`` finding); it is a hit when no ``injection_marker``
annotation has status ``present``. The variant keeps the causes apart: ``absent`` (at least one comparison was made and
every one found nothing), ``undetermined`` (no ``present``, but some comparison was ``ambiguous`` or a ``gap``: the
payload may have been read) and ``no_marker`` (the SEM holds no marker annotation at all: no tool result was compared
with a payload, so nothing can show the payload reached the agent). A wrong ``absent`` is inherited from the SEM profile
(for example the YAML-escaped AutoDojo payloads of analysis B1); the detector never re-reads tool outputs. Without SEM
records it is skipped, not guessed, exactly like the seal-dependent detectors without a seal.

**Not yet implemented** (they need layers that do not exist yet; D.15.3 lists them and they are recorded here so the
gap is visible, never silently dropped):

* ``cross_origin_duplicate``: byte-identical or mirror duplicates across origins (lineage, I.2.4) needs the corpus
  index, not one AER;
* ``validator_warning``: any AER validator warning is an unclassified anomaly (D.15.3); the validator needs the raw
  store and the rule catalogues, which ``scan`` deliberately does not take.

A hit's *rules* come from the records' field-scoped rule references (``rule@n#/pointer``), so a catalogue entry can
claim exactly the hits its own mapper rule produced. Records that are about the whole record (scopes, judgements) offer
all their rules.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from agentprov.aer.rules import rule_id_of
from agentprov.artefacts.catalogue import GENERIC_PREFIX

__all__ = [
    "ABNORMAL_FINISH_NORMAL",
    "DETECTORS",
    "MAX_LOCATORS",
    "NOT_YET_IMPLEMENTED",
    "SENTINEL_VALUES",
    "DetectorInfo",
    "Hit",
    "run_detectors",
]

#: The cap on locators kept per hit (the hit's count is exact; the list is the first ones in file order).
MAX_LOCATORS: Final = 25
#: Longest text scanned for call markers, per text part (bounded work on hostile input).
_MAX_SCAN_CHARS: Final = 100_000
_MAX_TOOL_NAMES: Final = 256

#: Typed-field deny-list of the sentinel ban (C.7.3), compared case-insensitively.
SENTINEL_VALUES: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-"})
#: Finish reasons that are normal endings across the providers AgentPROV reads (compared lower-case). A reason outside
#: this set is reported as ``abnormal_finish``; extending the set is a reviewed change.
ABNORMAL_FINISH_NORMAL: Final = frozenset(
    {"stop", "tool_calls", "tool_call", "tool_use", "end_turn", "stop_sequence", "function_call", "complete"}
)
_MARKERS: Final = ("<function=", "<|python_tag|>", "<tool_call>", "[TOOL_CALLS]", "<function_call>", "<|tool_call")
_JSON_CALL: Final = re.compile(r'\{\s*"(?:name|function)"\s*:\s*"[^"\n]{1,80}"\s*,\s*"(?:arguments|parameters|args)"\s*:')
_TOOL_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]{0,63}")
_VARIANT_TOKEN: Final = re.compile(r"[A-Za-z0-9_.\-]{1,40}")
_SAFE_TOKEN: Final = re.compile(r"[A-Za-z0-9_.@:\-]{1,80}")
_MAX_LOCATOR_CHARS: Final = 120
_HARNESS_ORIGINS: Final = frozenset({"harness_default", "harness_rule"})

NOT_YET_IMPLEMENTED: Final = ("cross_origin_duplicate", "validator_warning")


@dataclass(frozen=True, slots=True)
class DetectorInfo:
    """What the catalogue validator and the docs know about one generic detector."""

    name: str  # ``artefact.generic.<name>``
    title: str
    evidence_class: str
    variants: frozenset[str] | None  # None: open (variants are data-dependent tokens)


def _info(name: str, title: str, cls: str, variants: tuple[str, ...] | None) -> tuple[str, DetectorInfo]:
    full = GENERIC_PREFIX + name
    return full, DetectorInfo(full, title, cls, None if variants is None else frozenset(variants))


DETECTORS: Final[Mapping[str, DetectorInfo]] = MappingProxyType(
    dict(
        [
            _info("empty_execution", "empty or outcome-only execution", "O", ("outcome_only", "no_messages")),
            _info("harness_imposed_outcome", "outcome imposed by the harness", "O", tuple(sorted(_HARNESS_ORIGINS))),
            _info("sentinel_time", "sentinel or unknown time", "O", None),
            _info("provider_id_anomaly", "provider call-id anomaly", "O", ("absent", "empty", "repeated", "link_conflict")),
            _info("unexecuted_call", "tool call requested but never executed", "D", ("",)),
            _info("abnormal_finish", "abnormal finish reason", "O", None),
            _info("text_encoded_call", "suspected text-encoded tool call", "I", ("marker", "json_call", "named_call")),
            _info("pass_loss", "lost or inferred pass", "D", ("lost", "inferred")),
            _info("accounting_inconsistent", "accounting check inconsistent", "O", None),
            _info("accounting_unverifiable", "accounting check unverifiable", "O", None),
            _info("seal_issue", "seal issue with no generic counterpart", "O", None),
            _info("payload_not_reaching_agent", "injected payload never reached the agent", "D", ("absent", "undetermined", "no_marker")),
        ]
    )
)


@dataclass(slots=True)
class Hit:
    """The accumulated evidence for one (detector, variant) in one execution."""

    detector: str
    variant: str
    ids: dict[str, None] = field(default_factory=dict)  # insertion-ordered set of locators
    rules: set[str] = field(default_factory=set)
    issue_codes: set[str] = field(default_factory=set)


class _Hits:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], Hit] = {}

    def add(
        self,
        name: str,
        variant: str,
        locator: str,
        *,
        rules: Sequence[str] = (),
        issue: str | None = None,
    ) -> None:
        key = (GENERIC_PREFIX + name, variant if variant == "" or _SAFE_TOKEN.fullmatch(variant) else "other")
        hit = self._hits.get(key)
        if hit is None:
            hit = self._hits[key] = Hit(*key)
        hit.ids[locator[:_MAX_LOCATOR_CHARS]] = None
        hit.rules.update(rules)
        if issue is not None:
            hit.issue_codes.add(issue)

    def result(self) -> list[Hit]:
        return [self._hits[k] for k in sorted(self._hits)]


def _scoped(record: Mapping[str, Any], *prefixes: str) -> list[str]:
    """Rule ids of ``record`` whose reference is scoped (``#/pointer``) under one of ``prefixes``."""
    out: list[str] = []
    refs = record.get("rule")
    if not isinstance(refs, list):
        return out
    for ref in refs:
        if isinstance(ref, str) and "#" in ref:
            pointer = ref.split("#", 1)[1]
            if any(pointer == p or pointer.startswith(p + "/") for p in prefixes):
                out.append(rule_id_of(ref))
    return out


def _all_rules(record: Mapping[str, Any]) -> list[str]:
    refs = record.get("rule")
    return [rule_id_of(r) for r in refs if isinstance(r, str)] if isinstance(refs, list) else []


def _str_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("id")
    return value if isinstance(value, str) else None


def _parts(record: Mapping[str, Any]) -> list[tuple[int, Mapping[str, Any]]]:
    parts = record.get("parts")
    if not isinstance(parts, list):
        return []
    return [(k, p) for k, p in enumerate(parts) if isinstance(p, dict)]


@dataclass(slots=True)
class View:
    """The records of one execution, indexed once for the detectors."""

    header: Mapping[str, Any]
    body: list[Mapping[str, Any]]  # every record except the header and the seal, in file order
    seal: Mapping[str, Any] | None
    by_kind: dict[str, list[Mapping[str, Any]]]
    #: The annotation records (``k: "ann"``) of the execution's SEM file; ``None`` when no SEM was given (the detectors
    #: that need it are skipped, not guessed).
    sem: list[Mapping[str, Any]] | None = None

    @property
    def exec_id(self) -> str:
        return _str_id(self.header) or "exec"


# ---------------------------------------------------------------------------------------------------- detectors


def _empty_variant(view: View) -> str | None:
    if view.header.get("unit") == "outcome_only":
        return "outcome_only"
    if not view.by_kind.get("message"):
        return "no_messages"
    return None


def _empty_execution(view: View, hits: _Hits) -> None:
    variant = _empty_variant(view)
    if variant is not None:
        hits.add("empty_execution", variant, view.exec_id)


def _harness_imposed(view: View, hits: _Hits) -> None:
    for rec in view.by_kind.get("judgement", []):
        origin, rid = rec.get("origin"), _str_id(rec)
        if origin in _HARNESS_ORIGINS and rid is not None:
            hits.add("harness_imposed_outcome", str(origin), rid, rules=_all_rules(rec))


def _is_sentinel(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() in SENTINEL_VALUES


def _sentinel_time(view: View, hits: _Hits) -> None:
    for rec in view.body:
        rid = _str_id(rec)
        if rid is None:
            continue
        rules = _scoped(rec, "/t")
        unk = rec.get("unk")
        if isinstance(unk, dict):
            for pointer in sorted(unk):
                reason = unk[pointer]
                if isinstance(pointer, str) and (pointer == "/t" or pointer.startswith("/t/")) and isinstance(reason, str):
                    hits.add("sentinel_time", f"unknown_{reason}", rid, rules=rules)
        t = rec.get("t")
        if not isinstance(t, dict):
            continue
        raw = t.get("raw")
        if isinstance(raw, dict) and any(_is_sentinel(v) for v in raw.values()):
            hits.add("sentinel_time", "raw_sentinel", rid, rules=rules)
        if any(_is_sentinel(t.get(k)) for k in ("start", "end", "start_naive", "end_naive") if k in t):
            hits.add("sentinel_time", "typed_sentinel", rid, rules=rules)


def _tool_call_parts(view: View) -> list[tuple[str, str, int, Mapping[str, Any], Mapping[str, Any]]]:
    out = []
    for rec in view.by_kind.get("message", []):
        mid = _str_id(rec)
        if mid is None:
            continue
        for k, part in _parts(rec):
            if part.get("t") == "tool_call":
                out.append((f"{mid}#{k}", mid, k, part, rec))
    return out


def _provider_ids(view: View, hits: _Hits) -> None:
    seen: dict[str, list[tuple[str, int, Mapping[str, Any]]]] = {}
    for pid, _mid, k, part, rec in _tool_call_parts(view):
        scoped = _scoped(rec, f"/parts/{k}/provider_call_id")
        value = part.get("provider_call_id")
        if value is None:
            hits.add("provider_id_anomaly", "absent", pid, rules=scoped)
        elif value == "":
            hits.add("provider_id_anomaly", "empty", pid, rules=scoped)
        elif isinstance(value, str):
            seen.setdefault(value, []).append((pid, k, rec))
    for value in sorted(seen):
        group = seen[value]
        if len(group) > 1:
            for pid, k, rec in group:
                hits.add("provider_id_anomaly", "repeated", pid, rules=_scoped(rec, f"/parts/{k}/provider_call_id"))


def _unexecuted(view: View, hits: _Hits) -> None:
    called = {r.get("call") for r in view.by_kind.get("tool_execution", [])}
    denied = {r.get("subject") for r in view.by_kind.get("decision", []) if r.get("verdict") == "deny"}
    for pid, _mid, _k, _part, _rec in _tool_call_parts(view):
        if pid not in called and pid not in denied:
            hits.add("unexecuted_call", "", pid)


def _abnormal_finish(view: View, hits: _Hits) -> None:
    for rec in view.by_kind.get("model_call", []):
        reason, rid = rec.get("finish_reason"), _str_id(rec)
        if isinstance(reason, str) and rid is not None and reason.strip().lower() not in ABNORMAL_FINISH_NORMAL:
            variant = reason.strip().lower() if _VARIANT_TOKEN.fullmatch(reason.strip()) else "other"
            hits.add("abnormal_finish", variant, rid, rules=_scoped(rec, "/finish_reason"))


def _tool_names(view: View) -> list[str]:
    names: set[str] = set()
    for rec in view.by_kind.get("fixture", []):
        if rec.get("kind") != "tool_definitions":
            continue
        content = rec.get("content")
        items = content.get("tools") if isinstance(content, dict) else content
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                fn = item.get("function")
                name = item.get("name", fn.get("name") if isinstance(fn, dict) else None)
                if isinstance(name, str):
                    names.add(name)
    for rec in view.by_kind.get("tool_execution", []):
        if isinstance(rec.get("name"), str):
            names.add(rec["name"])
    for _pid, _mid, _k, part, _rec in _tool_call_parts(view):
        if isinstance(part.get("name"), str):
            names.add(part["name"])
    return sorted(n for n in names if _TOOL_NAME.fullmatch(n))[:_MAX_TOOL_NAMES]


def _text_encoded(view: View, hits: _Hits) -> None:
    names = _tool_names(view)
    patterns = [(n, re.compile(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"\s*\(")) for n in names]
    for rec in view.by_kind.get("message", []):
        mid = _str_id(rec)
        if mid is None or rec.get("role") != "assistant":
            continue
        parts = _parts(rec)
        if any(p.get("t") == "tool_call" for _k, p in parts):
            continue
        for k, part in parts:
            text = part.get("text") if part.get("t") == "text" else None
            if not isinstance(text, str):
                continue
            text = text[:_MAX_SCAN_CHARS]
            where = f"{mid}#{k}"
            if any(marker in text for marker in _MARKERS):
                hits.add("text_encoded_call", "marker", where)
            elif _JSON_CALL.search(text):
                hits.add("text_encoded_call", "json_call", where)
            elif any(p.search(text) for _n, p in patterns):
                hits.add("text_encoded_call", "named_call", where)


def _pass_loss(view: View, hits: _Hits) -> None:
    for rec in view.by_kind.get("scope", []):
        rid = _str_id(rec)
        if rid is None or rec.get("kind") != "attempt":
            continue
        unk = rec.get("unk")
        if isinstance(unk, dict) and any(v == "lost" for v in unk.values()):
            hits.add("pass_loss", "lost", rid, rules=_all_rules(rec))
        if rec.get("ev") == "I":
            hits.add("pass_loss", "inferred", rid, rules=_all_rules(rec))


def _accounting(view: View, hits: _Hits) -> None:
    seal = view.seal
    accounting = seal.get("accounting") if seal is not None else None
    checks = accounting.get("checks") if isinstance(accounting, dict) else None
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        verdict, cid = check.get("verdict"), check.get("id")
        if verdict not in ("inconsistent", "unverifiable") or not isinstance(cid, str):
            continue
        scope = check.get("scope")
        hits.add(f"accounting_{verdict}", rule_id_of(cid), scope if isinstance(scope, str) else view.exec_id, rules=[rule_id_of(cid)])


#: Seal issue codes that correspond to a generic detector: ``code -> (detector, variant or None for "as computed")``.
#: The accounting codes mirror the verdicts and are covered by :func:`_accounting`.
_ISSUE_DETECTORS: Final[Mapping[str, tuple[str, str | Callable[[View], str]]]] = MappingProxyType(
    {
        "no_execution_observed": ("empty_execution", lambda view: _empty_variant(view) or "outcome_only"),
        "outcome_imposed_by_runner": ("harness_imposed_outcome", "harness_default"),
        "unexecuted_tool_call": ("unexecuted_call", ""),
        "call_result_link_conflict": ("provider_id_anomaly", "link_conflict"),
        "retry_passes_inferred": ("pass_loss", "inferred"),
        "earlier_attempts_unobservable": ("pass_loss", "lost"),
    }
)
_MIRRORED_ISSUES: Final = frozenset({"accounting_inconsistent", "accounting_unverifiable"})


def _issues(view: View, hits: _Hits) -> None:
    seal = view.seal
    issues = seal.get("issues") if seal is not None else None
    for issue in issues if isinstance(issues, list) else []:
        if not isinstance(issue, dict) or not isinstance(issue.get("code"), str):
            continue
        code = issue["code"]
        if code in _MIRRORED_ISSUES:
            continue
        rule = issue.get("rule")
        rules = [rule_id_of(rule)] if isinstance(rule, str) else []
        ids = [i for i in issue.get("ids", []) if isinstance(i, str)] if isinstance(issue.get("ids"), list) else []
        target = _ISSUE_DETECTORS.get(code)
        if target is None:
            name, variant = "seal_issue", code
        else:
            name, spec = target
            variant = spec(view) if callable(spec) else spec
        for locator in ids or [view.exec_id]:
            hits.add(name, variant, locator, rules=rules, issue=code)


def _payload_not_reaching(view: View, hits: _Hits) -> None:
    if view.sem is None or view.header.get("unit") != "agent_execution":
        return
    task = view.header.get("task")
    if not isinstance(task, dict) or not isinstance(task.get("attack_id"), str):
        return
    statuses: list[str] = []
    for ann in view.sem:
        value = ann.get("value")
        if ann.get("type") == "injection_marker" and isinstance(value, dict) and isinstance(value.get("status"), str):
            statuses.append(value["status"])
    if "present" in statuses:
        return
    if not statuses:
        variant = "no_marker"
    elif all(s == "absent" for s in statuses):
        variant = "absent"
    else:
        variant = "undetermined"
    hits.add("payload_not_reaching_agent", variant, view.exec_id)


_ORDER: Final[tuple[Callable[[View, _Hits], None], ...]] = (
    _empty_execution,
    _harness_imposed,
    _sentinel_time,
    _provider_ids,
    _unexecuted,
    _abnormal_finish,
    _text_encoded,
    _pass_loss,
    _accounting,
    _issues,
    _payload_not_reaching,
)


def run_detectors(view: View) -> list[Hit]:
    """Run every implemented detector over one execution; hits sorted by (detector, variant). Never mutates ``view``."""
    hits = _Hits()
    for detector in _ORDER:
        detector(view, hits)
    return hits.result()
