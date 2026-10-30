"""Examination 2, S01 follow-up: why are the three PI-detector arms of one AgentDyn model identical to each other but
never to the undefended arm? (read-only; digests, timings and counts only).

For one model it records, per arm and cell: digests of the system message, the first user message, the first assistant
message (and its first model call's input ids), the run start timestamp and duration, the number of redactions, and the
message count; then compares arms pairwise (first-reply identity given identical inputs; time order and duration ratio of
identical pairs, as a test for response caching).

Usage: ``python tools/analysis2/exam2_piguard2.py --corpus DIR --model MODEL --out REPORT.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from message_roles import is_assistant  # noqa: E402  (assistant + DTap agent: one shared grouping)

from agentprov.io.canonical import jcs_bytes


def h(x: object) -> str:
    return hashlib.sha256(jcs_bytes(x)).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    root = a.corpus.expanduser()
    rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
    arms: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for r in rows:
        lines = (root / r["paths"]["aer"]).read_bytes().split(b"\n")
        recs = [json.loads(x) for x in lines if x]
        agent = next((x for x in recs if x.get("k") == "actor" and x.get("kind") == "llm_agent"), {})
        if (agent.get("model") or {}).get("requested") != a.model:
            continue
        hdr = recs[0]
        t = hdr.get("task") or {}
        cell = (t.get("suite"), t.get("task_id"), t.get("attack_id"), t.get("attack_target_id"))
        run = next(x for x in recs if x.get("k") == "scope" and x.get("kind") == "run")
        msgs = [x for x in recs if x.get("k") == "message"]
        def strip(m: dict) -> list:
            return [m.get("role"), [{k: v for k, v in p.items() if k not in ("provider_call_id", "responds_to")} for p in m.get("parts") or []]]
        first_asst = next((m for m in msgs if is_assistant(m.get("role"))), None)
        arms[str(t.get("defense_id"))][cell] = {
            "ex": r["ex"],
            "sys": h(strip(msgs[0])) if msgs else None,
            "user": h(strip(msgs[1])) if len(msgs) > 1 else None,
            "a1": h(strip(first_asst)) if first_asst else None,
            "traj": h([strip(m) for m in msgs]),
            "n": len(msgs),
            "ts": ((run.get("t") or {}).get("raw") or {}).get("start"),
            "dur": (run.get("t") or {}).get("dur_s"),
            "redact": sum(1 for x in recs if x.get("k") == "decision"),
            "tools": sum(1 for m in msgs if m.get("role") == "tool"),
        }
    out: dict = {"model": a.model, "arms": {k: len(v) for k, v in arms.items()}, "pairs": {}}
    for d1, d2 in combinations(sorted(arms), 2):
        A, B = arms[d1], arms[d2]
        c: Counter = Counter()
        ratios: list[float] = []
        order = Counter()
        for cell in set(A) & set(B):
            x, y = A[cell], B[cell]
            c["cells"] += 1
            c[f"same_system={x['sys'] == y['sys']}"] += 1
            c[f"same_user={x['user'] == y['user']}"] += 1
            if x["n"] == 3 and y["n"] == 3:
                c["both_3msg"] += 1
                c[f"both_3msg_same_reply={x['a1'] == y['a1']}"] += 1
            if x["sys"] == y["sys"] and x["user"] == y["user"]:
                c[f"same_inputs_same_first_reply={x['a1'] == y['a1']}"] += 1
            if x["traj"] == y["traj"]:
                c["identical"] += 1
                if x["dur"] and y["dur"]:
                    first, second = (x, y) if (x["ts"] or "") <= (y["ts"] or "") else (y, x)
                    ratios.append(second["dur"] / first["dur"])
                    order[f"first={d1 if first is x else d2}"] += 1
        out["pairs"][f"{d1}|{d2}"] = {**dict(c), "identical_second_over_first_duration": {
            "n": len(ratios), "median": round(statistics.median(ratios), 3) if ratios else None,
            "share_below_0.5": round(sum(r < 0.5 for r in ratios) / len(ratios), 3) if ratios else None,
            "share_above_2": round(sum(r > 2 for r in ratios) / len(ratios), 3) if ratios else None}, "which_ran_first": dict(order)}
    spans = {}
    for d, cells in arms.items():
        ts = sorted(v["ts"] for v in cells.values() if v["ts"])
        spans[d] = [ts[0], ts[-1]] if ts else None
    out["timestamp_span_by_arm"] = spans
    a.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
