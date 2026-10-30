"""Examination 2, Q-045 / PI-30: cross-corpus overlap of raw objects and execution ids among the phase-10 corpora, and
which attributes of the shared ``raw:`` PROV entity differ (read-only; counts, attribute names, ids).

Usage: ``python tools/analysis2/exam2_overlap.py --out REPORT.json CORPUS_DIR [...]``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("corpora", nargs="+")
    a = ap.parse_args()
    raws: dict[str, dict[str, dict]] = {}
    exs: dict[str, set[str]] = {}
    rows_by: dict[str, dict[str, dict]] = {}
    for c in a.corpora:
        root = Path(c).expanduser()
        rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
        rows_by[root.name] = {r["ex"]: r for r in rows}
        exs[root.name] = set(rows_by[root.name])
        raws[root.name] = {}
        for r in rows:
            for rr in r.get("raw") or ():
                if rr.get("role") == "primary":
                    raws[root.name].setdefault(rr["sha256"], r)
    rep: dict = {"pairs": {}}
    names = sorted(raws)
    for x, y in combinations(names, 2):
        shared_raw = set(raws[x]) & set(raws[y])
        shared_ex = exs[x] & exs[y]
        if not shared_raw and not shared_ex:
            continue
        attr_diff: Counter = Counter()
        aer_equal = Counter()
        sample = sorted(shared_raw)[:300]
        for sha in sample:
            rx, ry = raws[x][sha], raws[y][sha]
            aer_equal[str(rx["digests"]["aer"] == ry["digests"]["aer"])] += 1
            key = "raw:sha256-" + sha.split(":", 1)[1]
            dx = json.loads((Path(a.corpora[names.index(x)]).expanduser().parent / (x) / next(iter(rx["paths"]["prov"].values()))["json"]).read_bytes())
            dy = json.loads((Path(a.corpora[names.index(y)]).expanduser().parent / (y) / next(iter(ry["paths"]["prov"].values()))["json"]).read_bytes())
            ex_, ey_ = dx["entity"].get(key, {}), dy["entity"].get(key, {})
            for k in sorted(set(ex_) | set(ey_)):
                if ex_.get(k) != ey_.get(k):
                    attr_diff[k] += 1
        rep["pairs"][f"{x}|{y}"] = {"shared_primary_raw_objects": len(shared_raw), "shared_execution_ids": len(shared_ex),
                                    "sampled": len(sample), "aer_digest_equal_in_sample": dict(aer_equal),
                                    "raw_entity_attributes_differing_in_sample": dict(attr_diff),
                                    "example_shared_ex": sorted(shared_ex)[:3]}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(rep, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
