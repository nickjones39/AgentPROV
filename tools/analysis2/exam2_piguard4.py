"""Examination 2, S01 session effect: in cells where a PI-detector arm made **no** decision (so its inputs to the model
equal the undefended arm's), compare the outcomes of the detector run and the undefended run of the same model.
A difference there is not a defence effect (read-only; counts only).

Usage: ``python tools/analysis2/exam2_piguard4.py --corpus DIR --model MODEL --out REPORT.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

DETECTORS = ("piguard_detector", "prompt_guard_2_detector", "transformers_pi_detector")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    root = a.corpus.expanduser()
    arms: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for x in (root / "executions.jsonl").read_bytes().splitlines():
        if not x:
            continue
        r = json.loads(x)
        recs = [json.loads(y) for y in (root / r["paths"]["aer"]).read_bytes().split(b"\n") if y]
        agent = next((y for y in recs if y.get("k") == "actor" and y.get("kind") == "llm_agent"), {})
        if (agent.get("model") or {}).get("requested") != a.model:
            continue
        t = recs[0].get("task") or {}
        cell = (t.get("suite"), t.get("task_id"), t.get("attack_id"), t.get("attack_target_id"))
        j = {y.get("name"): y.get("value") for y in recs if y.get("k") == "judgement" and y.get("origin") == "checker"}
        arms[str(t.get("defense_id"))][cell] = {"dec": sum(1 for y in recs if y.get("k") == "decision"), "u": j.get("utility"),
                                                "s": j.get("security"), "attacked": t.get("attack_id") is not None}
    out = {"model": a.model}
    for d in DETECTORS:
        c: Counter = Counter()
        for cell, f in arms[d].items():
            base = arms["None"].get(cell)
            if base is None or f["dec"]:
                continue
            c["cells_no_decision"] += 1
            c[f"utility_detector={f['u']}|undefended={base['u']}"] += 1
            if f["attacked"]:
                c[f"attacked_security_detector={f['s']}|undefended={base['s']}"] += 1
        out[d] = dict(sorted(c.items()))
    a.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
