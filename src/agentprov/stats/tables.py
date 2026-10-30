"""The generic tables of ``agentprov stats`` (MN N.2.12; K.5.11; PQ Q.32; O.3.5 "Shared statistics").

One pass over a corpus, streamed in index order, computes the requested tables **per corpus, never pooled** (N.2.12):

``counts``
    per ``(source_id, profile)``: records by index ``status``, ``unit``, ``execution_observed`` and ``completeness``;
    ``n_executions`` = ``unit == agent_execution ∧ execution_observed`` (R-28), ``n_outcome_only``; rows with output for
    the PROV spec; ``rate_excluded`` (rows a family-declared rate exclusion matches, :mod:`agentprov.stats.exclusions`);
    the registry parts and import statuses of the profile (I.5.1; the registry is the only status store). A second row set,
    ``register``, counts the register entries by ``(stage, code, severity, disposition)``.
``statements``
    PROV statements by ``(source_id, profile, bundle, method, stype, evidence, rule)``, recounted from the stored PROV-JSON
    (the engine's report is not stored). A statement is an entry of a PROV-JSON section that carries
    ``apv:evidenceClass``; bundles are ``core``, ``inference``, ``assessment`` (from the E.4.2 bundle IRI) and
    ``toplevel``; ``method`` is the inference method slug or the assessment profile slug. Entries without a class (the
    unidentified ``specializationOf``, ``mentionOf``, ``hadMember``) are counted apart, in ``statements_structural``.
    With ``per_execution`` the same counts are also given at execution grain, ``statements_by_execution`` (O.3.5's
    ``statements`` frame: ``ex × bundle × stype × evidence × rule``).
``unknowns``
    per ``(source_id, profile)`` and field-group occurrence source (C.3.16): occurrences by status (``O``, ``D``, ``I`` and
    the seven C.7.1 reasons), their shares (summing to 1), and how many ``not_recorded`` were undeclared absences.
``field_groups``
    the information-loss table (R-57): per ``(source_id, profile)`` and group, cells by status and the field-group coverage
    ``(O + D) / (cells − not_applicable)``; the observed share ``O / (cells − not_applicable)`` is composition only. A
    row with ``group == "all"`` aggregates every (execution, group) cell of the list (O.3.5 ``fg_coverage_pct``).
``artefacts`` (``stats --artefacts``; D.15.4)
    the shared artefact layer's :func:`agentprov.artefacts.scan` over every selected execution and its :func:`table`, per
    ``(source_id, profile, model)``.

The population of ``unknowns`` and ``field_groups`` is ``unit == agent_execution ∧ execution_observed`` (C.3.16, O.3.5),
less the executions a family-declared exclusion takes out of that rate (reported in the rows' ``excluded`` column; no
source name or source-specific code appears here, D.16.17 item 4).
Inputs are read through :class:`agentprov.corpus.reader.CorpusReader` (strict, size-limited, chain-checked); no raw
artefact is read and nothing is written. A file that cannot be read is a *failure* (counted by code, exit 1), never a
silent skip. Labels are closed-vocabulary values or pass ``escape_untrusted_line`` (G.8.6): one line, so a label cannot
add rows or headings to the ``text`` and ``markdown`` tables (F-12C-04).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.aer.reader import AerDocument
from agentprov.aer.types import UNKNOWN_REASONS
from agentprov.corpus.index import IndexRow
from agentprov.corpus.reader import CorpusReadError
from agentprov.errors import AgentProvError
from agentprov.ingest.quote import escape_untrusted_line
from agentprov.io.canonical import jcs_bytes
from agentprov.stats.exclusions import Exclusion, declared_exclusions, excluded_from
from agentprov.stats.fieldgroups import STATUSES, FieldGroup, evaluate, field_groups
from agentprov.stats.source import StatsCorpus, row_matches

__all__ = [
    "BUNDLES",
    "DEFAULT_TABLES",
    "OPTIONAL_TABLES",
    "PROV_SPECS",
    "TABLES",
    "CorpusTables",
    "StatsInputError",
    "compute_corpus",
    "model_ids",
    "model_label",
    "prov_statements",
    "share",
]

#: The four tables of N.2.12, in their order.
TABLES: Final = ("counts", "statements", "unknowns", "field_groups")
DEFAULT_TABLES: Final = TABLES
#: Tables that are only computed on request (``stats --artefacts``).
OPTIONAL_TABLES: Final = ("artefacts",)
#: The provenance specs whose PROV files ``stats`` reads; only the first has a closed rule catalogue.
PROV_SPECS: Final = ("agentprov-prov/0.1", "adprov-v2.3-compat")
BUNDLES: Final = ("core", "inference", "assessment", "toplevel")
EVIDENCE: Final = {"apv:Observed": "O", "apv:Derived": "D", "apv:Inferred": "I"}
#: The PROV-JSON section names (W3C PROV-JSON; ``prefix`` and ``bundle`` are structure, not statements).
PROV_SECTIONS: Final = frozenset({
    "entity", "activity", "agent", "wasGeneratedBy", "used", "wasInformedBy", "wasStartedBy", "wasEndedBy",
    "wasInvalidatedBy", "wasDerivedFrom", "wasAttributedTo", "wasAssociatedWith", "actedOnBehalfOf", "wasInfluencedBy",
    "alternateOf", "specializationOf", "mentionOf", "hadMember"})  # fmt: skip
_BUNDLE_RE: Final = re.compile(r"xd:bundle\.(?:(core)|(inf|assess)\.([a-z0-9][a-z0-9_-]*))\.([a-z2-7]+)")
_BUNDLE_KIND: Final = {"core": "core", "inf": "inference", "assess": "assessment"}
_RULE_ID_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+@[1-9][0-9]*")
_REASONS_DISPLAY: Final = tuple(UNKNOWN_REASONS)
_LABEL_CHARS: Final = 200
_SHARE_DIGITS: Final = 6
_MODEL_KEY_HEX: Final = 12

#: The artefact table's grouping key: (source_id, profile, sorted requested model ids or ``None``).
_ArtefactKey = tuple[str, str, tuple[str, ...] | None]


class StatsInputError(AgentProvError):
    """A stored file that ``stats`` reads is not what the format says (exit 1; counted per execution)."""

    code = "stats.input.invalid"
    exit_code = 1


def share(numerator: int, denominator: int) -> float | None:
    """``numerator / denominator`` rounded to six decimals (JCS-stable); ``None`` for a zero denominator."""
    return None if denominator == 0 else round(numerator / denominator, _SHARE_DIGITS)


def _label(value: str) -> str:
    return escape_untrusted_line(value, max_chars=_LABEL_CHARS)


# ------------------------------------------------------------------------------------------------ PROV statements
def _evidence_letter(value: object) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("$")
    return EVIDENCE.get(value) if isinstance(value, str) else None


def _bundle_of(name: object) -> tuple[str, str]:
    match = _BUNDLE_RE.fullmatch(name) if isinstance(name, str) else None
    if match is None:
        raise StatsInputError("a bundle name is not an E.4.2 bundle IRI", code="stats.prov.bundle")
    if match.group(1):
        return "core", ""
    return _BUNDLE_KIND[match.group(2)], match.group(3)


def _count_sections(
    content: Mapping[str, Any],
    bundle: tuple[str, str],
    rules: frozenset[str] | None,
    classified: Counter[tuple[str, str, str, str, str]],
    structural: Counter[tuple[str, str, str]],
    unknown_rules: Counter[str],
) -> None:
    for section, entries in content.items():
        if section in ("prefix", "bundle"):
            continue
        if section not in PROV_SECTIONS or not isinstance(entries, Mapping):
            raise StatsInputError("a PROV-JSON section is not a PROV statement type", code="stats.prov.section")
        for value in entries.values():
            for entry in value if isinstance(value, list) else [value]:
                if not isinstance(entry, Mapping):
                    raise StatsInputError("a PROV-JSON statement is not an object", code="stats.prov.statement")
                if "apv:evidenceClass" not in entry:
                    structural[(bundle[0], bundle[1], section)] += 1
                    continue
                letter = _evidence_letter(entry["apv:evidenceClass"])
                rule = entry.get("apv:rule")
                if letter is None or not isinstance(rule, str):
                    raise StatsInputError("a classified statement has an apv: class and one rule id", code="stats.prov.evidence")
                if _RULE_ID_RE.fullmatch(rule) is None or (rules is not None and rule not in rules):
                    unknown_rules[rule] += 1
                    rule = _label(rule)
                classified[(bundle[0], bundle[1], section, letter, rule)] += 1


def prov_statements(
    document: object, *, rules: frozenset[str] | None = None
) -> tuple[Counter[tuple[str, str, str, str, str]], Counter[tuple[str, str, str]], Counter[str]]:
    """Count the statements of one bundled PROV-JSON document.

    Returns ``(classified, structural, unknown_rules)``: ``classified`` keyed ``(bundle, method, stype, evidence, rule)``,
    ``structural`` keyed ``(bundle, method, stype)``, and the rule ids that are not in ``rules`` (when given) or not
    rule ids at all (those are counted under their escaped text). :class:`StatsInputError` for a malformed document."""
    if not isinstance(document, Mapping):
        raise StatsInputError("a PROV-JSON document is an object", code="stats.prov.document")
    classified: Counter[tuple[str, str, str, str, str]] = Counter()
    structural: Counter[tuple[str, str, str]] = Counter()
    unknown: Counter[str] = Counter()
    _count_sections(document, ("toplevel", ""), rules, classified, structural, unknown)
    bundles = document.get("bundle", {})
    if not isinstance(bundles, Mapping):
        raise StatsInputError("the bundle member is an object", code="stats.prov.document")
    for name, content in bundles.items():
        if not isinstance(content, Mapping):
            raise StatsInputError("a bundle is an object", code="stats.prov.document")
        _count_sections(content, _bundle_of(name), rules, classified, structural, unknown)
    return classified, structural, unknown


def _spec_rules(spec: str) -> frozenset[str] | None:
    if spec != "agentprov-prov/0.1":
        return None
    from agentprov.prov.specs import load_spec

    return frozenset(load_spec().rules)


# ------------------------------------------------------------------------------------------------ helpers
def model_ids(document: AerDocument) -> tuple[str, ...] | None:
    """The distinct requested model ids of the execution's ``llm_agent`` actors, sorted; ``None`` when no such actor
    records one (never a placeholder, C.7.3). This is the model identity; :func:`model_label` is only its display."""
    models = set()
    for rec in document.of_kind("actor"):
        model = rec.get("model")
        if rec.get("kind") == "llm_agent" and isinstance(model, Mapping) and isinstance(model.get("requested"), str):
            models.add(model["requested"])
    return tuple(sorted(models)) or None


def _models_label(models: tuple[str, ...] | None) -> str | None:
    return _label(",".join(models)) if models else None


def model_label(document: AerDocument) -> str | None:
    """The requested model ids of the execution's ``llm_agent`` actors, sorted, joined by ``,`` and escaped; ``None``
    when no such actor records one (never a placeholder, C.7.3). Truncation and the ``,`` join make it a display
    label only: distinct id sets can share it, so nothing groups on it (CB-33)."""
    return _models_label(model_ids(document))


def _registry_parts(source_id: str, profile: str) -> tuple[list[str], list[str]]:
    from agentprov.adapters.registry import get_source

    try:
        registration = get_source(source_id)
    except KeyError:
        return [], []
    profile_id = profile.rpartition("@")[0]
    caps = [c for c in registration.capabilities if c.profile == profile_id]
    return sorted({c.part for c in caps}), sorted({c.import_status for c in caps if c.import_status is not None})


@dataclass(slots=True)
class _SourceAcc:
    rows: int = 0
    n_executions: int = 0
    status: Counter[str] = field(default_factory=Counter)
    unit: Counter[str] = field(default_factory=Counter)
    observed: Counter[bool] = field(default_factory=Counter)
    completeness: Counter[str] = field(default_factory=Counter)
    prov_output: int = 0
    excluded_any: int = 0
    excluded_field_groups: int = 0
    excluded_unknowns: int = 0
    occurrences: dict[str, Counter[tuple[str, bool]]] = field(default_factory=dict)
    cells: dict[str, Counter[tuple[str, bool]]] = field(default_factory=dict)
    statements: Counter[tuple[str, str, str, str, str]] = field(default_factory=Counter)
    structural: Counter[tuple[str, str, str]] = field(default_factory=Counter)


@dataclass(slots=True)
class CorpusTables:
    """The tables of one corpus: its identity label, population, row sets, failures and notices."""

    identity: dict[str, Any]
    population: dict[str, int]
    tables: dict[str, list[dict[str, Any]]]
    failures: dict[str, int] = field(default_factory=dict)
    failure_list: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "corpus": self.identity,
            "failures": dict(sorted(self.failures.items())),
            "population": dict(sorted(self.population.items())),
            "tables": {name: rows for name, rows in self.tables.items()},
        }


# ------------------------------------------------------------------------------------------------ the pass
def _status_columns(counter: Counter[tuple[str, bool]]) -> dict[str, int]:
    by_status: Counter[str] = Counter()
    for (status, _undeclared), n in counter.items():
        by_status[status] += n
    out = {s.removeprefix("unk:"): by_status.get(s, 0) for s in STATUSES}
    out["undeclared"] = sum(n for (s, u), n in counter.items() if u)
    return out


def compute_corpus(
    corpus: StatsCorpus,
    *,
    tables: Sequence[str] = DEFAULT_TABLES,
    prov_spec: str = "agentprov-prov/0.1",
    select: Mapping[str, frozenset[str]] | None = None,
    groups: Sequence[FieldGroup] | None = None,
    on_row: Callable[[IndexRow], None] | None = None,
    per_execution: bool = False,
    exclusions: Sequence[Exclusion] | None = None,
) -> CorpusTables:
    """Compute ``tables`` over ``corpus`` in one streamed pass (see the module docstring)."""
    wanted = set(tables)
    unknown_tables = wanted - set(TABLES) - set(OPTIONAL_TABLES)
    if unknown_tables:
        raise ValueError("unknown stats table")
    if prov_spec not in PROV_SPECS:
        raise ValueError("unknown provenance spec")
    groups = tuple(groups) if groups is not None else field_groups()
    exclusions = tuple(exclusions) if exclusions is not None else declared_exclusions()
    by_execution: list[dict[str, Any]] = []
    need_groups = bool(wanted & {"unknowns", "field_groups"})
    need_artefacts = "artefacts" in wanted
    rules = _spec_rules(prov_spec) if "statements" in wanted else None
    catalogues: tuple[Any, ...] = ()
    if need_artefacts:
        from agentprov.artefacts import discover_catalogues

        catalogues = discover_catalogues()

    reader = corpus.reader
    acc: dict[tuple[str, str], _SourceAcc] = {}
    failures: Counter[str] = Counter()
    failure_list: list[dict[str, Any]] = []
    unknown_rules: Counter[str] = Counter()
    findings: dict[_ArtefactKey, list[Any]] = {}
    scanned: Counter[_ArtefactKey] = Counter()
    selected: set[str] = set()
    total_rows = 0

    def fail(ex: str, stage: str, exc: AgentProvError) -> None:
        failures[exc.code] += 1
        failure_list.append({"subject": {"ex": ex}, "stage": stage, "code": exc.code, "detail": _label(str(exc))})

    for row in reader.iter_index():
        total_rows += 1
        if select and not row_matches(row, select):
            continue
        selected.add(row.ex)
        key = (row.source_id, row.profile)
        a = acc.setdefault(key, _SourceAcc())
        a.rows += 1
        population = row.unit == "agent_execution" and row.execution_observed
        a.n_executions += population
        a.excluded_any += any(e.matches(row) for e in exclusions)
        in_groups = population and not excluded_from(row, "field_groups", exclusions)
        in_unknowns = population and not excluded_from(row, "unknowns", exclusions)
        a.excluded_field_groups += population and not in_groups
        a.excluded_unknowns += population and not in_unknowns
        a.status[row.status] += 1
        a.unit[row.unit] += 1
        a.observed[row.execution_observed] += 1
        a.completeness[row.completeness] += 1
        has_prov = prov_spec in (row.prov_paths or {})
        a.prov_output += has_prov

        document: AerDocument | None = None
        if (need_groups and (in_groups or in_unknowns)) or need_artefacts:
            try:
                document = reader.read_aer(row)
            except AgentProvError as exc:
                fail(row.ex, "aer", exc)
        if document is not None and need_groups and (in_groups or in_unknowns):
            try:
                status = evaluate(document.records, groups)
            except AgentProvError as exc:
                fail(row.ex, "field_groups", exc)
            else:
                if in_groups:
                    for gid, cell in status.cells.items():
                        a.cells.setdefault(gid, Counter())[cell] += 1
                if in_unknowns:
                    for oid, counter in status.occurrences.items():
                        a.occurrences.setdefault(oid, Counter()).update(counter)
        if document is not None and need_artefacts:
            from agentprov.artefacts import scan

            sem_records = None
            if row.sem_paths:
                try:
                    sem = reader.read_sem(row, sorted(row.sem_paths)[0])
                    sem_records = sem.records  # header first, annotations after (the seal is not needed)
                except AgentProvError as exc:
                    fail(row.ex, "sem", exc)
            akey = (row.source_id, row.profile, model_ids(document))
            scanned[akey] += 1
            try:
                findings.setdefault(akey, []).extend(scan([*document.records, document.seal], catalogues, sem_records=sem_records))
            except AgentProvError as exc:
                fail(row.ex, "artefacts", exc)
        if "statements" in wanted and has_prov:
            try:
                doc = reader.read_prov(row, prov_spec)
                classified, structural, unknown = prov_statements(doc, rules=rules)
            except AgentProvError as exc:
                fail(row.ex, "prov", exc)
            else:
                a.statements.update(classified)
                if per_execution:
                    by_execution.extend(
                        {"bundle": b, "evidence": e, "ex": row.ex, "method": m, "n": n, "profile": row.profile, "rule": r,
                         "source_id": row.source_id, "stype": t}
                        for (b, m, t, e, r), n in sorted(classified.items(), key=_statement_order)
                    )  # fmt: skip
                a.structural.update(structural)
                unknown_rules.update(unknown)
        if on_row is not None:
            on_row(row)

    out: dict[str, list[dict[str, Any]]] = {}
    keys = sorted(acc)
    if "counts" in wanted:
        out["counts"] = [_counts_row(k, acc[k], prov_spec) for k in keys]
        out["register"] = _register_rows(corpus, selected if select else None, fail_counter=failures)
    if "statements" in wanted:
        out["statements"] = [
            {"bundle": b, "evidence": e, "method": m, "n": n, "profile": k[1], "rule": r, "source_id": k[0], "stype": t}
            for k in keys for (b, m, t, e, r), n in sorted(acc[k].statements.items(), key=_statement_order)
        ]  # fmt: skip
        if per_execution:
            out["statements_by_execution"] = by_execution
        out["statements_structural"] = [
            {"bundle": b, "method": m, "n": n, "profile": k[1], "source_id": k[0], "stype": t}
            for k in keys for (b, m, t), n in sorted(acc[k].structural.items(), key=_structural_order)
        ]  # fmt: skip
    if "unknowns" in wanted:
        out["unknowns"] = [r for k in keys if acc[k].n_executions for r in _unknown_rows(k, acc[k], groups)]
    if "field_groups" in wanted:
        out["field_groups"] = [r for k in keys if acc[k].n_executions for r in _field_group_rows(k, acc[k], groups)]
    if need_artefacts:
        out["artefacts"] = _artefact_rows(findings, scanned)

    notices: list[str] = list(corpus.notices)
    if unknown_rules:
        notices.append(f"{sum(unknown_rules.values())} statement(s) cite a rule id outside the shipped {prov_spec} catalogue")
        failures["stats.prov.rule_unknown"] += sum(unknown_rules.values())
    if prov_spec == "adprov-v2.3-compat" and "statements" in wanted:
        notices.append("adprov-v2.3-compat graphs are a regression oracle (apv:RegressionOracle; R-55), not provenance")
    failure_list.sort(key=lambda f: (f["subject"]["ex"], f["stage"], f["code"]))
    return CorpusTables(
        identity=corpus.identity(),
        population={"rows": total_rows, "selected": len(selected),
                    "n_executions": sum(a.n_executions for a in acc.values())},  # fmt: skip
        tables=out,
        failures=dict(failures),
        failure_list=failure_list,
        notices=notices,
    )


_BUNDLE_ORDER: Final = {b: i for i, b in enumerate(BUNDLES)}
_EVIDENCE_ORDER: Final = {"O": 0, "D": 1, "I": 2}


def _statement_order(item: tuple[tuple[str, str, str, str, str], int]) -> tuple[Any, ...]:
    (b, m, t, e, r), _ = item
    return (_BUNDLE_ORDER[b], m, t, _EVIDENCE_ORDER[e], r)


def _structural_order(item: tuple[tuple[str, str, str], int]) -> tuple[Any, ...]:
    (b, m, t), _ = item
    return (_BUNDLE_ORDER[b], m, t)


def _counts_row(key: tuple[str, str], a: _SourceAcc, prov_spec: str) -> dict[str, Any]:
    parts, statuses = _registry_parts(*key)
    return {
        "completeness_known_incomplete": a.completeness["known_incomplete"],
        "completeness_unverifiable": a.completeness["unverifiable"],
        "completeness_verified_complete": a.completeness["verified_complete"],
        "execution_observed_false": a.observed[False],
        "execution_observed_true": a.observed[True],
        "n_executions": a.n_executions,
        "n_outcome_only": a.unit["outcome_only"],
        "profile": key[1],
        "prov_output": a.prov_output,
        "rate_excluded": a.excluded_any,
        "records": a.rows,
        "registry_import_status": statuses,
        "registry_parts": parts,
        "source_id": key[0],
        "status_failed": a.status["failed"],
        "status_ok": a.status["ok"],
        "status_ok_with_issues": a.status["ok_with_issues"],
        "unit_agent_execution": a.unit["agent_execution"],
        "unit_outcome_only": a.unit["outcome_only"],
        "unit_scenario": a.unit["scenario"],
    }


def _register_rows(corpus: StatsCorpus, selected: set[str] | None, *, fail_counter: Counter[str]) -> list[dict[str, Any]]:
    try:
        entries = corpus.reader.register()
    except CorpusReadError as exc:
        fail_counter[exc.code] += 1
        return []
    counter: Counter[tuple[str, str, str, str]] = Counter()
    for entry in entries:
        if selected is not None and entry.subject.get("ex") not in selected:
            continue
        counter[(entry.stage, entry.code, entry.severity, entry.disposition)] += 1
    return [{"code": c, "disposition": d, "n": n, "severity": sv, "stage": st} for (st, c, sv, d), n in sorted(counter.items())]


def _unknown_rows(key: tuple[str, str], a: _SourceAcc, groups: Iterable[FieldGroup]) -> list[dict[str, Any]]:
    rows = []
    for group in groups:
        for occ in group.occurrences:
            counter = a.occurrences.get(occ.id, Counter())
            columns = _status_columns(counter)
            n = sum(counter.values())
            row: dict[str, Any] = {"excluded": a.excluded_unknowns, "group": group.id, "n": n, "occurrence": occ.id,
                                   "pointer": occ.pointers[0],
                                   "profile": key[1], "record": occ.select.record, "source_id": key[0], **columns}  # fmt: skip
            for status in STATUSES:
                name = status.removeprefix("unk:")
                row[f"share_{name}"] = share(columns[name], n)
            rows.append(row)
    return rows


def _field_group_row(key: tuple[str, str], group: str, a: _SourceAcc, counter: Counter[tuple[str, bool]]) -> dict[str, Any]:
    columns = _status_columns(counter)
    cells = sum(counter.values())
    denominator = cells - columns["not_applicable"]
    return {
        "cells": cells,
        "coverage": share(columns["O"] + columns["D"], denominator),
        "denominator": denominator,
        "group": group,
        "excluded": a.excluded_field_groups,
        "n_executions": a.n_executions - a.excluded_field_groups,
        "observed_share": share(columns["O"], denominator),
        "profile": key[1],
        "source_id": key[0],
        **columns,
    }


def _field_group_rows(key: tuple[str, str], a: _SourceAcc, groups: Iterable[FieldGroup]) -> list[dict[str, Any]]:
    rows = []
    total: Counter[tuple[str, bool]] = Counter()
    for group in groups:
        counter = a.cells.get(group.id, Counter())
        total.update(counter)
        rows.append(_field_group_row(key, group.id, a, counter))
    rows.append(_field_group_row(key, "all", a, total))
    return rows


def _artefact_model_labels(models: Iterable[tuple[str, ...] | None]) -> dict[tuple[str, ...] | None, str | None]:
    """The display label of each model identity. Truncation or a ``,`` inside an id can give distinct identities one
    label; each of those gets `` #`` and a short sha256 of the JCS of its id list, so their rows stay apart (CB-33). A
    label that still collides (an id written to look like another's suffixed label) gets the full digest."""
    plain = {m: _models_label(m) for m in set(models)}
    labels = dict(plain)
    for width in (_MODEL_KEY_HEX, 64):
        shared = Counter(labels.values())
        for m, label in labels.items():
            if m is not None and shared[label] > 1:
                labels[m] = f"{plain[m]} #{hashlib.sha256(jcs_bytes(list(m))).hexdigest()[:width]}"
    return labels


def _artefact_rows(findings: Mapping[_ArtefactKey, list[Any]], scanned: Counter[_ArtefactKey]) -> list[dict[str, Any]]:
    from agentprov.artefacts import table

    labels = _artefact_model_labels(k[2] for k in scanned)
    rows = []
    for akey in sorted(scanned, key=lambda k: (k[0], k[1], labels[k[2]] or "", k[2] or ())):
        source_id, profile, models = akey
        model = labels[models]
        for t in table(findings.get(akey, []), n_executions=scanned[akey]):
            rows.append({
                "artefact_id": _label(t.artefact_id), "executions": t.executions, "first": list(t.first),
                "handling": t.handling, "hits": t.hits, "model": model, "n_executions": scanned[akey],
                "profile": profile, "proportion": None if t.proportion is None else round(t.proportion, _SHARE_DIGITS),
                "source_id": source_id,
            })  # fmt: skip
    return rows
