"""Cell statistics for the estimate, in the order of design §8.3 as amended (D-653; in the core since D-701).

1. ``corpus``: :func:`usage.aggregate` over the ``--stats-corpus`` corpora (sampled AER files; counts only);
2. ``priors``: the shipped table ``data/estimate_priors.json`` (``tools/estimate/gen_estimate_priors.py``);
3. ``default``: the user's defaults (``estimate.default.*``).

Each level is looked up with the model family first, then any model. On the ``chars/4`` basis (no recorded usage),
each call's input gains the suite's tool-definition size from the backend catalogue (D-652), which the AER messages do
not hold.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

from agentprov.estimate.cost import CellStats, JudgeStats, Quantiles, default_stats
from agentprov.estimate.usage import CHARS_PER_TOKEN, JUDGE_FIELDS, Key, KeyStats, lookup, model_family

__all__ = ["PRIORS", "PRIORS_FORMAT", "StatsSource", "load_priors"]

PRIORS_FORMAT: Final = "agentprov-estimate-priors/0.1"
#: the benchmarks whose suites a live AgentDojo-family backend can run (the estimate's fallback order)
FAMILY_BENCHMARKS: Final = ("agentdojo", "agentdyn")
PRIORS: Final = Path(__file__).resolve().parent / "data" / "estimate_priors.json"
_LIMITS: Final = IngestLimits().replace(max_json_bytes=32 * 1024 * 1024, max_json_depth=16)
_FIELDS: Final = ("calls_p50", "calls_p90", "tokens_in_p50", "tokens_in_p90", "tokens_cached_p50", "tokens_cached_p90",
                  "tokens_out_p50", "tokens_out_p90")


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) \
        and value >= 0 else None


def load_priors(path: Path = PRIORS) -> tuple[dict[str, Any], dict[Key, KeyStats]]:
    """The shipped priors: the header (``built_from``) and the rows by key. Empty when the file is missing or unusable."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(32 * 1024 * 1024 + 1)
        doc = strict_json_loads(data.rstrip(b"\n"), _LIMITS)
    except (OSError, IngestError):
        return {}, {}
    if not isinstance(doc, dict) or doc.get("format") != PRIORS_FORMAT or not isinstance(doc.get("rows"), list):
        return {}, {}
    rows: dict[Key, KeyStats] = {}
    for r in doc["rows"]:
        if not isinstance(r, dict) or not isinstance(r.get("suite"), str):
            continue
        nums = {f: _num(r.get(f)) for f in _FIELDS}
        n = {f: v for f, v in nums.items() if v is not None}
        if len(n) != len(_FIELDS):
            continue
        key = (str(r.get("benchmark") or ""), r["suite"], str(r.get("attack") or ""), str(r.get("family") or ""),
               str(r.get("backend") or ""))
        # D-770: a row with the judge columns counts its judge calls apart; one without them (built before the split)
        # counts them in ``calls``
        judge = [_num(r.get(f)) for f in JUDGE_FIELDS]
        split = all(v is not None for v in judge)
        rows[key] = KeyStats(
            executions=int(_num(r.get("executions")) or 0), calls=int(_num(r.get("calls")) or 0), **n,
            seconds_p50=_num(r.get("seconds_p50")), seconds_p90=_num(r.get("seconds_p90")),
            basis=str(r.get("basis", ""))[:20], tokens_cache_write_p50=_num(r.get("tokens_cache_write_p50")) or 0.0,
            tokens_cache_write_p90=_num(r.get("tokens_cache_write_p90")) or 0.0,
            judge_calls_p50=judge[0] if split else None, judge_calls_p90=judge[1] if split else None,
            judge_tokens_in_p50=judge[2] if split else None, judge_tokens_in_p90=judge[3] if split else None,
            judge_tokens_out_p50=judge[4] if split else None, judge_tokens_out_p90=judge[5] if split else None,
            judges_in_calls=not split)
    built = doc.get("built_from") if isinstance(doc.get("built_from"), dict) else {}
    return {"built_from": built}, rows


def _cell_stats(k: KeyStats, source: str, what: str, tool_chars: int | None, fallback: CellStats) -> CellStats:
    extra = 0.0
    note = ""
    if k.basis in ("chars/4", "mixed") and tool_chars:
        extra = tool_chars / CHARS_PER_TOKEN
        note = f"; input + {round(extra)} tokens of tool definitions"
    seconds = (Quantiles(k.seconds_p50, max(k.seconds_p50, k.seconds_p90 or k.seconds_p50))
               if k.seconds_p50 is not None else fallback.seconds)
    judges = None
    if k.judge_calls_p50 is not None:
        def q(lo: float | None, hi: float | None) -> Quantiles:
            return Quantiles(lo or 0.0, max(lo or 0.0, hi or 0.0))

        judges = JudgeStats(q(k.judge_calls_p50, k.judge_calls_p90), q(k.judge_tokens_in_p50, k.judge_tokens_in_p90),
                            q(k.judge_tokens_out_p50, k.judge_tokens_out_p90))
    return CellStats(
        Quantiles(k.calls_p50, max(k.calls_p50, k.calls_p90)),
        Quantiles(k.tokens_in_p50 + extra, max(k.tokens_in_p50, k.tokens_in_p90) + extra),
        Quantiles(k.tokens_cached_p50, max(k.tokens_cached_p50, k.tokens_cached_p90)),
        Quantiles(k.tokens_out_p50, max(k.tokens_out_p50, k.tokens_out_p90)),
        seconds, source, f"{k.executions} executions, {what}, tokens by {k.basis}{note}",
        Quantiles(k.tokens_cache_write_p50, max(k.tokens_cache_write_p50, k.tokens_cache_write_p90)),
        judges, k.judges_in_calls)


class StatsSource:
    """``stats_for(suite, attack, kind)`` for :func:`estimate.estimate`: opened corpora, then priors, then defaults."""

    def __init__(self, *, benchmark: str, model: str | None, backend: str | None = None,
                 corpus: Mapping[Key, KeyStats] | None = None,
                 priors: Mapping[Key, KeyStats] | None = None, defaults: Mapping[str, object] | None = None,
                 tool_chars: Mapping[str, int | None] | None = None) -> None:
        self.benchmark, self.family, self.backend = benchmark, model_family(model), backend
        self.corpus, self.priors = dict(corpus or {}), dict(priors or {})
        self.defaults = default_stats(defaults)
        self.tool_chars = dict(tool_chars or {})

    def __call__(self, suite: str, attack: str | None, kind: str) -> CellStats:
        # the backend's benchmark first, then the other AgentDojo-family benchmark that names the suite (AutoDojo
        # runs AgentDyn's shopping, github and dailylife; the stored corpora file them under "agentdyn")
        benchmarks = list(dict.fromkeys((self.benchmark, *FAMILY_BENCHMARKS)))
        for source, table in (("corpus", self.corpus), ("priors", self.priors)):
            for benchmark in benchmarks:
                hit = lookup(table, benchmark, suite, attack, self.family, self.backend)
                if hit is not None:
                    return _cell_stats(hit[0], source, hit[1], self.tool_chars.get(suite), self.defaults)
        return self.defaults
