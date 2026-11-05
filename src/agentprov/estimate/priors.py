"""Cell statistics for the estimate, in the order of design §8.3 as amended (D-653; in the core since D-701).

1. ``corpus``: :func:`usage.aggregate` over the ``--stats-corpus`` corpora (sampled AER files; counts only);
2. ``priors-local`` and ``priors`` (D-1062): the local priors ``$AGENTPROV_HOME/estimate/priors-local.json``, built from
   the user's sealed corpora by ``agentprov priors build`` (:mod:`.localpriors`), and the shipped table
   ``data/estimate_priors.json`` (``tools/estimate/gen_estimate_priors.py``). Per benchmark (the backend's first), the
   model family's rows come before the any-model rows, and within each the local row before the shipped one: local
   family, shipped family, local any-model, shipped any-model. Without a local file this is the shipped table's order
   as before;
3. ``default``: the user's defaults (``estimate.default.*``).

Each level is looked up with the model family first, then any model. On the ``chars/4`` basis (no recorded usage),
each call's input gains the suite's tool-definition size from the backend catalogue (D-652), which the AER messages do
not hold.

:meth:`StatsSource.basis` says what the cells of one estimate were drawn from (the ``quote.basis`` object of
``agentprov estimate --format json``, D-1062).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

from agentprov.estimate.cost import CellStats, JudgeStats, Quantiles, default_stats
from agentprov.estimate.usage import CHARS_PER_TOKEN, JUDGE_FIELDS, Key, KeyStats, lookup_key, model_family

__all__ = ["LOCAL", "PRIORS", "PRIORS_FORMAT", "SHIPPED", "StatsSource", "load_priors"]

PRIORS_FORMAT: Final = "agentprov-estimate-priors/0.1"
#: the benchmarks whose suites a live AgentDojo-family backend can run (the estimate's fallback order)
FAMILY_BENCHMARKS: Final = ("agentdojo", "agentdyn")
PRIORS: Final = Path(__file__).resolve().parent / "data" / "estimate_priors.json"
#: the ``source`` of a cell drawn from the local priors (D-1062) and from the shipped ones
LOCAL: Final = "priors-local"
SHIPPED: Final = "priors"
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


@dataclass(frozen=True, slots=True)
class _Hit:
    """What one cell group was drawn from."""

    source: str  # corpus | priors-local | priors | default
    key: Key | None  # the row's key (None: the defaults)
    executions: int
    basis: str  # the row's token basis (usage | chars/4 | mixed | none); "" for the defaults
    family_specific: bool
    cached: bool  # the statistics count cached input tokens (priced at the cache rate)


class StatsSource:
    """``stats_for(suite, attack, kind)`` for :func:`estimate.estimate`: opened corpora, then priors (local, then
    shipped), then defaults. Every call is remembered for :meth:`basis`."""

    def __init__(self, *, benchmark: str, model: str | None, backend: str | None = None,
                 corpus: Mapping[Key, KeyStats] | None = None,
                 priors: Mapping[Key, KeyStats] | None = None, defaults: Mapping[str, object] | None = None,
                 tool_chars: Mapping[str, int | None] | None = None, local: Mapping[Key, KeyStats] | None = None,
                 local_corpora: tuple[str, ...] = ()) -> None:
        self.benchmark, self.family, self.backend = benchmark, model_family(model), backend
        self.corpus, self.priors, self.local = dict(corpus or {}), dict(priors or {}), dict(local or {})
        self.local_corpora = local_corpora
        self.defaults = default_stats(defaults)
        self.tool_chars = dict(tool_chars or {})
        self.used: dict[tuple[str, str | None, str], _Hit] = {}

    def __call__(self, suite: str, attack: str | None, kind: str) -> CellStats:
        # the backend's benchmark first, then the other AgentDojo-family benchmark that names the suite (AutoDojo
        # runs AgentDyn's shopping, github and dailylife; the stored corpora file them under "agentdyn")
        benchmarks = list(dict.fromkeys((self.benchmark, *FAMILY_BENCHMARKS)))
        hit: tuple[Key, KeyStats, str, str] | None = None
        for benchmark in benchmarks:
            found = lookup_key(self.corpus, benchmark, suite, attack, self.family, self.backend)
            if found is not None:
                hit = (*found, "corpus")
                break
        else:
            hit = self._priors(benchmarks, suite, attack)
        if hit is None:
            stats = self.defaults
            self.used[(suite, attack, kind)] = _Hit("default", None, 0, "", False, stats.tokens_cached.high > 0)
            return stats
        key, k, what, source = hit
        stats = _cell_stats(k, source, what, self.tool_chars.get(suite), self.defaults)
        self.used[(suite, attack, kind)] = _Hit(source, key, k.executions, k.basis, bool(key[3]),
                                                stats.tokens_cached.high > 0)
        return stats

    def _priors(self, benchmarks: list[str], suite: str, attack: str | None
                ) -> tuple[Key, KeyStats, str, str] | None:
        tables = ((LOCAL, self.local), (SHIPPED, self.priors)) if self.local else ((SHIPPED, self.priors),)
        for benchmark in benchmarks:
            for family_specific in (True, False):
                for source, table in tables:
                    found = lookup_key(table, benchmark, suite, attack, self.family, self.backend,
                                       family_specific=family_specific)
                    if found is not None:
                        return (*found, source)
        return None

    def basis(self) -> dict[str, Any]:
        """What the cells asked for so far were drawn from (D-1062): ``priors`` ``local``, ``shipped`` or ``mixed``
        (``None``: no cell used priors), whether every measured cell used this model family's rows, the family when
        any did, the recorded executions behind the distinct rows used, the local priors' corpus ids (when they were
        used), the token basis (``chars/4``, ``usage`` or ``mixed``; ``None`` when nothing was measured), whether any
        cell's statistics hold cached input tokens, and the cell groups per source."""
        hits = list(self.used.values())
        used = {h.source for h in hits}
        kinds = {LOCAL: "local", SHIPPED: "shipped"}
        priors = sorted(kinds[s] for s in used if s in kinds)
        measured = [h for h in hits if h.source != "default"]
        rows = {(h.source, h.key): h.executions for h in measured}
        bases = {h.basis for h in measured}
        token_basis = None if not bases else bases.pop() if len(bases) == 1 else "mixed"
        return {
            "priors": None if not priors else priors[0] if len(priors) == 1 else "mixed",
            "family_specific": bool(measured) and all(h.family_specific for h in measured),
            "family": self.family if any(h.family_specific for h in measured) else None,
            "executions": sum(rows.values()),
            "corpora": list(self.local_corpora) if LOCAL in used else [],
            "token_basis": token_basis,
            "cached_input": any(h.cached for h in hits),
            "groups_by_source": {s: sum(1 for h in hits if h.source == s) for s in sorted(used)},
        }
