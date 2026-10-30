"""The live-run cost and time estimate (design §8.3 as amended by D-650; in the core since D-701, where
``agentprov estimate`` computes it and the GUI shows it). Pure: no I/O, no network.

**Cells** come from ``run --dry-run --plan-json`` (D-651): every planned cell with its suite, attack and kind, and how
many of its repeats are already settled. The units still due are ``repeats - settled`` per cell.

**Per cell group** (suite × attack-or-benign × kind), :class:`CellStats` gives calls per cell, input / cached-input /
output tokens per call and the cell's duration, each at p50 and p90, with the source of the numbers:

1. ``corpus``: executions of the same suite, attack and model in the corpora named by ``--stats-corpus`` (the GUI
   passes the ones opened in the viewer; design §8.3);
2. ``priors``: the shipped priors table (``data/estimate_priors.json``, D-653; counts and quantiles only), by benchmark,
   suite, attack and, where known, model family;
3. ``default``: the user's defaults (``agentprov settings`` ``estimate.default.*``; the GUI's Settings › Estimate),
   labelled as assumptions.

**Cost** of one call = ``(in - cached - written)·p_in + cached·p_cached + written·p_write + out·p_out``, where
``in`` is every input token sent (each provider's usage convention is converted by :mod:`usage`, D-656) and
``p_cached`` / ``p_write`` fall back to ``p_in`` when the provider prices no cached input or cache writes, with the p50 figure built from the p50 quantiles and the p90 figure from the p90
quantiles (each quantile independently: a deliberately high p90). Plus the preflight probe (one call, D.10.9).
**Worst case** counts every due attempt (``attempts_due`` of the plan, up to ``--max-attempts`` per unit) at p90.

**Time** = ``ceil(units / jobs)`` × the unit-weighted mean cell duration, at p50 and p90.

**Inspect cells** (D-770): a unit is one cell of ``samples`` samples × ``epochs``, so it holds that many executions,
run ``parallel`` at a time (Inspect's ``max_connections``); the statistics are per execution (one sample). Each
execution makes agent calls (``calls``) and, when the plan has judges, judge calls (:class:`JudgeStats`: calls per
execution, tokens per call), priced at the judge model's price with no cache discount. A capped run's judges use the
agent's model (D-740), so then both prices are the same. Statistics that count judge calls among the agent's
(``judges_in_calls``: the shipped priors until they are rebuilt with the split) price them at the agent's price.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from agentprov.estimate.prices import Price, plain, stale

__all__ = [
    "BENIGN",
    "INSPECT_KIND",
    "NO_ATTACK",
    "CellStats",
    "Estimate",
    "Group",
    "JudgeStats",
    "PlanCell",
    "Quantiles",
    "default_stats",
    "duration_text",
    "estimate",
    "money",
]

BENIGN: Final = "(benign)"
#: D-770: an Inspect cell's kind; its attack row says "no attack" (AgentHarm's harmful split is not benign)
INSPECT_KIND: Final = "inspect"
NO_ATTACK: Final = "(no attack)"
_M: Final = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class Quantiles:
    p50: float
    p90: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.p50) and math.isfinite(self.p90)) or self.p50 < 0 or self.p90 < 0:
            raise ValueError("quantiles must be finite and not negative")

    @property
    def high(self) -> float:
        return max(self.p50, self.p90)


@dataclass(frozen=True, slots=True)
class JudgeStats:
    """Judge calls of one execution (an Inspect scorer's model calls, D-770)."""

    calls: Quantiles  # judge calls per execution
    tokens_in: Quantiles  # input tokens per judge call
    tokens_out: Quantiles  # output tokens per judge call


@dataclass(frozen=True, slots=True)
class CellStats:
    calls: Quantiles  # model calls per cell
    tokens_in: Quantiles  # input tokens sent per call (cached reads and cache writes included)
    tokens_cached: Quantiles  # cached input tokens per call (a part of tokens_in)
    tokens_out: Quantiles  # output tokens per call (reasoning included)
    seconds: Quantiles  # one cell's wall time
    source: str  # corpus | priors | default
    basis: str = ""  # e.g. "312 executions of banking × important_instructions"
    tokens_cache_write: Quantiles = Quantiles(0, 0)  # cache writes per call (a part of tokens_in; Anthropic)
    judges: JudgeStats | None = None  # measured judge calls (D-770); None: none measured
    judges_in_calls: bool = False  # the judge calls are counted in ``calls`` (statistics without the split)


def default_stats(values: Mapping[str, object] | None = None) -> CellStats:
    """The user's defaults (``estimate.default.*``, without the prefix). The shipped values are assumptions for a tool-using agent on an
    AgentDojo-sized task, never measurements; the priors table replaces them where it has data."""
    v = dict(values or {})

    def q(name: str, p50: float, p90: float) -> Quantiles:
        try:
            a, b = float(v.get(f"{name}_p50", p50)), float(v.get(f"{name}_p90", p90))  # type: ignore[arg-type]
            return Quantiles(a, max(a, b))
        except (TypeError, ValueError):
            return Quantiles(p50, p90)

    return CellStats(q("calls", 6, 12), q("tokens_in", 4000, 9000), q("tokens_cached", 0, 0), q("tokens_out", 200, 600),
                     q("seconds", 45, 150), "default", "your defaults (settings estimate.default.*): assumptions, not measured")


@dataclass(frozen=True, slots=True)
class PlanCell:
    suite: str
    attack: str | None
    kind: str
    settled: int
    executions: int = 1  # executions per unit: 1, or an Inspect cell's samples × epochs (D-770)
    parallel: int = 1  # of those, run at once (Inspect's max_connections)

    @classmethod
    def from_json(cls, row: Mapping[str, object]) -> PlanCell:
        settled = row.get("settled")
        return cls(str(row.get("suite") or ""), None if row.get("attack") is None else str(row.get("attack")),
                   str(row.get("kind") or ""), settled if isinstance(settled, int) and not isinstance(settled, bool)
                   else 0)


@dataclass(frozen=True, slots=True)
class Group:
    label: str
    units: int
    cost_p50: Decimal
    cost_p90: Decimal
    seconds_p50: float
    seconds_p90: float
    sources: tuple[str, ...]

    def to_json(self, *, priced: bool) -> dict[str, Any]:
        return {"label": self.label, "units": self.units,
                "cost_p50": plain(self.cost_p50) if priced else None,
                "cost_p90": plain(self.cost_p90) if priced else None,
                "seconds_p50": round(self.seconds_p50, 3), "seconds_p90": round(self.seconds_p90, 3),
                "sources": list(self.sources)}


@dataclass(frozen=True, slots=True)
class Estimate:
    units: int  # units (cell repeats) still due
    attempts_due: int
    calls_p50: float
    calls_p90: float
    cost_p50: Decimal | None  # None: no price for the model
    cost_p90: Decimal | None
    cost_worst: Decimal | None
    seconds_p50: float
    seconds_p90: float
    by_suite: tuple[Group, ...]
    by_attack: tuple[Group, ...]
    price: Price | None
    sources: Mapping[str, int]  # units per stats source
    warnings: tuple[str, ...] = field(default=())

    def to_json(self, today: dt.date | None = None) -> dict[str, Any]:
        """The ``agentprov-estimate/0.1`` body (money as plain decimal strings, never floats)."""

        def m(v: Decimal | None) -> str | None:
            return None if v is None else plain(v)

        priced = self.cost_p50 is not None  # a missing judge price leaves the agent priced but the cost unknown
        return {
            "units": self.units, "attempts_due": self.attempts_due,
            "calls_p50": round(self.calls_p50, 3), "calls_p90": round(self.calls_p90, 3),
            "cost_p50": m(self.cost_p50), "cost_p90": m(self.cost_p90), "cost_worst": m(self.cost_worst),
            "seconds_p50": round(self.seconds_p50, 3), "seconds_p90": round(self.seconds_p90, 3),
            "by_suite": [g.to_json(priced=priced) for g in self.by_suite],
            "by_attack": [g.to_json(priced=priced) for g in self.by_attack],
            "price": None if self.price is None else self.price.to_json(),
            "price_stale": bool(self.price is not None and stale(self.price, today)),
            "sources": dict(self.sources), "warnings": list(self.warnings), "headline": self.headline(),
        }  # fmt: skip

    def headline(self) -> str:
        if self.cost_p50 is None or self.cost_p90 is None:
            return f"{self.units} cell run(s); no price for this model: set one with 'agentprov prices set'"
        assert self.price is not None
        return (f"≈ {money(self.cost_p50)} (p90 {money(self.cost_p90)}) for {self.units} cell run(s), "
                f"prices as of {self.price.as_of.isoformat()} ({self.price.source})")


def money(value: Decimal) -> str:
    if value >= 100:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.4f}" if value > 0 else "$0"


def duration_text(seconds: float) -> str:
    seconds = max(0, round(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} m"
    return f"{m} m" if m else f"{seconds} s"


@dataclass(slots=True)
class _Acc:
    units: int = 0
    cost_p50: Decimal = Decimal(0)
    cost_p90: Decimal = Decimal(0)
    seconds_p50: float = 0.0
    seconds_p90: float = 0.0
    sources: set[str] = field(default_factory=set)

    def group(self, label: str) -> Group:
        return Group(label, self.units, self.cost_p50, self.cost_p90, self.seconds_p50, self.seconds_p90,
                     tuple(sorted(self.sources)))


def _call_cost(stats: CellStats, price: Price, quantile: str) -> Decimal:
    tin = Decimal(str(getattr(stats.tokens_in, quantile)))
    tcache = min(Decimal(str(getattr(stats.tokens_cached, quantile))), tin)
    twrite = min(Decimal(str(getattr(stats.tokens_cache_write, quantile))), tin - tcache)
    tout = Decimal(str(getattr(stats.tokens_out, quantile)))
    pcache = price.cached_input if price.cached_input is not None else price.input
    pwrite = price.cache_write if price.cache_write is not None else price.input
    return ((tin - tcache - twrite) * price.input + tcache * pcache + twrite * pwrite + tout * price.output) / _M


def _judge_call_cost(judges: JudgeStats, price: Price, quantile: str) -> Decimal:
    tin = Decimal(str(getattr(judges.tokens_in, quantile)))
    tout = Decimal(str(getattr(judges.tokens_out, quantile)))
    return (tin * price.input + tout * price.output) / _M


@dataclass(slots=True)
class _Due:
    units: int = 0
    executions: int = 0  # executions of those units
    time_factor: float = 0.0  # sum over units of executions / parallel: cell durations per execution duration
    max_executions: int = 1  # the largest unit, for the worst case


def estimate(cells: Sequence[PlanCell], *, repeats: int, attempts_due: int, jobs: int, price: Price | None,
             stats_for: Callable[[str, str | None, str], CellStats], preflight: bool = True,
             today: dt.date | None = None, judged: bool = False, judge_price: Price | None = None) -> Estimate:
    """The estimate of the units still due. ``stats_for(suite, attack, kind)`` gives each group's statistics.
    ``judged``: the plan has judges, priced at ``judge_price`` (D-770; ``None``: no price for the judge model)."""
    jobs = max(1, jobs)
    groups: dict[tuple[str, str | None, str], _Due] = {}
    for cell in cells:
        due = max(0, repeats - cell.settled)
        if due:
            acc_due = groups.setdefault((cell.suite, cell.attack, cell.kind), _Due())
            executions = max(1, cell.executions)
            acc_due.units += due
            acc_due.executions += due * executions
            acc_due.time_factor += due * executions / max(1, min(cell.parallel, executions))
            acc_due.max_executions = max(acc_due.max_executions, executions)
    if judged and judge_price is None:
        price_known = False
    else:
        price_known = price is not None
    warnings: list[str] = []
    judges_unmeasured = judges_as_agent = 0
    suites: dict[str, _Acc] = {}
    attacks: dict[str, _Acc] = {}
    sources: dict[str, int] = {}
    units = 0
    calls50 = calls90 = 0.0
    cost50 = cost90 = Decimal(0)
    secs50 = secs90 = 0.0
    p90_call_cost = Decimal(0)
    p90_calls_per_unit = 0.0
    for (suite, attack, kind), group in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2])):
        stats = stats_for(suite, attack, kind)
        n, ex = group.units, group.executions
        sources[stats.source] = sources.get(stats.source, 0) + n
        units += n
        judges = stats.judges if judged else None
        if judged and judges is None:
            if stats.judges_in_calls:
                judges_as_agent += n
            else:
                judges_unmeasured += n
        c50, c90 = stats.calls.p50 * ex, stats.calls.high * ex
        j50, j90 = (judges.calls.p50 * ex, judges.calls.high * ex) if judges is not None else (0.0, 0.0)
        calls50 += c50 + j50
        calls90 += c90 + j90
        g50 = g90 = Decimal(0)
        if price_known and price is not None:
            g50 = Decimal(str(c50)) * _call_cost(stats, price, "p50")
            g90 = Decimal(str(c90)) * _call_cost(stats, price, "p90")
            p90_call_cost = max(p90_call_cost, _call_cost(stats, price, "p90"))
            if judges is not None and judge_price is not None:
                g50 += Decimal(str(j50)) * _judge_call_cost(judges, judge_price, "p50")
                g90 += Decimal(str(j90)) * _judge_call_cost(judges, judge_price, "p90")
                p90_call_cost = max(p90_call_cost, _judge_call_cost(judges, judge_price, "p90"))
            cost50 += g50
            cost90 += g90
        per_execution = stats.calls.high + (judges.calls.high if judges is not None else 0.0)
        p90_calls_per_unit = max(p90_calls_per_unit, per_execution * group.max_executions)
        s50, s90 = stats.seconds.p50 * group.time_factor, stats.seconds.high * group.time_factor
        secs50 += s50
        secs90 += s90
        for table, label in ((suites, suite), (attacks, attack or (NO_ATTACK if kind == INSPECT_KIND else BENIGN))):
            acc = table.setdefault(label, _Acc())
            acc.units += n
            acc.cost_p50 += g50
            acc.cost_p90 += g90
            acc.seconds_p50 += s50
            acc.seconds_p90 += s90
            acc.sources.add(stats.source)
    probe50 = probe90 = Decimal(0)
    if preflight and price_known and price is not None and units:
        first = stats_for(*next(iter(sorted(groups, key=lambda k: (k[0], k[1] or "", k[2])))))
        probe50, probe90 = _call_cost(first, price, "p50"), _call_cost(first, price, "p90")
    rounds = math.ceil(units / jobs) if units else 0
    t50 = rounds * (secs50 / units) if units else 0.0
    t90 = rounds * (secs90 / units) if units else 0.0
    worst = None
    if price_known:
        worst = Decimal(str(max(attempts_due, units) * p90_calls_per_unit)) * p90_call_cost + probe90
    if price is None:
        warnings.append("No price for this model: the cost cannot be estimated ('agentprov prices set').")
    elif stale(price, today):
        warnings.append(f"The price is from {price.as_of.isoformat()}, more than 60 days ago: refresh it "
                        "('agentprov prices refresh') or set your own ('agentprov prices set').")
    if price is not None and not price_known:
        warnings.append("No price for the judge model: the cost cannot be estimated ('agentprov prices set').")
    if judges_as_agent and price is not None and judge_price is not None and \
            (judge_price.input, judge_price.output) != (price.input, price.output):
        warnings.append(f"{judges_as_agent} cell run(s) use statistics that count the judge calls among the agent's "
                        "(the shipped priors): those judge calls are priced at the agent's model.")
    if judges_unmeasured:
        warnings.append(f"{judges_unmeasured} cell run(s) have no judge-call statistics: their judge calls are not "
                        "in the estimate.")
    if price is not None and price.note:
        warnings.append(price.note)
    if sources.get("default"):
        warnings.append(f"{sources['default']} cell run(s) use your default assumptions (no corpus or prior "
                        "measurements for those suites and attacks).")

    def rows(table: Mapping[str, _Acc]) -> tuple[Group, ...]:
        return tuple(acc.group(label) for label, acc in sorted(table.items()))

    return Estimate(
        units=units, attempts_due=attempts_due, calls_p50=calls50 + (1 if preflight and units else 0),
        calls_p90=calls90 + (1 if preflight and units else 0),
        cost_p50=cost50 + probe50 if price_known else None, cost_p90=cost90 + probe90 if price_known else None,
        cost_worst=worst, seconds_p50=t50, seconds_p90=t90, by_suite=rows(suites), by_attack=rows(attacks),
        price=price, sources=dict(sorted(sources.items())), warnings=tuple(warnings),
    )
