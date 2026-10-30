"""Gate R3 at full scope: the field-level diff of every native June-2024 AER and its converted v1 AER (J.4.3, J.4.4).

    uv run python tools/migration/r3_reconcile.py --out docs/reports/migration [--workers 10] [--limit N]

Local only, no network: the native logs are the ``runs/**/*.json`` blobs of ``ethz-spylab/agentdojo@c274885`` in the bare,
extraction-free fetch cache (each blob checked against its git blob SHA-1; ``tools/agentdojo/import_scan.py``'s reader),
and the converted transcripts are the files of ``$AGENTPROV_BASELINE_CORPUS/corpus/corpus-og-agentdojo-runs-prov``
joined by the converter's own layout rule (``import_scan.output_relpath``; gate R's join). Both sides are mapped by the
product mappers (``agentdojo-upstream`` with the pinned ``git`` origin; ``adprov-v1`` with the frozen-corpus origin the
migration gates record, J.4), projected and classified by :mod:`agentprov.migration.reconcile`.

Writes ``R3-full.json`` (counts by category and field pattern, unexplained cases with their first items, lineage
verdicts) and ``R3-lineage.jsonl`` (one lineage record per matched pair). Nothing holds source text: field patterns,
counts, digests and pinned paths.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentdojo"))
import import_scan as scan  # noqa: E402  (gate R's pinned-blob reader and the converter's layout rule)

BASELINE_COMMIT: Final = "579a908354b93361efe0905ffb7623256aa96a06"
CONVERTED: Final = scan.CONVERTED
_STATE: dict[str, Any] = {}


def _init(root: str, listing: frozenset[str]) -> None:
    _STATE.update(root=root, listing=listing)


def _records(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.splitlines()]


def work(job: tuple[str, str, bytes]) -> dict[str, Any]:
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin
    from agentprov.migration.reconcile import classify, lineage, project

    path, blob, raw = job
    row: dict[str, Any] = {"path": path}
    try:
        native_data, native_info = aer_bytes(map_artefact(raw, Origin.git(scan.REPO, scan.COMMIT, path, blob),
                                                          profile_id=scan.PROFILE)[0])
        native = _records(native_data)
        header, task = native[0], native[0].get("task", {})
        row["unit"] = header.get("unit")
        pipeline = (header.get("ext", {}).get("agentdojo", {}) or {}).get("pipeline_name")
        stem = scan.output_relpath(str(pipeline), str(task.get("suite")), str(task.get("task_id")), task.get("attack_id"),
                                   task.get("attack_target_id"))
        rel = f"{stem}.transcript.json"
        if rel not in _STATE["listing"]:
            row["matched"] = False
            return row
        row["matched"] = True
        transcript = Path(_STATE["root"], rel).read_bytes()
        origin = Origin.corpus("AgentDojo-PROV", "2.3", f"{CONVERTED.rsplit('/', 1)[-1]}/{rel}", producer_commit=BASELINE_COMMIT)
        v1_data, v1_info = aer_bytes(map_artefact(transcript, origin, profile_id="adprov-v1")[0])
        v1 = _records(v1_data)
        row["classes"] = [[c, p, r, n] for (c, p, r), n in classify(project(native), project(v1)).items()]
        row["lineage"] = lineage(header, v1[0], native_sha256=native_info.file_sha256, v1_sha256=v1_info.file_sha256,
                                 v1_issue_codes=[str(i.get("code")) for i in v1_info.issues])
        row["item"] = rel
    except Exception as exc:  # a crash is a finding; the label is the pinned path, never content
        row["crash"] = getattr(exc, "code", type(exc).__name__)
    return row


def run(cache: Path, baseline: Path, *, workers: int, limit: int | None) -> dict[str, Any]:
    from agentprov.migration.reconcile import ReconciliationReport

    entries = scan.list_blobs(cache)
    if limit is not None:
        entries = entries[:limit]
    root = baseline / CONVERTED
    listing = scan.converted_listing(root)
    report = ReconciliationReport()
    unmatched: list[str] = []
    crashes: dict[str, str] = {}
    started = time.perf_counter()
    with Pool(workers, initializer=_init, initargs=(str(root), listing)) as pool:
        for row in pool.imap(work, scan.read_blobs(cache, entries), chunksize=16):
            if "crash" in row:
                crashes[row["path"]] = str(row["crash"])
            elif not row.get("matched"):
                unmatched.append(row["path"])
            else:
                report.pairs += 1
                for category, pattern, rule, n in row["classes"]:
                    report.categories[(category, pattern, rule)] += n
                    if category == "differs_unexpected" or rule == "unexplained":
                        key = f"{category}:{pattern}"
                        report.unexplained[key] += 1
                        firsts = report.unexplained_items.setdefault(key, [])
                        if len(firsts) < 5:
                            firsts.append(row["item"])
                report.lineage.append(row["lineage"])
                report.lineage_verdicts[str(row["lineage"]["verdict"])] += 1
    document = report.to_json()
    document.update(
        native_logs=len(entries), unmatched_native=len(unmatched),
        unmatched_native_first=sorted(unmatched)[:20], crashes=len(crashes), crash_codes=dict(sorted(crashes.items())[:20]),
        upstream={"repo": scan.REPO, "commit": scan.COMMIT}, baseline_commit=BASELINE_COMMIT,
        elapsed_s=round(time.perf_counter() - started, 1),
    )
    return {"report": document, "lineage": sorted(report.lineage, key=lambda r: str(r["upstream_path"]))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=scan.DEFAULT_CACHE)
    parser.add_argument("--baseline", type=Path, default=os.environ.get("AGENTPROV_BASELINE_CORPUS"),
                        help="the AgentDojo-PROV checkout; default $AGENTPROV_BASELINE_CORPUS")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.baseline is None:
        parser.error("--baseline or $AGENTPROV_BASELINE_CORPUS is required")
    result = run(args.cache, Path(args.baseline), workers=args.workers, limit=args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.limit is None else f".limit{args.limit}"
    (args.out / f"R3-full{suffix}.json").write_text(json.dumps(result["report"], indent=2, sort_keys=True) + "\n",
                                                    encoding="utf-8")
    (args.out / f"R3-lineage{suffix}.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in result["lineage"]), encoding="utf-8")
    doc = result["report"]
    print(f"R3: {doc['pairs']} pairs, passed={doc['passed']}, unexplained={len(doc['unexplained'])}, "
          f"lineage={doc['lineage_verdicts']}, unmatched native={doc['unmatched_native']}, crashes={doc['crashes']}, "
          f"{doc['elapsed_s']} s")
    return 0 if doc["passed"] and not doc["crashes"] else 1


if __name__ == "__main__":
    sys.exit(main())
