"""Compare ``agentdojo.suites@1`` with the v2.3 labels over the full baseline trees (local only; numbers, no content).

    uv run python tools/agentdojo/sem_equivalence_scan.py --baseline ../AgentDojo-PROV-framework \
        --out docs/reports/sem/equivalence-v2.3.json

Each v1 transcript is mapped with the ``adprov-v1`` profile (as the migration gates do), annotated with the semantics
profile and compared element by element with its stored v2.3 graph by :mod:`agentprov.testing.sem_v23`: integrity of
every tool output, the user query and the agent's parts; role of every tool activity (sink <=> any sink role); source
channel; injection marker. Differences are counted by category (registered: ``unknown_tool_fail_closed``,
``yaml_rejection_fallback``; anything else is ``unexplained``), with the items of unexplained ones. Also counted: the
annotation census (type x value; marker statuses), and the outcome claims. Prints and writes no transcript content.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

COMMIT = "579a908354b93361efe0905ffb7623256aa96a06"


def work(args: tuple[str, str, str, str | None, str]) -> dict[str, Any]:
    item, tree, transcript, graph, relpath = args
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.testing import sem_v23

    try:
        profile = load_semantics_profile("agentdojo.suites", 1)
        raw = Path(transcript).read_bytes()
        outcome, _ = map_artefact(raw, Origin.corpus("AgentDojo-PROV", "2.3", relpath, producer_commit=COMMIT),
                                  profile_id="adprov-v1")
        if outcome.degenerate:
            return {"tree": tree, "status": "degenerate", "item": item}
        data, _ = aer_bytes(outcome)
        doc = load_aer_bytes(data)
        anns = list(profile.annotate(doc))
        known = profile.known_tools(doc)[0]  # type: ignore[attr-defined]
        census: Counter[str] = Counter()
        for a in anns:
            value = a.value["status"] if a.type == "injection_marker" else a.value  # type: ignore[index]
            census[f"{a.type}={json.dumps(value, sort_keys=True)}/{a.ev}"] += 1
        diffs = sem_v23.compare_with_v23(doc, anns, sem_v23.load_graph(Path(graph)), known) if graph else []
        return {
            "tree": tree, "status": "ok", "item": item, "census": dict(census),
            "diffs": [{"category": d.category or "unexplained", "attribute": d.attribute, "v23": d.v23,
                       "sem": d.sem, "element": d.element} for d in diffs],
            "unknown_tool_turns": sum(1 for te in doc.of_kind("tool_execution") if te["name"] not in known),
        }
    except Exception as exc:  # a failure is a finding; the item label is a corpus-relative path
        return {"tree": tree, "status": "error", "item": item, "code": getattr(exc, "code", type(exc).__name__),
                "where": traceback.format_exc().splitlines()[-1][:200]}


def native_work(job: tuple[str, str, bytes]) -> dict[str, Any]:
    """One pinned native log: map (``agentdojo-upstream``), annotate, compare with its converted pair's v2.3 graph."""
    path, blob, raw = job
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.testing import sem_v23

    import import_scan as scan  # tools/agentdojo (on sys.path in the parent and the workers)

    try:
        profile = load_semantics_profile("agentdojo.suites", 1)
        outcome, _ = map_artefact(raw, Origin.git(scan.REPO, scan.COMMIT, path, blob), profile_id=scan.PROFILE)
        if outcome.degenerate:
            return {"tree": "native", "status": "degenerate", "item": path}
        doc = load_aer_bytes(aer_bytes(outcome)[0])
        anns = list(profile.annotate(doc))
        known = profile.known_tools(doc)[0]  # type: ignore[attr-defined]
        census: Counter[str] = Counter()
        for a in anns:
            value = a.value["status"] if a.type == "injection_marker" else a.value  # type: ignore[index]
            census[f"{a.type}={json.dumps(value, sort_keys=True)}/{a.ev}"] += 1
        task, ext = doc.header.get("task", {}), doc.header.get("ext", {}).get("agentdojo", {})
        stem = scan.output_relpath(str(ext.get("pipeline_name")), str(task.get("suite")), str(task.get("task_id")),
                                   task.get("attack_id"), task.get("attack_target_id"))
        graph = Path(_NATIVE["root"], f"{stem}.json") if f"{stem}.transcript.json" in _NATIVE["listing"] else None
        diffs = sem_v23.compare_with_v23(doc, anns, sem_v23.load_graph(graph), known) if graph else []
        return {
            "tree": "native", "status": "ok", "item": path, "census": dict(census), "matched": graph is not None,
            "diffs": [{"category": d.category or "unexplained", "attribute": d.attribute, "v23": d.v23,
                       "sem": d.sem, "element": d.element} for d in diffs],
            "unknown_tool_turns": sum(1 for te in doc.of_kind("tool_execution") if te["name"] not in known),
        }
    except Exception as exc:
        return {"tree": "native", "status": "error", "item": path, "code": getattr(exc, "code", type(exc).__name__),
                "where": traceback.format_exc().splitlines()[-1][:200]}


_NATIVE: dict[str, Any] = {}


def _native_init(root: str, listing: frozenset[str]) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    _NATIVE.update(root=root, listing=listing)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tree in ("release", "converted", "native"):
        mine = [r for r in rows if r["tree"] == tree]
        ok = [r for r in mine if r["status"] == "ok"]
        census: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        by_attribute: Counter[str] = Counter()
        unexplained: list[dict[str, Any]] = []
        for r in ok:
            census.update(r["census"])
            for d in r["diffs"]:
                categories[d["category"]] += 1
                by_attribute[f"{d['category']}:{d['attribute']}"] += 1
                if d["category"] == "unexplained":
                    unexplained.append({"item": r["item"], "element": d["element"], "attribute": d["attribute"],
                                        "v23": d["v23"], "sem": d["sem"]})
        if not mine:
            continue
        out[tree] = {
            "executions": len(mine),
            "compared_with_v2_3": sum(1 for r in ok if r.get("matched", True)),
            "annotated": len(ok),
            "degenerate": sum(r["status"] == "degenerate" for r in mine),
            "failures": sorted(({"item": r["item"], "code": r["code"], "where": r["where"]} for r in mine
                                if r["status"] == "error"), key=lambda f: f["item"]),
            "differences": dict(sorted(categories.items())),
            "differences_by_attribute": dict(sorted(by_attribute.items())),
            "executions_with_differences": sum(1 for r in ok if r["diffs"]),
            "unknown_tool_turns": sum(r["unknown_tool_turns"] for r in ok),
            "unexplained": sorted(unexplained, key=lambda u: (u["item"], u["element"], u["attribute"]))[:200],
            "census": dict(sorted(census.items())),
        }
    return out


def main() -> int:
    from agentprov.migration.pipeline import full_inputs

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True, help="the AgentDojo-PROV repository root")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--native-cache", type=Path, default=None,
                        help="also annotate every pinned native log of agentdojo@c274885 from this bare object store "
                             "and compare each with the v2.3 graph of its converted pair (J.3.5)")
    args = parser.parse_args()
    pairs, _ = full_inputs(args.baseline)
    jobs = [(p.item, p.tree, str(p.transcript), str(p.graph) if p.graph else None, p.origin_relpath) for p in pairs]
    with Pool(args.workers) as pool:
        rows = list(pool.imap_unordered(work, jobs, chunksize=20))
    if args.native_cache is not None:
        _native_init("", frozenset())
        import import_scan as scan

        root = args.baseline / scan.CONVERTED
        listing = scan.converted_listing(root)
        entries = scan.list_blobs(args.native_cache.expanduser())
        with Pool(args.workers, initializer=_native_init, initargs=(str(root), listing)) as pool:
            rows += list(pool.imap(native_work, scan.read_blobs(args.native_cache.expanduser(), entries), chunksize=16))
    report = {"scan": "agentdojo.suites@1 vs AgentDojo-PROV v2.3 labels over the baseline v1 trees"
                      + (" and the native 2024-06 logs" if args.native_cache is not None else ""),
              "baseline_commit": COMMIT, "trees": summarise(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    trees = report["trees"]
    failures = sum(len(t["failures"]) for t in trees.values())
    unexplained = sum(t["differences"].get("unexplained", 0) for t in trees.values())
    print(f"{len(rows)} executions, {failures} failures, {unexplained} unexplained differences -> {args.out}")
    for name, t in trees.items():
        print(f"  {name}: {t['differences']} unknown tool turns {t['unknown_tool_turns']}")
    return 1 if failures or unexplained else 0


if __name__ == "__main__":
    raise SystemExit(main())
