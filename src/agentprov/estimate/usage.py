"""Measured cell statistics for the estimate (design §8.3; D-653; in the core since D-701). **Counts only: no corpus text is kept.**

From one AER document, :func:`execution_usage` takes the benchmark, suite and attack (``execution.task``), the agent's
requested model, the number of model calls, each call's input / cached / output tokens and the run's duration:

* tokens are the call's recorded ``usage`` where the source records it (``basis = "usage"``). AER keeps each
  provider's own convention (D-656): for an agent whose ``model.provider`` is ``anthropic``, ``input_tokens`` excludes
  the cache reads and writes, so the input sent is ``input + cache_read + cache_write``; for an OpenAI-compatible one,
  ``input_tokens`` already includes the cached part. Here every call is counted as *input sent*, with its cached reads
  and cache writes as parts of it, so the estimate prices both conventions with one formula;
* otherwise they are **estimated** from the recorded message sizes, four characters per token, over the call's input
  messages and the messages it generated (``basis = "chars/4"``). Tool definitions are not in the AER messages, so this
  estimate is low for tool-heavy prompts. A string counts its characters, a blob reference its byte count; nothing of
  the text itself leaves this function.

**Judge calls** (D-770): a model call whose actor is a ``judge`` (an Inspect scorer's model) is counted apart, as
:attr:`ExecutionUsage.judge_tokens_in` / ``judge_tokens_out``; ``calls`` and the agent's token lists hold the agent's
calls only. AgentDojo-family executions have no judge actors, so nothing changes for them.

:func:`aggregate` turns many executions into quantiles per key ``(benchmark, suite, attack-or-benign, model family,
backend)``. The backend is the live backend of a captured execution (its profile ``<backend>-live``; user decision
2026-10-22: the same suite run on two backends is compared, so their numbers are kept apart); imports have none.
The same code serves ``agentprov estimate --stats-corpus`` and ``tools/estimate/gen_estimate_priors.py`` (the shipped
priors).
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.aer.reader import iter_records

__all__ = [
    "CHARS_PER_TOKEN",
    "ExecutionUsage",
    "JUDGE_FIELDS",
    "KeyStats",
    "aggregate",
    "execution_usage",
    "model_family",
    "quantile",
    "sample_corpus",
]

CHARS_PER_TOKEN: Final = 4
#: design §8.3: a sample of up to this many AER files per corpus
SAMPLE_FILES: Final = 200
_DATE_SUFFIX: Final = re.compile(r"[-@](20\d{2}-?\d{2}-?\d{2}|\d{4})$")
_FAMILY_OK: Final = re.compile(r"[a-z0-9][a-z0-9._+-]{0,79}")


def model_family(requested: str | None) -> str | None:
    """A model id without its vendor prefix and date suffix, lower case (``openai/gpt-4o-2024-05-13`` → ``gpt-4o``);
    ``None`` when the id is missing or is not a plain label."""
    if not requested:
        return None
    name = requested.strip().lower().rsplit("/", 1)[-1]
    name = _DATE_SUFFIX.sub("", name)
    return name if _FAMILY_OK.fullmatch(name) else None


def _size(value: Any, depth: int = 0) -> int:
    """Characters of every string in a JSON value, or a blob reference's byte count (no text is returned)."""
    if depth > 32:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        if "$blob" in value and isinstance(value.get("bytes"), int):
            return max(0, int(value["bytes"]))
        return sum(_size(v, depth + 1) for k, v in value.items() if k not in ("t", "provider_call_id", "responds_to"))
    if isinstance(value, list):
        return sum(_size(v, depth + 1) for v in value)
    return 0


@dataclass(frozen=True, slots=True)
class ExecutionUsage:
    benchmark: str | None
    suite: str | None
    attack: str | None
    model: str | None
    calls: int
    tokens_in: tuple[int, ...]  # per call: input sent (cached reads and cache writes included)
    tokens_cached: tuple[int, ...]  # cache reads (a part of tokens_in)
    tokens_out: tuple[int, ...]
    seconds: float | None
    basis: str  # usage | chars/4 | mixed | none
    tokens_cache_write: tuple[int, ...] = ()  # cache writes (a part of tokens_in)
    provider: str | None = None
    backend: str | None = None  # the live backend (from the execution's profile id <backend>-live), None for imports
    judge_tokens_in: tuple[int, ...] = ()  # per judge call (D-770): input sent
    judge_tokens_out: tuple[int, ...] = ()


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def execution_usage(path: Path | str) -> ExecutionUsage | None:
    """The counts of one AER file (read with the core reader, which checks the seal); ``None`` when unreadable."""
    try:
        records = list(iter_records(path))
    except Exception:  # an unreadable or tampered document is skipped, never repaired
        return None
    if not records or "ex" not in records[0]:
        return None
    profile = records[0].get("profile")
    profile_id = profile.get("id") if isinstance(profile, dict) else None
    backend = profile_id[: -len("-live")] if isinstance(profile_id, str) and profile_id.endswith("-live") else None
    raw_task = records[0].get("task")
    task: dict[str, Any] = raw_task if isinstance(raw_task, dict) else {}
    message_size: dict[str, int] = {}
    generated: dict[str, int] = {}
    model = None
    provider = None
    seconds = None
    calls: list[dict[str, Any]] = []
    judges: set[str] = set()  # ids of the judge actors
    for r in records:
        k = r.get("k")
        if k == "actor" and r.get("kind") == "judge" and isinstance(r.get("id"), str):
            judges.add(r["id"])
        if k == "message":
            size = _size(r.get("parts"))
            if isinstance(r.get("id"), str):
                message_size[r["id"]] = size
            if isinstance(r.get("generated_by"), str):
                generated[r["generated_by"]] = generated.get(r["generated_by"], 0) + size
        elif k == "model_call":
            calls.append(r)
        elif k == "actor" and r.get("kind") == "llm_agent" and model is None:
            m = r.get("model")
            model = m.get("requested") if isinstance(m, dict) and isinstance(m.get("requested"), str) else None
            provider = m.get("provider") if isinstance(m, dict) and isinstance(m.get("provider"), str) else None
        elif k == "scope" and r.get("kind") == "run" and seconds is None:
            t = r.get("t")
            d = t.get("dur_s") if isinstance(t, dict) else None
            seconds = float(d) if isinstance(d, int | float) and not isinstance(d, bool) and math.isfinite(d) \
                and d >= 0 else None
    tin: list[int] = []
    tcache: list[int] = []
    twrite: list[int] = []
    tout: list[int] = []
    jin: list[int] = []
    jout: list[int] = []
    bases: set[str] = set()
    for call in calls:
        if call.get("actor") in judges:  # a judge's call: input sent and output only (priced with no cache discount)
            jin_n, jout_n, basis = _judge_tokens(call, message_size, generated)
            jin.append(jin_n)
            jout.append(jout_n)
            bases.add(basis)
            continue
        raw_usage = call.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        recorded_in, recorded_out = _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))
        if recorded_in is not None and recorded_out is not None:
            read, write = _int(usage.get("cache_read_tokens")) or 0, _int(usage.get("cache_write_tokens")) or 0
            if provider == "anthropic":  # uncached input; reads and writes reported beside it (D-656)
                tin.append(recorded_in + read + write)
            else:  # OpenAI-compatible: prompt tokens include the cached part
                tin.append(recorded_in)
                read, write = min(read, recorded_in), min(write, max(0, recorded_in - read))
            tcache.append(read)
            twrite.append(write)
            tout.append(recorded_out)
            bases.add("usage")
            continue
        raw_inputs = call.get("input")
        inputs: list[Any] = raw_inputs if isinstance(raw_inputs, list) else []
        chars_in = sum(int(message_size.get(i, 0)) if isinstance(i, str) else _size(i) for i in inputs)
        chars_out = generated.get(str(call.get("id")), 0)
        tin.append(math.ceil(chars_in / CHARS_PER_TOKEN))
        tout.append(math.ceil(chars_out / CHARS_PER_TOKEN))
        tcache.append(0)
        twrite.append(0)
        bases.add("chars/4")
    basis = "none" if not bases else bases.pop() if len(bases) == 1 else "mixed"

    def label(value: Any) -> str | None:
        return value if isinstance(value, str) and 0 < len(value) <= 200 else None

    return ExecutionUsage(label(task.get("benchmark")), label(task.get("suite")), label(task.get("attack_id")),
                          model, len(tin), tuple(tin), tuple(tcache), tuple(tout), seconds, basis, tuple(twrite),
                          label(provider), label(backend), tuple(jin), tuple(jout))


def _judge_tokens(call: Mapping[str, Any], message_size: Mapping[str, int], generated: Mapping[str, int]
                  ) -> tuple[int, int, str]:
    """A judge call's input sent and output tokens, and their basis: the recorded usage (an OpenAI-compatible count,
    which includes any cached part: Inspect's judges go through its OpenAI-compatible provider, D-741), else
    ``chars/4`` of its messages."""
    raw_usage = call.get("usage")
    usage: Mapping[str, Any] = raw_usage if isinstance(raw_usage, Mapping) else {}
    recorded_in, recorded_out = _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))
    if recorded_in is not None and recorded_out is not None:
        return recorded_in, recorded_out, "usage"
    raw_inputs = call.get("input")
    inputs: list[Any] = raw_inputs if isinstance(raw_inputs, list) else []
    chars_in = sum(int(message_size.get(i, 0)) if isinstance(i, str) else _size(i) for i in inputs)
    chars_out = generated.get(str(call.get("id")), 0)
    return math.ceil(chars_in / CHARS_PER_TOKEN), math.ceil(chars_out / CHARS_PER_TOKEN), "chars/4"


def quantile(values: Sequence[float], q: float) -> float:
    """The ``q`` quantile (inclusive method; the value itself for one sample)."""
    if not values:
        raise ValueError("no values")
    if len(values) == 1:
        return float(values[0])
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return float(cuts[max(0, min(98, round(q * 100) - 1))])


@dataclass(frozen=True, slots=True)
class KeyStats:
    """Quantiles of one key (counts only)."""

    executions: int
    calls: int
    calls_p50: float
    calls_p90: float
    tokens_in_p50: float
    tokens_in_p90: float
    tokens_cached_p50: float
    tokens_cached_p90: float
    tokens_out_p50: float
    tokens_out_p90: float
    seconds_p50: float | None
    seconds_p90: float | None
    basis: str
    tokens_cache_write_p50: float = 0.0
    tokens_cache_write_p90: float = 0.0
    #: D-770: judge calls per execution and tokens per judge call; None when no execution of the key had a judge call
    judge_calls_p50: float | None = None
    judge_calls_p90: float | None = None
    judge_tokens_in_p50: float | None = None
    judge_tokens_in_p90: float | None = None
    judge_tokens_out_p50: float | None = None
    judge_tokens_out_p90: float | None = None
    judges_in_calls: bool = False  # ``calls`` counts the judge calls too (a priors row without the judge split)

    def to_json(self) -> dict[str, Any]:
        def r(x: float | None) -> float | None:
            return None if x is None else round(x, 2)

        return {"executions": self.executions, "calls": self.calls, "calls_p50": r(self.calls_p50),
                "calls_p90": r(self.calls_p90), "tokens_in_p50": r(self.tokens_in_p50),
                "tokens_in_p90": r(self.tokens_in_p90), "tokens_cached_p50": r(self.tokens_cached_p50),
                "tokens_cached_p90": r(self.tokens_cached_p90), "tokens_out_p50": r(self.tokens_out_p50),
                "tokens_out_p90": r(self.tokens_out_p90), "seconds_p50": r(self.seconds_p50),
                "seconds_p90": r(self.seconds_p90), "basis": self.basis,
                "tokens_cache_write_p50": r(self.tokens_cache_write_p50),
                "tokens_cache_write_p90": r(self.tokens_cache_write_p90),
                **({f: r(getattr(self, f)) for f in JUDGE_FIELDS} if self.judge_calls_p50 is not None else {})}


#: D-770: the judge columns of a key (present only for keys with judge calls)
JUDGE_FIELDS: Final = ("judge_calls_p50", "judge_calls_p90", "judge_tokens_in_p50", "judge_tokens_in_p90",
                       "judge_tokens_out_p50", "judge_tokens_out_p90")


Key = tuple[str, str, str, str, str]  # benchmark, suite, attack or "", model family or "", backend or ""


def aggregate(usages: Iterable[ExecutionUsage], *, with_model: bool = True, with_backend: bool = True,
              min_executions: int = 1) -> dict[Key, KeyStats]:
    """Quantiles per ``(benchmark, suite, attack or "", model family or "", backend or "")``. Executions with no
    model call are left out (they say nothing about cost). Keys with fewer than ``min_executions`` executions are
    dropped."""
    groups: dict[Key, list[ExecutionUsage]] = {}
    for u in usages:
        if (u.calls == 0 and not u.judge_tokens_in) or not u.suite:
            continue
        family = (model_family(u.model) or "") if with_model else ""
        key = (u.benchmark or "", u.suite, u.attack or "", family, (u.backend or "") if with_backend else "")
        groups.setdefault(key, []).append(u)
    out: dict[Key, KeyStats] = {}
    for key, items in groups.items():
        if len(items) < min_executions:
            continue
        calls = [float(u.calls) for u in items]
        tin = [float(t) for u in items for t in u.tokens_in]
        tcache = [float(t) for u in items for t in u.tokens_cached]
        twrite = [float(t) for u in items for t in u.tokens_cache_write] or [0.0]
        tout = [float(t) for u in items for t in u.tokens_out]
        secs = [u.seconds for u in items if u.seconds is not None]
        bases = {u.basis for u in items}
        judged: list[float | None] = [None] * len(JUDGE_FIELDS)
        if any(u.judge_tokens_in for u in items):
            jcalls = [float(len(u.judge_tokens_in)) for u in items]
            jin = [float(t) for u in items for t in u.judge_tokens_in]
            jout = [float(t) for u in items for t in u.judge_tokens_out]
            judged = [quantile(values, q) for values in (jcalls, jin, jout) for q in (0.5, 0.9)]
        if not tin:  # judge calls only: no agent call to take token quantiles from
            tin = tcache = tout = [0.0]
        out[key] = KeyStats(
            len(items), int(sum(calls)), quantile(calls, 0.5), quantile(calls, 0.9), quantile(tin, 0.5),
            quantile(tin, 0.9), quantile(tcache, 0.5), quantile(tcache, 0.9), quantile(tout, 0.5),
            quantile(tout, 0.9), quantile(secs, 0.5) if secs else None, quantile(secs, 0.9) if secs else None,
            bases.pop() if len(bases) == 1 else "mixed", quantile(twrite, 0.5), quantile(twrite, 0.9),
            judge_calls_p50=judged[0], judge_calls_p90=judged[1], judge_tokens_in_p50=judged[2],
            judge_tokens_in_p90=judged[3], judge_tokens_out_p50=judged[4], judge_tokens_out_p90=judged[5])
    return out


def lookup(table: Mapping[Key, KeyStats], benchmark: str, suite: str, attack: str | None,
           family: str | None, backend: str | None = None) -> tuple[KeyStats, str] | None:
    """The most specific key present: this model family on this backend, this family on any backend (or imports),
    any model on this backend, then any model anywhere; the attack exactly (None: benign)."""
    tries = [((family or ""), (backend or ""), "this model family on this backend"),
             ((family or ""), "", "this model family"), ("", (backend or ""), "any model on this backend"),
             ("", "", "any model")]
    seen: set[tuple[str, str]] = set()
    for fam, back, what in tries:
        if (fam, back) in seen or (not fam and what.startswith("this model")) or (not back and "backend" in what):
            continue
        seen.add((fam, back))
        hit = table.get((benchmark, suite, attack or "", fam, back))
        if hit is not None:
            return hit, what
    return None


def sample_corpus(root: Path, limit: int = SAMPLE_FILES) -> list[ExecutionUsage]:
    """The counts of up to ``limit`` AER files of a stored corpus, spread evenly over its sorted file list."""
    aer = Path(root) / "aer"
    files = sorted(aer.rglob("*.aer.jsonl")) if aer.is_dir() else []
    step = max(1, len(files) // max(1, limit))
    return [u for u in (execution_usage(p) for p in files[::step][:limit]) if u is not None]
