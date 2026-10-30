# ruff: noqa: B007, B905, UP031  (analysis script, committed as run; style-only)
"""Examination 2, S01 divergence test: where do two defence arms of one model first diverge? (read-only)

For every matched cell of two arms, find the first message index at which the message lists differ (provider call ids
ignored) and classify it: an assistant message after an identical context (model-side divergence: the model answered
differently to the same input), a tool message where exactly one side was rewritten by the defence (defence-side
divergence), another tool-message difference, or a length difference only. If, within a session, the model always
answers identically to identical context, every divergence is defence-side.

Usage: ``python tools/analysis2/exam2_piguard3.py --corpus DIR --model MODEL --out REPORT.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from message_roles import is_assistant  # noqa: E402  (assistant + DTap agent: one shared grouping)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    root = a.corpus.expanduser()
    arms: dict[str, dict[tuple, list]] = defaultdict(dict)
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
        msgs = []
        for m in recs:
            if m.get("k") == "message":
                parts = [{k: v for k, v in p.items() if k not in ("provider_call_id", "responds_to")} for p in m.get("parts") or []]
                msgs.append((m.get("role"), json.dumps(parts, sort_keys=True), str(m.get("actor", "")).startswith("def")))
        arms[str(t.get("defense_id"))][cell] = msgs
    out: dict = {"model": a.model, "pairs": {}}
    for d1, d2 in combinations(sorted(arms), 2):
        c: Counter = Counter()
        for cell in set(arms[d1]) & set(arms[d2]):
            A, B = arms[d1][cell], arms[d2][cell]
            i = next((k for k, (x, y) in enumerate(zip(A, B)) if x[:2] != y[:2]), None)
            if i is None:
                c["identical" if len(A) == len(B) else "prefix_only_length_differs"] += 1
                continue
            ra, rb = A[i][0], B[i][0]
            if ra != rb:
                c["diverge_role_mismatch"] += 1
            elif is_assistant(ra):
                c["diverge_assistant_after_identical_context"] += 1
            elif ra == "tool":
                if A[i][2] != B[i][2]:
                    c["diverge_tool_one_side_rewritten_by_defence"] += 1
                else:
                    c["diverge_tool_other"] += 1
            else:
                c[f"diverge_{ra}"] += 1
        out["pairs"][f"{d1}|{d2}"] = dict(c)
    a.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
