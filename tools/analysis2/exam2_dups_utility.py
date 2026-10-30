"""Examination 2: inside identical-trajectory groups (first-analysis extractor rows), does *utility* differ for the same
user task? (Security legitimately differs across injection tasks and for benign members; utility of the same user task
on the same message list should not.) Counts and ex ids only.

Usage: ``python tools/analysis2/exam2_dups_utility.py FEATURES.jsonl [...]``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict


def val(r: dict, name: str):
    return next((j["value"] for j in r.get("judgements") or () if j["name"] == name and not j.get("revises")), None)


def main() -> int:
    out = {}
    for path in sys.argv[1:]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("traj_digest"):
                groups[r["traj_digest"]].append(r)
        c: Counter = Counter()
        ex = []
        for g in groups.values():
            if len(g) < 2:
                continue
            c["groups"] += 1
            by_task: dict[str, set] = defaultdict(set)
            for r in g:
                by_task[str(r.get("task_id"))].add(str(val(r, "utility")))
            if any(len(v) > 1 for v in by_task.values()):
                c["utility_differs_same_user_task"] += 1
                if len(ex) < 5:
                    ex.append(sorted(r["ex"] for r in g)[:2])
            if len({str(r.get("task_id")) for r in g}) > 1:
                c["different_user_tasks_in_group"] += 1
        out[path.rsplit("/", 1)[-1]] = {"counts": dict(c), "examples": ex}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
