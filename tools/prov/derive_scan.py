"""Derive ``agentprov-prov/0.1`` over every baseline v1 transcript and report counts (local only; numbers, no content).

    uv run python tools/prov/derive_scan.py --baseline ../AgentDojo-PROV-framework --out docs/reports/prov/derive-scan.json

Each transcript is mapped with the ``adprov-v1`` profile (as the migration gates do), the AER is validated and derived,
and per-tree totals are written: executions, failures, statement counts by rule, bundles, communications by bundle
kind, gaps and derive latency. This is a robustness scan, not gate D: tier-4 validation and the full gate run in phase
13. The script prints and writes no transcript content.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
import traceback
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"


def work(args: tuple[str, str, str, str]) -> dict[str, Any]:
    item, tree, transcript, relpath = args
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer
    from agentprov.prov.engine import derive

    try:
        raw = Path(transcript).read_bytes()
        outcome, _ = map_artefact(raw, Origin.corpus("AgentDojo-PROV", "2.3", relpath, producer_commit=COMMIT),
                                  profile_id="adprov-v1")
        if outcome.degenerate:
            return {"tree": tree, "status": "degenerate"}
        data, _ = aer_bytes(outcome)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.aer.jsonl"
            path.write_bytes(data)
            doc = load_aer(path)
        start = time.perf_counter()
        result = derive(doc)
        return {
            "tree": tree,
            "status": "ok",
            "secs": time.perf_counter() - start,
            "rules": result.report.rules_fired,
            "bundles": [b.iri.rsplit(".", 1)[0].removeprefix("xd:bundle.") for b in result.bundles],
            "comm": result.report.communications,
            "skipped": len(result.report.skipped),
            "gaps": sum(1 for d in result.report.disclosed if d["code"] == "gap"),
        }
    except Exception as exc:  # a failure is a finding; the item label is a corpus-relative path
        return {"tree": tree, "status": "error", "item": item, "code": getattr(exc, "code", type(exc).__name__),
                "where": traceback.format_exc().splitlines()[-1][:200]}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tree in ("release", "converted"):
        mine = [r for r in rows if r["tree"] == tree]
        ok = [r for r in mine if r["status"] == "ok"]
        secs = sorted(r["secs"] for r in ok) or [0.0]
        rules: Counter[str] = Counter()
        bundles: Counter[str] = Counter()
        for r in ok:
            rules.update(r["rules"])
            bundles.update(r["bundles"])
        out[tree] = {
            "executions": len(mine),
            "derived": len(ok),
            "failures": sorted(({"item": r["item"], "code": r["code"]} for r in mine if r["status"] == "error"),
                               key=lambda f: f["item"]),
            "degenerate": sum(r["status"] == "degenerate" for r in mine),
            "statements_by_rule": dict(sorted(rules.items())),
            "bundles": dict(sorted(bundles.items())),
            "communications": {"core": sum(r["comm"]["core"] for r in ok),
                               "inference": sum(r["comm"]["inference"] for r in ok)},
            "gaps": sum(r["gaps"] for r in ok),
            "skipped_references": sum(r["skipped"] for r in ok),
            "derive_ms": {"median": round(statistics.median(secs) * 1000, 1),
                          "p99": round(secs[int(len(secs) * 0.99)] * 1000, 1), "max": round(secs[-1] * 1000, 1)},
        }
    return out


def main() -> int:
    from agentprov.migration.pipeline import full_inputs

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True, help="the AgentDojo-PROV repository root")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    pairs, _ = full_inputs(args.baseline)
    jobs = [(p.item, p.tree, str(p.transcript), p.origin_relpath) for p in pairs]
    with Pool(args.workers) as pool:
        rows = list(pool.imap_unordered(work, jobs, chunksize=20))
    report = {"scan": "agentprov-prov/0.1 derive over the baseline v1 trees", "baseline_commit": COMMIT,
              "trees": summarise(rows)}
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = sum(len(t["failures"]) for t in report["trees"].values())
    print(f"{len(rows)} executions, {failures} failures -> {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
