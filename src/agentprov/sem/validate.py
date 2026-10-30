"""The SEM validator (D8 tier 3; C.14.4): a ``sem/0.1`` document against the AER it annotates and the rule catalogues.

:func:`validate_sem_document` checks a :class:`~agentprov.sem.types.SemDocument` (from the engine or the reader) and
:func:`validate_sem` a file pair. Both return the AER validator's :class:`~agentprov.aer.validate.ValidationReport`
(C.14.1 names that type), whose ``execution_digest`` member carries the **SEM** digest here. The checks, with the
invariant label each finding carries:

========  ======================================================================================  =====================
SEM-V01   every line is canonical JCS; the seal is ``{k, id, n_records, records_sha256}`` with the  ``sem.format``,
          C.11.6 digest and count (C.14.1)                                                         ``sem.seal.*``
SEM-V02   the header is closed and well formed (C.14.1)                                            ``sem.header``
SEM-V03   ``aer_digest`` is the AER execution digest and ``ex`` its id: a stale SEM is invalid     ``sem.aer_digest``,
          (C.14.4)                                                                                 ``sem.ex``
SEM-V04   annotation records are closed and typed, ids ``a<n>`` unique (C.14.2)                    ``sem.schema``,
                                                                                                   ``sem.id``
SEM-V05   every ``target`` exists (AER record, part ``m<n>#<k>``, ``exec`` or an earlier           ``sem.target.*``
          annotation) and has a kind C.14.3 allows for the type
SEM-V06   every premise exists, an annotation premise is earlier, and ``p`` resolves inside       ``sem.premise.*``
          the premise (or is declared in the record's ``unk``)
SEM-V07   ``at`` resolves inside the target; ``span`` is a half-open range of Unicode scalar       ``sem.at``,
          values of the string at ``at``                                                            ``sem.span``
SEM-V08   core values have their C.14.3 shape; no ``outcome`` on a ``harness_default`` judgement   ``sem.value``,
                                                                                                   ``sem.outcome.*``
SEM-V09   a namespaced type is declared in the header ``ns`` and its value matches the schema      ``sem.type.undeclared``,
                                                                                                   ``sem.ns.schema``,
                                                                                                   ``sem.value.schema``
SEM-V10   rule references parse, name a catalogue in the header ``rules`` at that version, exist  ``sem.rule.syntax``,
          and are not ``reserved`` (the marker ``normaliser`` too)                                  ``sem.rule.missing``,
                                                                                                   ``sem.rule.reserved``
SEM-V11   class constraints (C.6.4) and propagation (C.6.5 rule 3): ``ev`` is never stronger than  ``sem.rule.class``,
          its premises; a ``D`` or ``O`` annotation cites no ``I`` rule; an ``I`` annotation cites   ``sem.ev``
          an ``I`` rule unless a premise is already ``I``; ``author`` is ``I`` (C.14.3)
SEM-V12   ``confidence`` ∈ [0, 1]; ``method`` and ``confidence`` come together (C.14.2)             ``sem.method``
========  ======================================================================================  =====================

C.14.4 marks no check release-only, so ``mode`` changes nothing but the report's label. The value schemas of
namespaced types come from the ``profile`` when the caller supplies it (trusted package data; the header must then equal
the profile's declarations); otherwise from the header's own ``ns``, and since that is file content a ``pattern`` keyword
is not run (an unbounded regular expression on untrusted input) and the check is listed in ``skipped``. Findings carry
codes, line numbers, JSON Pointers and ids that match the id grammar; anything else is shown as a length and digest.

:func:`annotation_problems` holds the record-local checks (SEM-V04, V07 shapes, V08 shapes, V09 grammar, V10 syntax, V12)
and is shared with the engine, so a profile cannot emit what the validator rejects on its face.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Collection, Iterator, Mapping
from pathlib import Path
from typing import Any, Final

from agentprov.aer.canon import CanonError, dumps_line
from agentprov.aer.evidence import effective_tag, is_prefix, tag_class, weakest
from agentprov.aer.ids import EXECUTION_ID_RE, LOCAL_ID_RE, PART_ID_RE, split_part_id
from agentprov.aer.locators import pointer_exists, pointer_get
from agentprov.aer.reader import AerDocument, AerFormatError, AerIntegrityError, load_aer
from agentprov.aer.rules import (
    RULE_REF_RE,
    CatalogueUnavailableError,
    RuleCatalogue,
    RuleRegistry,
    parse_rule_ref,
    rule_id_of,
)
from agentprov.aer.types import PART_TYPES
from agentprov.aer.validate import MAX_FINDINGS, Finding, Mode, ValidationReport, _safe
from agentprov.io.jsonschema_subset import check_against_schema, unsupported_keywords
from agentprov.sem.reader import SemFormatError, SemIntegrityError, load_sem
from agentprov.sem.types import (
    ANNOTATION_TYPES,
    CORE_OUTCOME_CLAIMS,
    INTEGRITY_VALUES,
    MARKER_STATUSES,
    ROLE_VALUES,
    SEM_VERSION,
    SemanticsProfile,
    SemDocument,
)

__all__ = [
    "ALLOWED_TARGETS",
    "ANN_ID_RE",
    "HEADER_KEYS",
    "SEM_CHECKS",
    "annotation_problems",
    "validate_sem",
    "validate_sem_document",
]

#: The SEM checks and what each covers (module docstring table).
SEM_CHECKS: Final[Mapping[str, str]] = {
    "SEM-V01": "canonical JCS lines and the seal (C.14.1, C.11.6)",
    "SEM-V02": "closed header (C.14.1)",
    "SEM-V03": "aer_digest and ex bind the annotated AER (C.14.4)",
    "SEM-V04": "closed annotation records with unique ids (C.14.2)",
    "SEM-V05": "targets exist and have an allowed kind (C.14.3)",
    "SEM-V06": "premises exist, are earlier, and their pointers resolve (C.14.2)",
    "SEM-V07": "at and span (C.14.2)",
    "SEM-V08": "core value shapes and outcome origin (C.14.3)",
    "SEM-V09": "namespaced types and their declared schemas (C.14.2, C.14.4)",
    "SEM-V10": "rule references exist in the declared catalogues (C.6.4, C.14.4)",
    "SEM-V11": "evidence class constraints and propagation (C.6.4, C.6.5 rule 3)",
    "SEM-V12": "method and confidence (C.14.2)",
}
_INVARIANT: Final[Mapping[str, str]] = {
    "sem.format": "SEM-V01", "sem.seal.count": "SEM-V01", "sem.seal.digest": "SEM-V01",
    "sem.header": "SEM-V02",
    "sem.aer_digest": "SEM-V03", "sem.ex": "SEM-V03",
    "sem.schema": "SEM-V04", "sem.id": "SEM-V04",
    "sem.target.dangling": "SEM-V05", "sem.target.forward": "SEM-V05", "sem.target.kind": "SEM-V05",
    "sem.premise.dangling": "SEM-V06", "sem.premise.forward": "SEM-V06", "sem.premise.pointer": "SEM-V06",
    "sem.at": "SEM-V07", "sem.span": "SEM-V07",
    "sem.value": "SEM-V08", "sem.outcome.harness_default": "SEM-V08",
    "sem.type.undeclared": "SEM-V09", "sem.ns.schema": "SEM-V09", "sem.value.schema": "SEM-V09",
    "sem.rule.syntax": "SEM-V10", "sem.rule.missing": "SEM-V10", "sem.rule.reserved": "SEM-V10",
    "sem.rule.class": "SEM-V11", "sem.ev": "SEM-V11",
    "sem.method": "SEM-V12",
}  # fmt: skip

#: The closed header members (C.14.1).
HEADER_KEYS: Final = frozenset({"k", "id", "sem", "ex", "aer_digest", "profile", "rules", "ns", "canon", "hash"})
_ANN_REQUIRED: Final = ("k", "id", "target", "type", "value", "ev", "rule", "premises")
_ANN_KEYS: Final = frozenset({*_ANN_REQUIRED, "at", "span", "method", "confidence"})
_SEAL_KEYS: Final = frozenset({"k", "id", "n_records", "records_sha256"})
#: Annotation ids (C.14.2). They cannot collide with AER local ids, whose grammar excludes ``a<n>`` (C.4.2).
ANN_ID_RE: Final = re.compile(r"a(?:0|[1-9][0-9]*)")
_TYPE_NS_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_CATALOGUE_NS_RE: Final = re.compile(r"[a-z][a-z0-9_]*")
_PROFILE_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
_DIGEST_RE: Final = re.compile(r"sha256:[0-9a-f]{64}")

_CONTENT_PARTS: Final = frozenset(f"part:{t}" for t in PART_TYPES)
#: C.14.3 "Allowed targets", as target kinds: an AER record kind, or ``part:<t>`` for a message part of type ``t``.
#: Namespaced types may target any AER record or part, the header ``exec`` or an earlier annotation (``ann``).
ALLOWED_TARGETS: Final[Mapping[str, frozenset[str]]] = {
    "integrity": _CONTENT_PARTS | {"fixture", "artefact"},
    "channel": frozenset({"part:tool_result", "artefact"}),
    "role": frozenset({"tool_execution", "part:tool_call", "activity"}),
    "injection_marker": frozenset({"part:tool_result"}),
    "outcome": frozenset({"judgement"}),
    "author": _CONTENT_PARTS | {"message", "artefact"},
}

type Problem = tuple[str, str, str]  # (code, pointer, detail)


def _is_pointer(value: object) -> bool:
    return isinstance(value, str) and (value == "" or value.startswith("/"))


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _is_ref(value: object) -> bool:
    """A target or premise id: an AER local id or ``exec``, a part id, or an annotation id."""
    return isinstance(value, str) and (
        value == "exec" or LOCAL_ID_RE.fullmatch(value) is not None or PART_ID_RE.fullmatch(value) is not None
        or ANN_ID_RE.fullmatch(value) is not None
    )


# ------------------------------------------------------------------------------------------ record-local checks
def _value_problems(type_: str, value: object, record: Mapping[str, Any]) -> Iterator[Problem]:
    """The C.14.3 value shape of a core type (SEM-V08), without looking anything up in the AER."""
    if type_ == "integrity":
        if value not in INTEGRITY_VALUES:
            yield "sem.value", "/value", "integrity_value"
    elif type_ == "channel":
        if not isinstance(value, str) or value == "":
            yield "sem.value", "/value", "channel_value"
    elif type_ == "role":
        if not isinstance(value, list) or not value:
            yield "sem.value", "/value", "role_not_a_non_empty_array"
        elif any(not isinstance(v, str) or v not in ROLE_VALUES for v in value):
            yield "sem.value", "/value", "role_value"
        elif len(set(value)) != len(value):
            yield "sem.value", "/value", "role_not_unique"
    elif type_ == "injection_marker":
        yield from _marker_problems(value, record)
    elif type_ == "outcome":
        yield from _outcome_problems(value)
    elif type_ == "author":
        if not isinstance(value, dict) or set(value) != {"actor"}:
            yield "sem.value", "/value", "author_shape"
        elif not isinstance(value["actor"], str) or LOCAL_ID_RE.fullmatch(value["actor"]) is None:
            yield "sem.value", "/value/actor", "author_actor_id"


def _marker_problems(value: object, record: Mapping[str, Any]) -> Iterator[Problem]:
    if not isinstance(value, dict) or not set(value) <= {"fixture", "status", "normaliser"}:
        yield "sem.value", "/value", "marker_shape"
        return
    status = value.get("status")
    if status not in MARKER_STATUSES:
        yield "sem.value", "/value/status", "marker_status"
    if "normaliser" not in value:
        yield "sem.value", "/value/normaliser", "marker_normaliser_missing"
    elif not isinstance(value["normaliser"], str) or RULE_REF_RE.fullmatch(value["normaliser"]) is None:
        yield "sem.rule.syntax", "/value/normaliser", "not_a_rule_reference"
    if "fixture" in value:
        if not isinstance(value["fixture"], str) or LOCAL_ID_RE.fullmatch(value["fixture"]) is None:
            yield "sem.value", "/value/fixture", "marker_fixture_id"
    elif status != "gap":  # a missing fixture is exactly what ``gap`` reports (C.14.3)
        yield "sem.value", "/value/fixture", "marker_fixture_missing"
    # ``at``/``span`` locate a payload found verbatim; a payload found only in a decoded reading has no location in the
    # text, so a ``present`` marker may omit them (EF E.7.3: span "when SEM gives a span"; C.14.6).


def _outcome_problems(value: object) -> Iterator[Problem]:
    if not isinstance(value, dict) or not set(value) <= {"claim", "holds", "score", "scale"} or "claim" not in value:
        yield "sem.value", "/value", "outcome_shape"
        return
    claim = value["claim"]
    if not isinstance(claim, str) or not (claim in CORE_OUTCOME_CLAIMS or _TYPE_NS_RE.fullmatch(claim)):
        yield "sem.value", "/value/claim", "outcome_claim"
    if "holds" in value and not isinstance(value["holds"], bool):
        yield "sem.value", "/value/holds", "outcome_holds"
    if "score" in value and not _is_number(value["score"]):
        yield "sem.value", "/value/score", "outcome_score"
    if "scale" in value and (not isinstance(value["scale"], str) or value["scale"] == ""):
        yield "sem.value", "/value/scale", "outcome_scale"


def annotation_problems(record: Mapping[str, Any], *, declared_types: Collection[str] | None = None) -> list[Problem]:
    """The record-local problems of one ``k: "ann"`` record (shape, grammar, core value shapes); ``[]`` when none.

    ``declared_types`` is the set of namespaced types the header (or profile) declares; ``None`` skips that check.
    Shared by the engine (a profile defect) and the validator (a finding).
    """
    out: list[Problem] = []
    for key in _ANN_REQUIRED:
        if key not in record:
            out.append(("sem.schema", "/" + key, "required"))
    for key in record:
        if key not in _ANN_KEYS:
            out.append(("sem.schema", "/" + _safe(key), "not_allowed"))
    if record.get("k") != "ann":
        out.append(("sem.schema", "/k", "not_ann"))
    if "id" in record and (not isinstance(record["id"], str) or ANN_ID_RE.fullmatch(record["id"]) is None):
        out.append(("sem.id", "/id", "not_an_annotation_id"))
    if "target" in record and not _is_ref(record["target"]):
        out.append(("sem.schema", "/target", "not_an_id"))
    type_ = record.get("type")
    if "type" in record:
        if not isinstance(type_, str) or (type_ not in ANNOTATION_TYPES and _TYPE_NS_RE.fullmatch(type_) is None):
            out.append(("sem.schema", "/type", "not_a_type"))
        elif type_ not in ANNOTATION_TYPES and declared_types is not None and type_ not in declared_types:
            out.append(("sem.type.undeclared", "/type", _safe(type_)))
    ev = record.get("ev")
    if "ev" in record and ev not in ("O", "D", "I"):
        out.append(("sem.schema", "/ev", "not_a_class"))
    if type_ == "author" and ev in ("O", "D"):
        out.append(("sem.ev", "/ev", "authorship_claim_not_I"))
    rules = record.get("rule")
    if "rule" in record:
        if not isinstance(rules, list) or not rules:
            out.append(("sem.schema", "/rule", "not_a_non_empty_array"))
        else:
            for i, ref in enumerate(rules):
                if not isinstance(ref, str) or RULE_REF_RE.fullmatch(ref) is None:
                    out.append(("sem.rule.syntax", f"/rule/{i}", "not_a_rule_reference"))
    premises = record.get("premises")
    if "premises" in record:
        if not isinstance(premises, list):
            out.append(("sem.schema", "/premises", "not_an_array"))
        else:
            for i, premise in enumerate(premises):
                if not isinstance(premise, dict) or set(premise) != {"id", "p"}:
                    out.append(("sem.schema", f"/premises/{i}", "premise_shape"))
                elif not _is_ref(premise["id"]):
                    out.append(("sem.schema", f"/premises/{i}/id", "not_an_id"))
                elif not _is_pointer(premise["p"]):
                    out.append(("sem.schema", f"/premises/{i}/p", "not_a_pointer"))
    if "at" in record and not _is_pointer(record["at"]):
        out.append(("sem.at", "/at", "not_a_pointer"))
    if "span" in record:
        span = record["span"]
        if (not isinstance(span, list) or len(span) != 2
                or any(isinstance(x, bool) or not isinstance(x, int) for x in span)):
            out.append(("sem.span", "/span", "not_a_pair_of_integers"))
        elif not 0 <= span[0] <= span[1]:
            out.append(("sem.span", "/span", "not_a_half_open_range"))
        if "at" not in record:
            out.append(("sem.span", "/span", "span_without_at"))
    if "method" in record and (not isinstance(record["method"], str) or record["method"] == ""):
        out.append(("sem.method", "/method", "not_a_string"))
    if "confidence" in record:
        confidence = record["confidence"]
        if not _is_number(confidence) or not 0 <= confidence <= 1:
            out.append(("sem.method", "/confidence", "not_in_unit_interval"))
        if "method" not in record:
            out.append(("sem.method", "/method", "confidence_without_method"))
    elif "method" in record:
        out.append(("sem.method", "/confidence", "method_without_confidence"))
    if isinstance(type_, str) and type_ in ANNOTATION_TYPES and "value" in record:
        out.extend(_value_problems(type_, record["value"], record))
    return out


# ------------------------------------------------------------------------------------------ the validator
class _Validator:
    """One validation run: the AER index, the header's declarations and the annotations seen so far."""

    def __init__(
        self,
        sem: SemDocument,
        aer: AerDocument,
        *,
        catalogues: RuleRegistry,
        mode: Mode,
        profile: SemanticsProfile | None,
    ) -> None:
        self.sem = sem
        self.aer = aer
        self.cats = catalogues
        self.mode = mode
        self.profile = profile
        self.findings: list[Finding] = []
        self.truncated = False
        self.skipped: set[str] = set()
        self.declared_rules: dict[str, int] = {}
        self.catalogues: dict[str, RuleCatalogue | None] = {}
        self.schemas: dict[str, Mapping[str, Any]] = {}
        self.schemas_trusted = False
        self.declared_types: set[str] = set()
        self.earlier: dict[str, dict[str, Any]] = {}
        self.all_ids = {str(r.get("id")) for r in sem.records[1:]}

    def add(self, code: str, line: int | None, pointer: str = "", detail: str = "") -> None:
        if len(self.findings) >= MAX_FINDINGS:
            self.truncated = True
            return
        self.findings.append(Finding(code, _INVARIANT[code], line, pointer, "error", detail))

    # -------------------------------------------------------------------------------------- run
    def run(self) -> ValidationReport:
        self.lines()
        self.header()
        for index, record in enumerate(self.sem.records[1:], start=1):
            self.annotation(index, record)
            rid = record.get("id")
            if isinstance(rid, str) and rid not in self.earlier:
                self.earlier[rid] = record
        return ValidationReport(
            findings=tuple(self.findings),
            skipped=tuple(sorted(self.skipped)),
            deferred=("SEM digest chained into the corpus manifest after the AER digest (corpus tier, D9)",),
            n_records=len(self.sem.records) + 1,
            execution_digest=self.sem.digest,
            accounting_status=None,
            mode=self.mode,
            truncated=self.truncated,
            ex=self.sem.ex if isinstance(self.sem.header.get("ex"), str) else None,
        )

    # -------------------------------------------------------------------------------------- SEM-V01
    def lines(self) -> None:
        """Re-serialise every record: the document must be what its seal and digest say (JCS + C.11.6)."""
        body = hashlib.sha256()
        for index, record in enumerate(self.sem.records):
            try:
                body.update(dumps_line(record))
            except CanonError:
                self.add("sem.format", index, "", "not_representable_in_JCS")
        if not self.sem.records or self.sem.records[0] is not self.sem.header:
            self.add("sem.format", 0, "", "header_is_not_line_0")
        seal, line = self.sem.seal, len(self.sem.records)
        if not isinstance(seal, dict) or set(seal) != _SEAL_KEYS or seal.get("k") != "seal" or seal.get("id") != "seal":
            self.add("sem.format", line, "", "seal_not_closed")
            return
        if seal.get("n_records") != len(self.sem.records) + 1:
            self.add("sem.seal.count", line, "/n_records")
        digest = body.hexdigest()
        if seal.get("records_sha256") != digest or self.sem.digest != digest:
            self.add("sem.seal.digest", line, "/records_sha256")

    # -------------------------------------------------------------------------------------- SEM-V02, V03, V09 (ns)
    def header(self) -> None:
        h = self.sem.header
        for key in sorted(HEADER_KEYS - set(h)):
            self.add("sem.header", 0, "/" + key, "required")
        for key in sorted(set(h) - HEADER_KEYS, key=str):
            self.add("sem.header", 0, "/" + _safe(key), "not_allowed")
        for key, want in (("k", "sem"), ("id", "sem"), ("sem", SEM_VERSION), ("canon", "jcs-rfc8785"), ("hash", "sha256")):
            if key in h and h[key] != want:
                self.add("sem.header", 0, "/" + key, "fixed_value")
        ex = h.get("ex")
        if "ex" in h:
            if not isinstance(ex, str) or EXECUTION_ID_RE.fullmatch(ex) is None:
                self.add("sem.header", 0, "/ex", "not_an_execution_id")
            elif ex != self.aer.ex:
                self.add("sem.ex", 0, "/ex", "differs_from_the_AER")
        digest = h.get("aer_digest")
        if "aer_digest" in h:
            if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
                self.add("sem.header", 0, "/aer_digest", "not_a_digest")
            elif digest != "sha256:" + self.aer.execution_digest:
                self.add("sem.aer_digest", 0, "/aer_digest", "stale")
        profile = h.get("profile")
        if "profile" in h and not (
            isinstance(profile, dict) and set(profile) == {"id", "version"}
            and isinstance(profile["id"], str) and _PROFILE_ID_RE.fullmatch(profile["id"])
            and isinstance(profile["version"], int) and not isinstance(profile["version"], bool) and profile["version"] >= 1
        ):
            self.add("sem.header", 0, "/profile", "profile_shape")
        rules = h.get("rules")
        if "rules" in h:
            if not isinstance(rules, dict):
                self.add("sem.header", 0, "/rules", "not_an_object")
            else:
                for ns, version in rules.items():
                    if (not isinstance(ns, str) or _CATALOGUE_NS_RE.fullmatch(ns) is None
                            or isinstance(version, bool) or not isinstance(version, int) or version < 1):
                        self.add("sem.header", 0, "/rules/" + _safe(ns), "catalogue_version")
                        continue
                    self.declared_rules[ns] = version
        for ns, version in sorted(self.declared_rules.items()):
            try:
                self.catalogues[ns] = self.cats.get(ns, version)
            except CatalogueUnavailableError:
                self.catalogues[ns] = None
                self.add("sem.rule.missing", 0, "/rules/" + ns, "catalogue_unavailable")
        ns_decl = h.get("ns")
        header_schemas: dict[str, Mapping[str, Any]] = {}
        if "ns" in h:
            if not isinstance(ns_decl, dict):
                self.add("sem.header", 0, "/ns", "not_an_object")
            else:
                for name, schema in ns_decl.items():
                    if not isinstance(name, str) or _TYPE_NS_RE.fullmatch(name) is None:
                        self.add("sem.header", 0, "/ns/" + _safe(name), "not_a_namespaced_type")
                    elif unsupported_keywords(schema):
                        self.add("sem.ns.schema", 0, "/ns/" + name, "unsupported_schema")
                    else:
                        header_schemas[name] = schema
        self.schemas = header_schemas
        self.declared_types = {n for n in ns_decl if isinstance(n, str)} if isinstance(ns_decl, dict) else set()
        if self.profile is not None:
            self.check_profile(profile, rules, ns_decl)

    def check_profile(self, profile: object, rules: object, ns_decl: object) -> None:
        """With the profile in hand, the header must state exactly its declarations, and its schemas are trusted."""
        p = self.profile
        assert p is not None
        if profile != {"id": p.id, "version": p.version}:
            self.add("sem.header", 0, "/profile", "differs_from_the_profile")
        if rules != dict(p.rules):
            self.add("sem.header", 0, "/rules", "differs_from_the_profile")
        if ns_decl != dict(p.ns):
            self.add("sem.header", 0, "/ns", "differs_from_the_profile")
        trusted: dict[str, Mapping[str, Any]] = {}
        for name, schema in p.ns.items():
            if isinstance(schema, dict) and not unsupported_keywords(schema):
                trusted[name] = schema
        self.schemas, self.schemas_trusted = trusted, True

    # -------------------------------------------------------------------------------------- per annotation
    def annotation(self, line: int, rec: dict[str, Any]) -> None:
        problems = annotation_problems(rec, declared_types=self.declared_types)
        for code, pointer, detail in problems:
            self.add(code, line, pointer, detail)
        rid = rec.get("id")
        if isinstance(rid, str) and rid in self.earlier:
            self.add("sem.id", line, "/id", "duplicate")
        broken = {p for _, p, _ in problems}
        type_ = rec.get("type")
        target = self.resolve_target(line, rec) if "/target" not in broken else None
        if target is not None and isinstance(type_, str):
            kind, obj = target
            allowed = ALLOWED_TARGETS.get(type_)
            if allowed is not None and kind not in allowed:
                self.add("sem.target.kind", line, "/target", f"{type_}_on_{kind}")
            self.at_and_span(line, rec, obj, broken)
        if isinstance(type_, str):
            self.values_in_context(line, rec, type_, broken)
        tags = self.premises(line, rec) if "/premises" not in broken else None
        self.rules(line, rec, tags)

    def resolve(self, ref: str) -> tuple[str, dict[str, Any], dict[str, Any], str] | None:
        """``(kind, object, record, prefix)`` of an id: the object addressed, the record holding it (for evidence tags
        and ``unk``) and the pointer prefix of the object inside that record. ``None`` when nothing has that id."""
        if ANN_ID_RE.fullmatch(ref):
            ann = self.earlier.get(ref)
            return ("ann", ann, ann, "") if ann is not None else None
        if PART_ID_RE.fullmatch(ref):
            try:
                base, k = split_part_id(ref)
            except ValueError:  # an ordinal out of range (more than 18 digits) addresses nothing
                return None
            message, part = self.aer.get(base), self.aer.part(ref)
            if message is None or part is None:
                return None
            return f"part:{part.get('t')}", part, message, f"/parts/{k}"
        record = self.aer.get(ref)
        if record is None or record.get("k") == "seal":
            return None
        return str(record.get("k")), record, record, ""

    def resolve_target(self, line: int, rec: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
        target = rec.get("target")
        if not isinstance(target, str):
            return None
        found = self.resolve(target)
        if found is None:
            forward = ANN_ID_RE.fullmatch(target) is not None and target in self.all_ids
            self.add("sem.target.forward" if forward else "sem.target.dangling", line, "/target", _safe(target))
            return None
        return found[0], found[1]

    def at_and_span(self, line: int, rec: Mapping[str, Any], obj: dict[str, Any], broken: set[str]) -> None:
        if "at" not in rec or "/at" in broken:
            return
        try:
            located = pointer_get(obj, rec["at"])
        except KeyError:
            self.add("sem.at", line, "/at", "does_not_resolve_in_the_target")
            return
        if "span" not in rec or "/span" in broken:
            return
        if not isinstance(located, str):
            self.add("sem.span", line, "/span", "at_is_not_a_string")
        elif rec["span"][1] > len(located):  # Python str length counts Unicode scalar values (C.14.2)
            self.add("sem.span", line, "/span", "beyond_the_string")

    def values_in_context(self, line: int, rec: Mapping[str, Any], type_: str, broken: set[str]) -> None:
        value = rec.get("value")
        if type_ == "injection_marker" and isinstance(value, dict):
            fixture = value.get("fixture")
            if isinstance(fixture, str) and "/value/fixture" not in broken:
                found = self.aer.get(fixture)
                if found is None or found.get("k") != "fixture":
                    self.add("sem.value", line, "/value/fixture", "not_a_fixture_of_the_AER")
            normaliser = value.get("normaliser")
            if isinstance(normaliser, str) and "/value/normaliser" not in broken:
                self.rule_exists(line, "/value/normaliser", normaliser)
        elif type_ == "author" and isinstance(value, dict) and "/value" not in broken and "/value/actor" not in broken:
            actor = self.aer.get(str(value.get("actor")))
            if actor is None or actor.get("k") != "actor":
                self.add("sem.value", line, "/value/actor", "not_an_actor_of_the_AER")
        elif type_ == "outcome":
            target = self.aer.get(str(rec.get("target")))
            if target is not None and target.get("k") == "judgement" and target.get("origin") == "harness_default":
                self.add("sem.outcome.harness_default", line, "/target", "harness_default_judgement")
        elif type_ not in ANNOTATION_TYPES and type_ in self.schemas and "value" in rec:
            skipped: list[str] = []
            problems = check_against_schema(value, self.schemas[type_], patterns=self.schemas_trusted, skipped=skipped)
            if problems:
                self.add("sem.value.schema", line, "/value", f"{len(problems)}_schema_violations")
            if skipped:
                self.skipped.add("SEM-V09: pattern keywords of header-declared schemas (no trusted profile given)")

    def premises(self, line: int, rec: Mapping[str, Any]) -> list[str] | None:
        """Check every premise; return the evidence classes of those that resolve (``None`` when one does not)."""
        premises = rec.get("premises")
        if not isinstance(premises, list):
            return None
        tags: list[str] = []
        ok = True
        for i, premise in enumerate(premises):
            if not isinstance(premise, dict) or not isinstance(premise.get("id"), str):
                return None
            ref, pointer = premise["id"], premise.get("p")
            found = self.resolve(ref)
            if found is None:
                forward = ANN_ID_RE.fullmatch(ref) is not None and ref in self.all_ids
                self.add("sem.premise.forward" if forward else "sem.premise.dangling", line, f"/premises/{i}/id", _safe(ref))
                ok = False
                continue
            kind, obj, holder, prefix = found
            if not isinstance(pointer, str):
                ok = False
                continue
            if not (pointer_exists(obj, pointer) or (kind != "ann" and _unk_covers(holder, prefix + pointer))):
                self.add("sem.premise.pointer", line, f"/premises/{i}/p", _safe(ref))
                ok = False
                continue
            tag = holder.get("ev") if kind == "ann" else _tag(holder, prefix + pointer)
            if tag in ("O", "D", "I"):
                tags.append(tag)
            else:
                ok = False
        return tags if ok else None

    # -------------------------------------------------------------------------------------- SEM-V10, V11
    def rule_exists(self, line: int, pointer: str, ref: str) -> str | None:
        """The class of the rule ``ref`` names, or ``None`` after reporting why it is not citable."""
        if RULE_REF_RE.fullmatch(ref) is None:
            return None
        try:
            parsed = parse_rule_ref(ref)
        except ValueError:  # a version too long for int: the grammar matches, but no catalogue can hold the rule
            self.add("sem.rule.missing", line, pointer, _safe(rule_id_of(ref)))
            return None
        if parsed.namespace not in self.declared_rules:
            self.add("sem.rule.missing", line, pointer, "catalogue_not_declared_in_header")
            return None
        catalogue = self.catalogues.get(parsed.namespace)
        if catalogue is None:  # unavailable, reported once on the header
            return None
        entry = catalogue.get(parsed.rule_id)
        if entry is None:
            self.add("sem.rule.missing", line, pointer, _safe(parsed.rule_id))
            return None
        if entry.status == "reserved":
            self.add("sem.rule.reserved", line, pointer, _safe(parsed.rule_id))
            return None
        return entry.cls

    def rules(self, line: int, rec: Mapping[str, Any], premise_tags: list[str] | None) -> None:
        refs = rec.get("rule")
        if not isinstance(refs, list):
            return
        classes: list[str] = []
        complete = True
        for i, ref in enumerate(refs):
            if not isinstance(ref, str) or RULE_REF_RE.fullmatch(ref) is None:
                complete = False
                continue
            try:
                pointer = parse_rule_ref(ref).pointer
            except ValueError:  # a version too long for int, reported by rule_exists below
                pointer = None
            if pointer is not None and not pointer_exists(rec, pointer):
                self.add("sem.rule.syntax", line, f"/rule/{i}", "scope_pointer_does_not_resolve")
            cls = self.rule_exists(line, f"/rule/{i}", ref)
            if cls is None:
                complete = False
            else:
                classes.append(cls)
        ev = rec.get("ev")
        if ev not in ("O", "D", "I"):
            return
        if ev in ("O", "D") and "I" in classes:
            self.add("sem.rule.class", line, "/rule", f"{ev}_annotation_with_I_rule")
        premise_class = weakest(*premise_tags) if premise_tags else None
        if ev == "I" and complete and "I" not in classes and premise_class != "I":
            self.add("sem.rule.class", line, "/rule", "I_annotation_without_I_rule")
        if premise_class is not None and _RANK[ev] < _RANK[premise_class]:
            self.add("sem.ev", line, "/ev", f"{ev}_stronger_than_premises_{premise_class}")
        if rec.get("premises") == []:  # pre-round review #34: with no premises the bound is the rule's class (C.6.5 rule 3)
            if ev == "O":
                self.add("sem.ev", line, "/ev", "O_annotation_without_premises")
            elif complete and classes and _RANK[ev] < _RANK[weakest(*classes)]:
                self.add("sem.ev", line, "/ev", f"{ev}_stronger_than_rules_{weakest(*classes)}")


_RANK: Final = {"O": 0, "D": 1, "I": 2}


def _unk_covers(record: Mapping[str, Any], pointer: str) -> bool:
    unk = record.get("unk")
    return isinstance(unk, dict) and any(isinstance(q, str) and is_prefix(q, pointer) for q in unk)


def _tag(record: Mapping[str, Any], pointer: str) -> str | None:
    try:
        return tag_class(effective_tag(record, pointer))
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------ entry points
def validate_sem_document(
    sem: SemDocument,
    aer: AerDocument,
    *,
    catalogues: RuleRegistry | None = None,
    mode: Mode = "release",
    profile: SemanticsProfile | None = None,
) -> ValidationReport:
    """Every C.14.4 check of ``sem`` against ``aer`` (a loaded, verified AER).

    ``catalogues`` supplies the catalogues the header's ``rules`` names (default: package resources,
    :meth:`RuleRegistry.default`). ``profile``, when given, is the semantics profile the header names: the header must
    equal its declarations and namespaced values are checked against its (trusted) schemas.
    """
    if mode not in ("dev", "release"):
        raise ValueError("mode must be 'dev' or 'release'")
    registry = catalogues if catalogues is not None else RuleRegistry.default()
    return _Validator(sem, aer, catalogues=registry, mode=mode, profile=profile).run()


def validate_sem(
    path: Path | str,
    aer_path: Path | str,
    *,
    catalogues: RuleRegistry | None = None,
    mode: Mode = "release",
    profile: SemanticsProfile | None = None,
) -> ValidationReport:
    """Validate the SEM file ``path`` against the AER file ``aer_path`` (C.14.1 signature).

    A SEM file that cannot be read (framing, strict parse, canonical form, seal) gives a report with that one finding;
    an AER that cannot be read is tier 2's failure and gives one ``sem.aer_digest`` finding (the binding cannot hold).
    """
    try:
        aer = load_aer(aer_path)
    except (AerFormatError, AerIntegrityError, OSError):
        return _single("sem.aer_digest", None, "/aer_digest", "AER_unreadable", mode)
    try:
        sem = load_sem(path)
    except SemIntegrityError as exc:
        return _single(exc.code, None, "", "seal", mode)
    except (SemFormatError, OSError):
        return _single("sem.format", None, "", "unreadable", mode)
    return validate_sem_document(sem, aer, catalogues=catalogues, mode=mode, profile=profile)


def _single(code: str, line: int | None, pointer: str, detail: str, mode: Mode) -> ValidationReport:
    finding = Finding(code, _INVARIANT.get(code, "SEM-V01"), line, pointer, "error", detail)
    return ValidationReport(
        findings=(finding,), skipped=(), deferred=(), n_records=0, execution_digest=None, accounting_status=None, mode=mode
    )
