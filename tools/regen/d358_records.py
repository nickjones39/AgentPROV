"""Build ``docs/reports/regeneration/d358/<name>/*.json`` from the D-358 logs: counters, issue codes and digests only.

Usage: python -I tools/regen/d358_records.py OUT_DIR [--logs DIR]

Per corpus: ``import.json`` (the afe7038 import summary reduced to exit code, outcome, counters and issue codes, with the
full summary's sha256), ``tree.json`` (the ``tree_compare.py`` report, which holds file counts, area counts and
``corpus.json`` pointers, never content), ``timing.json`` (``measure.py``'s row: wall time, load, peak RSS, workers).
For ROPE also ``validate-afe7038.json``: the afe7038 validator's batch summaries, totalled, with the checks it skipped.
A corpus whose import or comparison is missing is left out. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

#: corpus -> (summary stem, tree report, measure.py label); Mandate ran first, as ``d358b`` (2026-10-14)
CORPORA = {
    "mandate": ("d358b-mandate", "d358-mandate-tree.json", "d358b-mandate-import-at-afe7038"),
    "agentharm": ("d358-agentharm", "d358-agentharm-tree.json", "d358-agentharm-import-afe7038"),
    "survey": ("d358-survey", "d358-survey-tree.json", "d358-survey-import-afe7038"),
    "adprov": ("d358-adprov", "d358-adprov-tree.json", "d358-adprov-import-afe7038"),
    "d2024": ("d358-d2024", "d358-d2024-tree.json", "d358-d2024-import-afe7038"),
    "rope": ("d358-rope", "d358-rope-tree.json", "d358-rope-import-afe7038"),
    "head": ("d358-head", "d358-head-tree.json", "d358-head-import-afe7038"),
    "agentdyn": ("d358-agentdyn", "d358-agentdyn-tree.json", "d358-agentdyn-import-afe7038"),
}
TIMING_KEYS = ("exit", "started", "wall_s", "load_start", "load_end", "peak_tree_rss_mib", "peak_processes")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--logs", type=Path, default=Path.home() / ".agentprov/migration-work/regen-plan/logs")
    a = ap.parse_args()
    runs: dict[str, dict[str, Any]] = {}
    for line in (a.logs / "runs.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row.get("exit") == 0:
            runs[row["label"]] = row  # the last successful run of a label is the one compared
    done = []
    for name, (stem, tree_name, label) in CORPORA.items():
        imp, tree = a.logs / f"{stem}-import.json", a.logs / tree_name
        if not imp.exists() or not tree.exists():
            continue
        summary = json.loads(imp.read_text())
        _dump(a.out / name / "import.json", {"source_sha256": _sha(imp), "exit_code": summary["exit_code"],
                                              "outcome": summary["outcome"], "counters": summary["counters"],
                                              "issues_by_code": summary["issues_by_code"]})
        _dump(a.out / name / "tree.json", {"source_sha256": _sha(tree), **json.loads(tree.read_text())})
        if label in runs:
            run = runs[label]
            jobs = int(run["command"][run["command"].index("--jobs") + 1])
            _dump(a.out / name / "timing.json", {k: run[k] for k in TIMING_KEYS} | {"jobs": jobs})
        done.append(name)
    val = a.logs / "d358-rope-validate-afe7038.jsonl"
    if val.exists():
        counters: Counter[str] = Counter()
        codes: Counter[str] = Counter()
        exits: Counter[str] = Counter()
        skips: Counter[str] = Counter()
        for line in val.read_text().splitlines():
            row = json.loads(line)
            counters.update(row["counters"])
            codes.update(row["issues_by_code"])
            exits[str(row["exit_code"])] += 1
            skips.update(f["detail"] for f in row["failures"] if f["code"] == "validate.check.skipped")
        batches = sum(exits.values())
        _dump(a.out / "rope" / "validate-afe7038.json", {
            "source_sha256": _sha(val), "batches": batches, "exit_codes": dict(exits), "counters": dict(counters),
            "issues_by_code": dict(codes), "skipped_checks_per_batch": {k: v // batches for k, v in skips.items()}})
    print("records:", ", ".join(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
