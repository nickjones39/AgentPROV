"""Examination 2: summarise the D01/D02 outputs of ``exam2_determinism.py run`` (counts, intervals, failing ids).

Usage: ``python tools/analysis2/exam2_detsum.py OUTDIR > SUMMARY.json``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam2_lib import cp_upper_zero, wilson  # noqa: E402


def main() -> int:
    d = Path(sys.argv[1])
    configs: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(d.glob("c*.jsonl")):
        configs[p.name.split(".")[0]] += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
    out: dict = {"configs": {}}
    shas: dict[tuple, set] = defaultdict(set)
    for name, rows in sorted(configs.items()):
        c: Counter = Counter()
        bad = []
        for r in rows:
            c["n"] += 1
            if "error" in r:
                c["errors"] += 1
                bad.append(r["ex"])
                continue
            ok_sem = all(v["equal"] for v in r.get("sem", {}).values())
            ok_prov = r.get("prov", {}).get("equal", False)
            c["sem_equal"] += ok_sem
            c["prov_equal"] += ok_prov
            if not (ok_sem and ok_prov):
                bad.append(r["ex"])
            if "validation_equal" in r:
                c["validation_checked"] += 1
                c["validation_equal"] += r["validation_equal"]
            shas[(r["corpus"], r["ex"])].add((json.dumps(r.get("sem"), sort_keys=True), json.dumps(r.get("prov"), sort_keys=True)))
            c[f"corpus|{r['corpus']}"] += 1
        n = c["n"] - c["errors"]
        k_fail = n - min(c["sem_equal"], c["prov_equal"])
        out["configs"][name] = {**dict(c), "mismatching_ex": bad[:10],
                                "upper95_if_zero": round(cp_upper_zero(n), 5) if k_fail == 0 else None,
                                "wilson95": [round(x, 5) for x in wilson(k_fail, n)]}
    out["executions_with_differing_outputs_across_configs"] = sum(1 for v in shas.values() if len(v) > 1)
    p = d / "d02_remap.jsonl"
    if p.exists():
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
        c = Counter()
        bad = []
        for r in rows:
            if r.get("skipped"):
                c[f"skipped_{r['skipped']}"] += 1
            elif "error" in r:
                c["errors"] += 1
                bad.append([r["ex"], r["error"]])
            else:
                c["remapped"] += 1
                c["aer_equal"] += r["aer_equal"]
                c[f"corpus|{r['corpus']}"] += 1
                if not r["aer_equal"]:
                    bad.append([r["ex"], r.get("diff_record"), r.get("diff_keys")])
        n = c["remapped"]
        out["d02"] = {**dict(c), "mismatches": bad[:10],
                      "upper95_if_zero": round(cp_upper_zero(n), 5) if n and c["aer_equal"] == n else None}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
