"""Identical-trajectory groups across files (from ``phase10_extract.py`` rows): what differs inside each group.

A group is a set of executions whose message lists (roles and parts, JCS) are identical. For each group the tool reports
which labels differ (model, attack, injection task, user task, defence) and whether utility or security differ; a
utility difference inside a group with the same user task means the same recorded trajectory was scored differently.

Usage: ``python tools/analysis/phase10_dups.py FEATURES.jsonl [...]``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict


def val(r: dict, name: str):
    return next((j["value"] for j in r.get("judgements") or () if j["name"] == name and not j["revises"]), None)


def main() -> int:
    for path in sys.argv[1:]:
        rows = [json.loads(line) for line in open(path, encoding="utf-8")]
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if r.get("traj_digest"):
                groups[r["traj_digest"]].append(r)
        dup = [g for g in groups.values() if len(g) > 1]
        stats: Counter[str] = Counter()
        ex_util: list[list[str]] = []
        for g in dup:
            labels = tuple(k for k in ("model", "attack", "target", "task_id", "suite", "defence", "rope_arm")
                           if len({str(r.get(k)) for r in g}) > 1)
            stats["labels_differ:" + ",".join(labels)] += 1
            attacked = [r for r in g if r.get("attack")]
            stats["with_benign_member"] += any(not r.get("attack") for r in g)
            stats["marker_present_any"] += any(r.get("sem_marker_present_msgs", 0) for r in g)
            stats["n_fixtures_nonempty_any"] += any(r.get("n_fixtures_nonempty") for r in g)
            if len({str(val(r, "utility")) for r in g}) > 1:
                stats["utility_differs"] += 1
                if len(ex_util) < 5:
                    ex_util.append(sorted(r["ex"] for r in g)[:2])
            if len({str(val(r, "security")) for r in attacked}) > 1:
                stats["security_differs_among_attacked"] += 1
            if any(val(r, "security") is True for r in attacked):
                stats["some_attacked_member_security_true"] += 1
        print(json.dumps({"file": path, "groups": len(dup), "executions": sum(len(g) for g in dup),
                          "stats": dict(sorted(stats.items())), "utility_differs_examples": ex_util}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
