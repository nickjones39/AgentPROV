"""The D8 check registry (MN M.1.2; K.10): check outcomes, findings and the tier report.

Kept minimal for tier 4: a check yields one :class:`CheckOutcome` with a status (``pass``, ``fail``, ``skipped`` or
``not_applicable``) and its findings. :class:`Tier4Report` aggregates outcomes and keeps the "MAY flag" diagnostics
(A5) apart, so they never decide a verdict. ``ok`` means no check failed; ``passed`` additionally requires that no check
was skipped, because a skipped check counts as a failure in release mode (D8; E.5.5; J.3.5 MP-3).

Findings carry identifiers, pointers and QNames only, never document or fixture text (G.8.1; R-42).

The D8 tiers that validate one document each, and their entry points (:data:`TIERS`): tier 2 is the AER validator
(:func:`agentprov.aer.validate.validate_file`), tier 3 the SEM validator (:func:`agentprov.sem.validate.validate_sem`,
C.14.4) and tier 4 :func:`agentprov.validate.prov.validate_prov`. Tiers 2 and 3 return the AER validator's
``ValidationReport`` (C.14.1); :func:`report_outcomes` folds such a report into this registry's outcomes, one per check
of the tier's check table (for tier 3, :data:`agentprov.sem.validate.SEM_CHECKS`), so every tier reports the same way.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from agentprov.aer.validate import ValidationReport

__all__ = ["MAX_FINDINGS", "TIERS", "CheckOutcome", "CheckStatus", "Finding", "Tier4Report", "outcome", "report_outcomes"]

CheckStatus = Literal["pass", "fail", "skipped", "not_applicable"]
#: D8 tier number -> (name, entry point) for the tiers that validate one document (module docstring).
TIERS: Final[Mapping[int, tuple[str, str]]] = {
    2: ("aer", "agentprov.aer.validate.validate_file"),
    3: ("sem", "agentprov.sem.validate.validate_sem"),
    4: ("prov", "agentprov.validate.prov.validate_prov"),
}
#: Findings kept per check; the count beyond it is reported as ``truncated`` (bounded reports on hostile input).
MAX_FINDINGS: Final = 200


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation: a code ``pv.<module>.<short_name>``, where it occurred (bundle / statement id / pointer) and a
    short detail built from ids and QNames only."""

    code: str
    where: str = ""
    detail: str = ""

    def as_json(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "where": self.where}


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """The outcome of one check. ``reason`` explains ``skipped`` and ``not_applicable`` outcomes."""

    id: str
    status: CheckStatus
    findings: tuple[Finding, ...] = ()
    reason: str = ""
    truncated: int = 0

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.id, "status": self.status, "findings": [f.as_json() for f in self.findings]}
        if self.reason:
            out["reason"] = self.reason
        if self.truncated:
            out["truncated"] = self.truncated
        return out


def outcome(check_id: str, findings: Iterable[Finding]) -> CheckOutcome:
    """``pass`` when ``findings`` is empty, else ``fail`` with the (bounded, de-duplicated, ordered) findings."""
    unique = sorted(set(findings), key=lambda f: (f.code, f.where, f.detail))
    if not unique:
        return CheckOutcome(check_id, "pass")
    kept = tuple(unique[:MAX_FINDINGS])
    return CheckOutcome(check_id, "fail", kept, truncated=len(unique) - len(kept))


@dataclass(slots=True)
class Tier4Report:
    """All tier-4 outcomes of one PROV document, plus the time diagnostics reported apart (A5)."""

    outcomes: list[CheckOutcome] = field(default_factory=list)
    diagnostics: list[Finding] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)

    def extend(self, outcomes: Iterable[CheckOutcome]) -> None:
        self.outcomes.extend(outcomes)

    @property
    def ok(self) -> bool:
        """No check failed (skipped checks allowed: dev mode)."""
        return not any(o.failed for o in self.outcomes)

    @property
    def passed(self) -> bool:
        """No check failed and none was skipped (release mode, D8)."""
        return self.ok and not any(o.status == "skipped" for o in self.outcomes)

    def failed(self) -> list[CheckOutcome]:
        return [o for o in self.outcomes if o.failed]

    def skipped(self) -> list[CheckOutcome]:
        return [o for o in self.outcomes if o.status == "skipped"]

    def get(self, check_id: str) -> CheckOutcome | None:
        for o in self.outcomes:
            if o.id == check_id:
                return o
        return None

    def codes(self) -> set[str]:
        """Every finding code of every failed check."""
        return {f.code for o in self.outcomes for f in o.findings}

    def findings(self, code_prefix: str = "") -> Iterator[Finding]:
        for o in self.outcomes:
            for f in o.findings:
                if f.code.startswith(code_prefix):
                    yield f

    def summary(self) -> dict[str, int]:
        counts = {"pass": 0, "fail": 0, "skipped": 0, "not_applicable": 0}
        for o in self.outcomes:
            counts[o.status] += 1
        return counts

    def as_json(self) -> dict[str, Any]:
        return {
            "diagnostics": [d.as_json() for d in self.diagnostics],
            "ok": self.ok,
            "outcomes": [o.as_json() for o in self.outcomes],
            "passed": self.passed,
            "summary": self.summary(),
            "versions": dict(sorted(self.versions.items())),
        }


def report_outcomes(report: ValidationReport, checks: Mapping[str, str]) -> list[CheckOutcome]:
    """One :class:`CheckOutcome` per check id of ``checks`` (in table order) from a tier-2/3 ``ValidationReport``.

    A check fails when an error finding carries its invariant label; otherwise it is ``skipped`` when a ``report.skipped``
    entry starts with ``"<check id>:"``, else it passes. Warnings never fail a check. A finding whose invariant is not in
    ``checks`` is kept under an extra ``unlisted`` check, so nothing is lost.
    """
    by_check: dict[str, list[Finding]] = {}
    for f in report.errors:
        key = f.invariant if f.invariant in checks else "unlisted"
        where = f"line {f.line}{f.pointer}" if f.line is not None else f.pointer
        by_check.setdefault(key, []).append(Finding(f.code, where, f.detail))
    out: list[CheckOutcome] = []
    for check_id in [*checks, *(["unlisted"] if "unlisted" in by_check else [])]:
        found = by_check.get(check_id, [])
        reasons = [s.partition(":")[2].strip() for s in report.skipped if s.startswith(f"{check_id}:")]
        if not found and reasons:
            out.append(CheckOutcome(check_id, "skipped", reason="; ".join(reasons)))
        else:
            out.append(outcome(check_id, found))
    return out


def by_id(outcomes: Sequence[CheckOutcome]) -> dict[str, CheckOutcome]:
    return {o.id: o for o in outcomes}
