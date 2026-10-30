"""The source-neutral safety net over a sealed AER, and the per-class summary table (docs/architecture D.15.3-D.15.4).

:func:`scan` takes the records of **one** sealed AER (header first, seal last; ``agentprov.aer.reader.load_aer`` gives
them as ``doc.records + [doc.seal]``, ``iter_records`` streams them) and the loaded catalogues, and returns the
:class:`Finding` list. Each finding is one (detector, variant) in that execution. It is either **claimed** by one or more
catalogue entries or **unclassified** (``artefact.unclassified.<detector>``), never dropped. An entry claims a finding
when any of these holds, and only if its ``scope.profiles`` admits the execution's profile:

1. its ``detector.rule`` is the finding's generic detector;
2. its ``detector.rule`` is a mapper rule that the finding's evidence cites, directly or through its ``_unverified`` twin
   (the same reading at class I, D.5.4) (field-scoped rule references of the hit
   records, the rule of a corresponding seal issue, or the id of an accounting check);
3. one of its ``claims`` names the finding's detector (and variant, when given);
4. one of its ``recorded_as.issues`` is a seal-issue code that contributed to the finding.

The function is pure: it reads its arguments, writes nothing and returns a deterministic, sorted list. The net does not
handle artefacts; the adapters' bespoke handlers do that during conversion (D.15). It only catches what no handler
claimed, and makes the counts comparable across sources.

**Wiring (not done yet).** ``agentprov import --dry-run --artefacts`` needs the import pipeline (still a stub in this
build) and ``agentprov stats --artefacts`` needs ``stats`` (phase 11). Until then this module is the whole interface:
``scan`` per execution, :func:`scan_many` over several, and :func:`table` for the per-class summary of D.15.4. The CLI
will call these functions and add nothing to the semantics.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.artefacts.catalogue import (
    GENERIC_PREFIX,
    UNCLASSIFIED_PREFIX,
    ArtefactCatalogue,
    ArtefactEntry,
    claim_parts,
)
from agentprov.artefacts.detectors import MAX_LOCATORS, Hit, View, run_detectors
from agentprov.errors import AgentProvError

__all__ = ["FIRST_EXECUTIONS", "Finding", "ScanError", "TableRow", "scan", "scan_many", "table"]

#: How many example execution ids a table row lists (D.15.4: "the first execution ids, as locators only").
FIRST_EXECUTIONS: Final = 5


class ScanError(AgentProvError):
    """The records given to :func:`scan` are not one execution (no header)."""

    code = "artefacts.scan_input"
    exit_code = 1


@dataclass(frozen=True, slots=True)
class Finding:
    """One detector hit class in one execution.

    ``entries`` are the ids of the claiming catalogue entries (sorted) and ``handling`` their handling classes, parallel to
    it; an empty ``entries`` means the finding is unclassified. ``ids`` are locators (record, part or scope ids) in file
    order, at most :data:`MAX_LOCATORS`; ``n`` is the exact number of distinct locators.
    """

    ex: str
    detector: str
    variant: str
    entries: tuple[str, ...]
    handling: tuple[str, ...]
    ids: tuple[str, ...]
    n: int
    rules: tuple[str, ...] = ()
    issue_codes: tuple[str, ...] = ()

    @property
    def classified(self) -> bool:
        return bool(self.entries)

    @property
    def artefact_ids(self) -> tuple[str, ...]:
        """The claiming entries, or the single ``artefact.unclassified.<detector>`` id."""
        return self.entries or (UNCLASSIFIED_PREFIX + self.detector.removeprefix(GENERIC_PREFIX),)

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.ex, self.detector, self.variant)

    def to_json(self) -> dict[str, Any]:
        return {
            "classified": self.classified,
            "detector": self.detector,
            "entries": list(self.entries),
            "ex": self.ex,
            "handling": list(self.handling),
            "ids": list(self.ids),
            "issue_codes": list(self.issue_codes),
            "n": self.n,
            "rules": list(self.rules),
            "variant": self.variant,
        }


def _sem_annotations(sem_records: Iterable[Mapping[str, Any]], ex: object) -> list[Mapping[str, Any]]:
    """The ``ann`` records of one SEM file (header first, optional seal); a SEM of another execution is refused."""
    records = list(sem_records)
    if not records or records[0].get("k") != "sem":
        raise ScanError("scan needs the records of one SEM file, header first")
    if records[0].get("ex") != ex:
        raise ScanError("the SEM records belong to another execution than the AER records")
    return [r for r in records[1:] if isinstance(r, Mapping) and r.get("k") == "ann"]


def _view(records: Sequence[Mapping[str, Any]], sem_records: Iterable[Mapping[str, Any]] | None = None) -> View:
    if not records or records[0].get("k") != "execution":
        raise ScanError("scan needs the records of one execution, header first")
    seal = records[-1] if len(records) > 1 and records[-1].get("k") == "seal" else None
    body = [r for r in records[1 : len(records) - (1 if seal is not None else 0)] if isinstance(r, Mapping)]
    by_kind: dict[str, list[Mapping[str, Any]]] = {}
    for record in body:
        kind = record.get("k")
        if isinstance(kind, str):
            by_kind.setdefault(kind, []).append(record)
    sem = None if sem_records is None else _sem_annotations(sem_records, records[0].get("ex"))
    return View(header=records[0], body=body, seal=seal, by_kind=by_kind, sem=sem)


def _profile_id(header: Mapping[str, Any]) -> str | None:
    profile = header.get("profile")
    value = profile.get("id") if isinstance(profile, Mapping) else None
    return value if isinstance(value, str) else None


def _reading(rule: str) -> str:
    """The D rule whose reading ``rule`` cites: an ``_unverified`` twin (D.5.4) reads as its D rule."""
    name, _, version = rule.partition("@")
    return f"{name.removesuffix('_unverified')}@{version}"


def _claims(entry: ArtefactEntry, hit: Hit) -> bool:
    if entry.detector_is_generic:
        if entry.detector_rule == hit.detector:
            return True
    elif entry.detector_rule in hit.rules or entry.detector_rule in {_reading(r) for r in hit.rules}:
        return True
    for claim in entry.claims:
        name, variant = claim_parts(claim)
        if name == hit.detector and (variant is None or variant == hit.variant):
            return True
    return bool(hit.issue_codes.intersection(entry.issues))


def scan(
    aer_records: Iterable[Mapping[str, Any]],
    catalogues: Iterable[ArtefactCatalogue],
    *,
    sem_records: Iterable[Mapping[str, Any]] | None = None,
) -> list[Finding]:
    """The findings for one sealed execution, sorted by ``(ex, detector, variant)``.

    ``aer_records`` is the file in order, header first; a trailing ``seal`` record enables the accounting and issue
    detectors (without it they are skipped, not guessed). ``sem_records`` are the records of the execution's SEM file
    (``load_sem(...).records``, header first); they enable ``payload_not_reaching_agent`` and are skipped when absent.
    A SEM file whose ``ex`` differs from the AER header's raises :class:`ScanError`. The records are only read.
    """
    records = list(aer_records)
    view = _view(records, sem_records)
    ex = view.header.get("ex")
    ex_id = ex if isinstance(ex, str) else "unknown"
    profile = _profile_id(view.header)
    entries = [e for c in sorted(catalogues, key=lambda c: (c.family, c.version)) for e in c.entries if e.applies_to(profile)]
    findings: list[Finding] = []
    for hit in run_detectors(view):
        claimed = sorted({e.id: e.handling_class for e in entries if _claims(e, hit)}.items())
        findings.append(
            Finding(
                ex=ex_id,
                detector=hit.detector,
                variant=hit.variant,
                entries=tuple(i for i, _ in claimed),
                handling=tuple(h for _, h in claimed),
                ids=tuple(list(hit.ids)[:MAX_LOCATORS]),
                n=len(hit.ids),
                rules=tuple(sorted(hit.rules)),
                issue_codes=tuple(sorted(hit.issue_codes)),
            )
        )
    return sorted(findings, key=lambda f: f.sort_key)


def scan_many(executions: Iterable[Iterable[Mapping[str, Any]]], catalogues: Sequence[ArtefactCatalogue]) -> list[Finding]:
    """:func:`scan` over several executions (AER records only); the result is sorted, so it does not depend on the order."""
    out: list[Finding] = []
    for records in executions:
        out.extend(scan(records, catalogues))
    return sorted(out, key=lambda f: f.sort_key)


# --------------------------------------------------------------------------------------------------------------
# The per-class table (D.15.4)
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TableRow:
    """One row of the artefact table: an entry id (or ``artefact.unclassified.<detector>``) with its counts."""

    artefact_id: str
    handling: str | None  # None for unclassified rows
    executions: int  # executions with at least one finding for this artefact
    hits: int  # sum of the findings' distinct locators
    proportion: float | None  # executions / n_executions, when the denominator is known
    first: tuple[str, ...]  # the first execution ids (sorted), locators only

    def to_json(self) -> dict[str, Any]:
        return {
            "artefact_id": self.artefact_id,
            "executions": self.executions,
            "first": list(self.first),
            "handling": self.handling,
            "hits": self.hits,
            "proportion": self.proportion,
        }


def table(findings: Iterable[Finding], *, n_executions: int | None = None) -> list[TableRow]:
    """The per-artefact summary, sorted by artefact id (unclassified rows included, never filtered out).

    ``n_executions`` is the number of executions scanned (findings only name the executions that have one); with it each
    row carries its proportion. The function is pure and its output depends only on the multiset of findings.
    """
    if n_executions is not None and n_executions < 0:
        raise ValueError("n_executions must be non-negative")
    groups: dict[str, dict[str, Any]] = {}
    for finding in findings:
        for artefact_id, handling in _rows_of(finding):
            row = groups.setdefault(artefact_id, {"handling": handling, "ex": set(), "hits": 0})
            row["ex"].add(finding.ex)
            row["hits"] += finding.n
    rows: list[TableRow] = []
    for artefact_id in sorted(groups):
        row = groups[artefact_id]
        seen = sorted(row["ex"])
        proportion = None if not n_executions else len(seen) / n_executions
        rows.append(TableRow(artefact_id, row["handling"], len(seen), row["hits"], proportion, tuple(seen[:FIRST_EXECUTIONS])))
    return rows


def _rows_of(finding: Finding) -> list[tuple[str, str | None]]:
    if finding.entries:
        return list(zip(finding.entries, finding.handling, strict=True))
    return [(finding.artefact_ids[0], None)]
