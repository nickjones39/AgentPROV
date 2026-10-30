"""The strict reader of ``run --dry-run --plan-json`` (``agentprov-run-dry-plan/0.1``, D-651) for the estimate.

The plan is the CLI's own output, but its names come from the backend worker: they are labels, never paths, and the
document is read bounded and strictly (``agentprov.ingest``) with its totals checked against its cells.

An Inspect plan (D-770) has no suite or kind per cell: each row names its ``task`` and how many ``samples`` it runs,
and the document's ``inspect`` table gives the epochs, the message limit, the sample concurrency and each judge
role's model. Such a cell becomes a :class:`PlanCell` of suite ``task``, kind ``inspect`` and ``samples × epochs``
executions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.estimate.cost import INSPECT_KIND, PlanCell
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["INSPECT_KIND", "PLAN_FORMAT", "DryPlan", "InspectInfo", "PlanError", "parse_plan"]

PLAN_FORMAT: Final = "agentprov-run-dry-plan/0.1"
_LIMITS: Final = IngestLimits().replace(max_json_bytes=64 * 1024 * 1024, max_json_depth=16)


class PlanError(AgentProvError):
    """A plan document that cannot be used (the message names the problem, never data)."""

    code = "estimate.plan"
    exit_code = 70  # the CLI's own output: a malformed one is an internal error


def _int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlanError(f"{what} is not a count")
    return value


@dataclass(frozen=True, slots=True)
class InspectInfo:
    """The ``inspect`` table of an Inspect plan (D-770)."""

    task: str
    epochs: int
    message_limit: int | None
    max_connections: int
    judges: tuple[tuple[str, str], ...]  # (role, model), sorted by role

    def to_json(self) -> dict[str, Any]:
        return {"task": self.task, "epochs": self.epochs, "message_limit": self.message_limit,
                "max_connections": self.max_connections, "judges": dict(self.judges)}


def _inspect_info(doc: Any) -> InspectInfo | None:
    if doc is None:
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("task"), str) or not isinstance(doc.get("judges"), dict):
        raise PlanError("a malformed inspect table")
    limit = doc.get("message_limit")
    judges = doc["judges"]
    if not all(isinstance(r, str) and isinstance(m, str) for r, m in judges.items()):
        raise PlanError("a malformed judge")
    return InspectInfo(doc["task"][:200], max(1, _int(doc.get("epochs"), "epochs")),
                       None if limit is None else _int(limit, "message_limit"),
                       max(1, _int(doc.get("max_connections"), "max_connections")),
                       tuple(sorted((r[:64], m[:200]) for r, m in judges.items())))


@dataclass(frozen=True, slots=True)
class DryPlan:
    plan_sha256: str
    backend: str
    repeats: int
    max_attempts: int
    units: int
    settled: int
    attempts_due: int
    benchmark_version: str
    cells: tuple[PlanCell, ...]
    inspect: InspectInfo | None = None

    def to_json(self) -> dict[str, Any]:
        out = {"plan_sha256": self.plan_sha256, "backend": self.backend, "cells": len(self.cells),
               "repeats": self.repeats, "max_attempts": self.max_attempts, "units": self.units,
               "settled": self.settled, "attempts_due": self.attempts_due,
               "benchmark_version": self.benchmark_version}
        if self.inspect is not None:
            out["inspect"] = {**self.inspect.to_json(), "samples": sum(c.executions for c in self.cells)
                              // self.inspect.epochs}
        return out


def parse_plan(data: bytes) -> DryPlan:
    try:
        doc = strict_json_loads(data.strip(), _LIMITS)
    except IngestError as exc:
        raise PlanError(f"the plan is not strict JSON ({exc.code})") from None
    if not isinstance(doc, dict) or doc.get("format") != PLAN_FORMAT:
        raise PlanError("not a run dry plan")
    rows = doc.get("cells")
    if not isinstance(rows, list):
        raise PlanError("no cells")
    inspect = _inspect_info(doc.get("inspect"))
    cells = []
    for row in rows:
        if inspect is not None:
            if not isinstance(row, dict) or not isinstance(row.get("task"), str):
                raise PlanError("a malformed cell")
            executions = max(1, _int(row.get("samples"), "samples")) * inspect.epochs
            base = PlanCell.from_json({**row, "suite": row["task"], "kind": INSPECT_KIND})
            cells.append(PlanCell(base.suite, None, INSPECT_KIND, base.settled, executions,
                                  min(inspect.max_connections, executions)))
            continue
        if not isinstance(row, dict) or not isinstance(row.get("suite"), str) or not isinstance(row.get("kind"), str):
            raise PlanError("a malformed cell")
        cells.append(PlanCell.from_json(row))
    plan = DryPlan(str(doc.get("plan_sha256", ""))[:64], str(doc.get("backend") or "")[:40],
                   max(1, _int(doc.get("repeats"), "repeats")), _int(doc.get("max_attempts"), "max_attempts"),
                   _int(doc.get("units"), "units"), _int(doc.get("settled"), "settled"),
                   _int(doc.get("attempts_due"), "attempts_due"), str(doc.get("benchmark_version") or "")[:80],
                   tuple(cells), inspect)
    if plan.units != len(cells) * plan.repeats or plan.settled != sum(min(c.settled, plan.repeats) for c in cells):
        raise PlanError("the totals do not match the cells")
    return plan
