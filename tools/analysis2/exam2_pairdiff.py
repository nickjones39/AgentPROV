"""Examination 2: difference signatures of the same execution id in two corpora, on a seeded sample (read-only).

Reuses the structural diff of ``exam2_p9diff``. Usage:
``python tools/analysis2/exam2_pairdiff.py --a DIR --b DIR --n 200 --out REPORT.json``.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exam2_p9diff as D  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, type=Path)
    ap.add_argument("--b", required=True, type=Path)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    A, Bd = a.a.expanduser(), a.b.expanduser()
    D._init(str(A), str(Bd))
    rows = {r["ex"]: r for r in (json.loads(x) for x in (Bd / "executions.jsonl").read_bytes().splitlines() if x)}
    shared = sorted(set(rows) & set(D._OLD_INDEX))
    sample = random.Random(20261011).sample(shared, min(a.n, len(shared)))
    sig: dict[str, Counter] = {"aer": Counter(), "sem": Counter(), "prov": Counter()}
    for ex in sample:
        res = D.one(rows[ex])
        for k, v in res.get("sigs", {}).items():
            sig[k][" | ".join(v)] += 1
    rep = {"a": A.name, "b": Bd.name, "shared": len(shared), "sampled": len(sample),
           "signatures": {k: v.most_common(10) for k, v in sig.items()}}
    a.out.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(rep, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
