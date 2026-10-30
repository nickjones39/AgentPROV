"""The concurrency sweep ``run --tune-jobs`` (N.2.1a(4); D-820, D-821): metrics, the recommendation and the report.

The sweep runs one fixed cell sample per ``jobs`` value ("arm"), each into its own working corpus, and measures it:
the wall time on T0's clock, and per call, from the stored capture logs (strict, bounded parsing; the logs are
untrusted evidence), the latency between ``llm.request`` and its ``llm.response`` (``mono_ns``), client timeouts
(an ``exception.type`` naming a timeout) and token usage. No prompt, reply or tool text is copied.

**Rule (N.2.1a(4)):** ``peak`` is the highest traces-per-hour of any arm that ran. The recommendation is the smallest N
whose arm reaches ``RATE_SHARE x peak`` with no request timeout and no failed cell; none qualifies -> no
recommendation. Orchestration (consent, the probe, the arms) is in :mod:`agentprov.cli.run`; this module is pure
apart from :func:`write_report`.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

TUNE_FORMAT: Final = "agentprov-tune-jobs/0.1"
ARM_FORMAT: Final = "agentprov-tune-arm/0.1"
RATE_SHARE: Final = 0.9
MAX_ARMS: Final = 12
#: a client-side timeout as the SDK and httpx name it (``APITimeoutError``, ``ReadTimeout``, ``TimeoutException``...)
_TIMEOUT = re.compile(r"Timeout")
_USAGE_IN: Final = ("prompt_tokens", "input_tokens")
_USAGE_OUT: Final = ("completion_tokens", "output_tokens")


class TuneUsageError(ValueError):
    """A ``--tune-jobs`` value the sweep refuses (the CLI reports it as a usage error, exit 2)."""


def parse_jobs(text: str, *, host_max: int | None = None) -> list[int]:
    """``--tune-jobs 1,2,4,6,8,12``: 1 to :data:`MAX_ARMS` distinct integers >= 1, in the order given."""
    parts = [p.strip() for p in text.split(",")]
    if not parts or any(not re.fullmatch(r"[0-9]{1,3}", p, re.ASCII) for p in parts):
        raise TuneUsageError("--tune-jobs takes integers separated by commas, e.g. 1,2,4,6,8,12")
    values = [int(p) for p in parts]
    if any(v < 1 for v in values):
        raise TuneUsageError("--tune-jobs values must be >= 1")
    if len(set(values)) != len(values):
        raise TuneUsageError("--tune-jobs values must be distinct")
    if len(values) > MAX_ARMS:
        raise TuneUsageError(f"--tune-jobs takes at most {MAX_ARMS} values")
    if host_max is not None and max(values) > host_max:
        raise TuneUsageError(f"--tune-jobs {max(values)} exceeds this host's maximum of {host_max} concurrent traces")
    return values


# ---------------------------------------------------------------------------------------------- per-call facts


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


@dataclass
class CallFacts:
    """What one stored capture log says about its model calls (counts and numbers only)."""

    latencies_ms: list[float] = field(default_factory=list)
    timeouts: int = 0
    errors: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    unparsed: int = 0


def call_facts(log: bytes, *, limits: Any = None) -> CallFacts:
    """The calls of one capture log: request-to-response latency (``mono_ns``), client timeouts, usage."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    limits = limits or IngestLimits()
    out = CallFacts()
    started: dict[str, int] = {}
    for line in log.split(b"\n"):
        if not line:
            continue
        try:
            event = strict_json_loads(line, limits, record=True)
        except IngestError:
            out.unparsed += 1
            continue
        if not isinstance(event, Mapping) or not isinstance(event.get("data"), Mapping):
            out.unparsed += 1
            continue
        kind, data, mono = event.get("type"), event["data"], _int(event.get("mono_ns"))
        call = data.get("call")
        if kind == "llm.request" and isinstance(call, str) and mono is not None:
            started[call] = mono
        elif kind == "llm.response":
            begin = started.pop(call, None) if isinstance(call, str) else None
            if begin is not None and mono is not None and mono >= begin:
                out.latencies_ms.append((mono - begin) / 1e6)
            exc = data.get("exception")
            etype = exc.get("type") if isinstance(exc, Mapping) else None
            if isinstance(etype, str) and _TIMEOUT.search(etype):
                out.timeouts += 1
            elif data.get("status") not in ("kept", "discarded"):
                out.errors += 1
            usage = data.get("usage")
            if isinstance(usage, Mapping):
                out.tokens_in += next((v for k in _USAGE_IN if (v := _int(usage.get(k))) is not None), 0)
                out.tokens_out += next((v for k in _USAGE_OUT if (v := _int(usage.get(k))) is not None), 0)
    return out


def _quantile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def arm_metrics(jobs: int, *, wall_s: float, counters: Mapping[str, int], entries: Iterable[Mapping[str, Any]],
                read_log: Callable[[Mapping[str, Any]], bytes | None], limits: Any = None) -> dict[str, Any]:
    """One arm's measurement (D-821): from T0's wall time, the campaign counters and the ledgered sessions' logs."""
    facts = CallFacts()
    cell_timeouts = sessions = 0
    for entry in entries:
        sessions += 1
        if entry.get("parent_note") == "timeout":
            cell_timeouts += 1
        log = read_log(entry)
        if log is None:
            continue
        one = call_facts(log, limits=limits)
        facts.latencies_ms += one.latencies_ms
        facts.timeouts += one.timeouts
        facts.errors += one.errors
        facts.tokens_in += one.tokens_in
        facts.tokens_out += one.tokens_out
        facts.unparsed += one.unparsed
    conclusive = int(counters.get("conclusive", 0))
    hours = wall_s / 3600 if wall_s > 0 else 0.0
    return {
        "jobs": jobs, "status": "ran", "wall_s": round(wall_s, 3),
        "cells": {k: int(counters.get(k, 0)) for k in ("cells_planned", "attempted", "conclusive", "inconsistent",
                                                       "inconclusive", "failed")},
        "sessions": sessions,
        "traces_per_hour": round(conclusive / hours, 3) if hours else None,
        "calls": len(facts.latencies_ms), "call_errors": facts.errors,
        "request_timeouts": facts.timeouts + cell_timeouts,
        "client_timeouts": facts.timeouts, "cell_timeouts": cell_timeouts,
        "latency_ms": {"p50": _r(_quantile(facts.latencies_ms, 0.5)), "p90": _r(_quantile(facts.latencies_ms, 0.9)),
                       "max": _r(max(facts.latencies_ms) if facts.latencies_ms else None)},
        "tokens": {"prompt": facts.tokens_in, "completion": facts.tokens_out,
                   "prompt_per_s": round(facts.tokens_in / wall_s, 2) if wall_s > 0 else None,
                   "completion_per_s": round(facts.tokens_out / wall_s, 2) if wall_s > 0 else None},
        "seconds_per_cell": round(wall_s * jobs / conclusive, 3) if conclusive else None,
        "unparsed_log_lines": facts.unparsed,
    }  # fmt: skip


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def skipped(jobs: int, reason: str) -> dict[str, Any]:
    """An arm that did not run: ``memory`` (above ``J_memory``) or ``after_timeouts`` (the stop rule, D-820)."""
    return {"jobs": jobs, "status": "skipped", "reason": reason}


def eligible(arm: Mapping[str, Any]) -> bool:
    """An arm the rule may pick: it ran, with no request timeout and no failed or unfinished cell."""
    cells = arm.get("cells") or {}
    return (arm.get("status") == "ran" and arm.get("traces_per_hour") is not None
            and int(arm.get("request_timeouts") or 0) == 0 and int(cells.get("failed", 0)) == 0
            and int(cells.get("conclusive", 0)) == int(cells.get("cells_planned", -1)))


def stops_sweep(arm: Mapping[str, Any]) -> bool:
    """The stop rule (D-820): after an arm with a request timeout or a failed cell, higher arms are skipped."""
    cells = arm.get("cells") or {}
    return arm.get("status") == "ran" and (int(arm.get("request_timeouts") or 0) > 0 or int(cells.get("failed", 0)) > 0)


def recommend(arms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """N.2.1a(4): the smallest N reaching ``RATE_SHARE x peak`` with no timeout and no failed cell."""
    rates = [float(a["traces_per_hour"]) for a in arms if a.get("status") == "ran" and a.get("traces_per_hour")]
    peak = max(rates) if rates else None
    pick = None
    if peak:
        good = sorted(int(a["jobs"]) for a in arms if eligible(a) and float(a["traces_per_hour"]) >= RATE_SHARE * peak)
        pick = good[0] if good else None
    return {"rule": {"rate_share": RATE_SHARE, "request_timeouts": 0, "failed_cells": 0},
            "peak_traces_per_hour": peak, "jobs": pick}


# ---------------------------------------------------------------------------------------------- the report


def report_document(*, header: Mapping[str, Any], arms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"format": TUNE_FORMAT, **dict(header), "arms": list(arms), "recommendation": recommend(arms)}


def report_markdown(doc: Mapping[str, Any]) -> str:
    """The report as a table (labels from the run; the model id is bounded and escaped for Markdown)."""
    from agentprov.cli.common import safe_text

    def cell(value: Any) -> str:
        return "—" if value is None else str(value)

    model = safe_text(str((doc.get("model") or {}).get("id") or ""), 160).replace("|", "\\|").replace("`", "'")
    lines = [f"# Concurrency sweep: `{model}`", "",
             f"Preset {doc.get('preset', {}).get('name')} v{doc.get('preset', {}).get('version')}; "
             f"{len(doc.get('sample', {}).get('cells', []))} cell(s) per arm; order {doc.get('order')}; "
             f"test_only {str(doc.get('test_only')).lower()}.", "",
             "| jobs | status | wall s | traces/h | timeouts | failed | p50 ms | p90 ms | s/cell |",
             "|---|---|---|---|---|---|---|---|---|"]
    for arm in doc.get("arms", []):
        if arm.get("status") != "ran":
            lines.append(f"| {arm['jobs']} | skipped ({arm.get('reason')}) | | | | | | | |")
            continue
        lat = arm.get("latency_ms") or {}
        lines.append(f"| {arm['jobs']} | ran | {cell(arm.get('wall_s'))} | {cell(arm.get('traces_per_hour'))} | "
                     f"{cell(arm.get('request_timeouts'))} | {cell((arm.get('cells') or {}).get('failed'))} | "
                     f"{cell(lat.get('p50'))} | {cell(lat.get('p90'))} | {cell(arm.get('seconds_per_cell'))} |")
    rec = doc.get("recommendation") or {}
    lines += ["", f"Peak {cell(rec.get('peak_traces_per_hour'))} traces/h; recommended jobs: "
                  f"**{cell(rec.get('jobs'))}** (smallest N ≥ {RATE_SHARE:.0%} of peak, no timeouts, no failed cell)."]
    return "\n".join(lines) + "\n"


def write_report(out_dir: Path, doc: Mapping[str, Any]) -> tuple[Path, Path]:
    """``tune-jobs.json`` (JCS) and ``tune-jobs.md`` in the sweep folder, written atomically."""
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.io.canonical import jcs_bytes

    js, md = out_dir / "tune-jobs.json", out_dir / "tune-jobs.md"
    atomic_write_bytes(js, jcs_bytes(dict(doc)) + b"\n")
    atomic_write_bytes(md, report_markdown(doc).encode("utf-8"))
    return js, md


def read_arm(path: Path, config_digest: str) -> dict[str, Any] | None:
    """A finished arm's ``tune-arm.json`` when it belongs to this configuration (resume, D-820); else ``None``."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        doc = strict_json_loads(data.strip(), IngestLimits())
    except IngestError:
        return None
    if not isinstance(doc, dict) or doc.get("format") != ARM_FORMAT or doc.get("config_digest") != config_digest:
        return None
    arm = doc.get("arm")
    return arm if isinstance(arm, dict) else None


def write_arm(path: Path, config_digest: str, arm: Mapping[str, Any]) -> None:
    from agentprov.io.atomic import atomic_write_bytes

    atomic_write_bytes(path, json.dumps({"format": ARM_FORMAT, "config_digest": config_digest, "arm": dict(arm)},
                                        sort_keys=True, indent=1).encode("utf-8") + b"\n")
