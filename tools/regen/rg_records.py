"""Build ``docs/reports/regeneration/round/<corpus>-rgN/`` from one re-import's logs: counts, digests and statuses only.

Usage: python -I tools/regen/rg_records.py LOGDIR NAME OUTDIR   (NAME: the driver's prefix, e.g. ``agentharm-rg2``)

The same reductions as the round's records (D-357; ``round/README.md``):
- the CLI summaries keep counters, issue codes, failure codes and exit status, with the full summary's sha256;
- the compare report drops the keyed multisets that carry annotation arguments (``sem_annotations_net``,
  ``prov_attributes_net``, ``aer_pointers``), keeping their sizes and the full report's sha256, plus the counts derived
  from them without any argument (SEM annotations by kind and class, markers by status and class, ``apv:afterCausal``);
- timing rows drop the command.
Reads ``NAME-{import,dryrun,validate,verify,compare,verdict}.json`` and ``runs.jsonl`` under LOGDIR. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DROP = ("sem_annotations_net", "prov_attributes_net", "aer_pointers")
TIMING = ("label", "exit", "wall_s", "peak_tree_rss_mib", "peak_processes", "started")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def summary(path: Path) -> dict[str, Any]:
    d = json.loads(path.read_text())
    codes: dict[str, int] = {}
    for failure in d.get("failures") or []:
        codes[failure.get("code")] = codes.get(failure.get("code"), 0) + 1
    return {"command": d["command"], "format": d["format"], "agentprov_version": d["agentprov_version"],
            "corpus_id": d["corpus"]["corpus_id"], "corpus_state": d["corpus"]["state"], "exit_code": d["exit_code"],
            "outcome": d["outcome"], "counters": d["counters"], "issues_by_code": d["issues_by_code"],
            "failure_codes": codes, "source_sha256": _sha(path)}


def compare(path: Path) -> dict[str, Any]:
    d = json.loads(path.read_text())
    keep = {k: v for k, v in d.items() if k not in DROP}
    keep["dropped_keys"] = {k: len(d[k]) for k in DROP if k in d}
    # counts derived from the dropped multisets (kinds, classes and marker statuses only; no annotation argument)
    by_kind: dict[str, int] = {}
    markers: dict[str, int] = {}
    for key, n in d.get("sem_annotations_net", {}).items():
        kind, args, cls = json.loads(key)[:3]
        by_kind[f"{kind} {cls}"] = by_kind.get(f"{kind} {cls}", 0) + n
        if kind == "injection_marker" and isinstance(args, dict):
            status = f"{args.get('status')} {cls}"
            markers[status] = markers.get(status, 0) + n
    keep["sem_annotations_net_by_kind_class"] = by_kind
    keep["injection_markers_net_by_status_class"] = markers
    keep["prov_attributes_net_afterCausal"] = {k: v for k, v in d.get("prov_attributes_net", {}).items()
                                               if k.endswith(" apv:afterCausal")}
    keep["source_sha256"] = _sha(path)
    return keep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("logdir", type=Path)
    ap.add_argument("name")
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    for step in ("import", "dryrun", "validate", "verify"):
        _dump(a.out / f"{step}.json", summary(a.logdir / f"{a.name}-{step}.json"))
    _dump(a.out / "compare.json", compare(a.logdir / f"{a.name}-compare.json"))
    _dump(a.out / "verdict.json", json.loads((a.logdir / f"{a.name}-verdict.json").read_text()))
    rows = []
    for line in (a.logdir / "runs.jsonl").read_text().splitlines():
        if line.strip():
            run = json.loads(line)
            if str(run.get("label", "")).startswith(f"{a.name}-") and run["label"].rsplit("-", 1)[-1] in {
                    "import", "dryrun", "validate", "verify", "compare"}:
                rows.append({k: run[k] for k in TIMING if k in run})
    _dump(a.out / "timings.json", sorted(rows, key=lambda r: r.get("started", "")))
    print(json.dumps({"out": str(a.out), "timings": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
