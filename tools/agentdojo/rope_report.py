"""ROPE-specific counts of a working corpus imported with the ``rope`` profile (D.6.13; DoD Q.8; HON-10).

    uv run python tools/agentdojo/rope_report.py --corpus DIR.partial --out REPORT.json

Reads only the corpus's sealed AERs (AgentPROV-format output) and writes counts and identifiers; never source text:

* Q.8: per correction rule (slack IT5, dailylife IT7, github IT1) and attack, the logs it applies to, their recorded and
  recomputed ``security`` values, and how many recomputed values differ; every recomputed judgement is checked to sit
  beside a recorded one (``revises`` an existing ``security`` judgement without ``revises``, which keeps its value);
* the AutoDojo slice: logs per (model, suite), linked slots and their forms, the per-file ambiguity-set sizes, and the
  intersection of the sets over each (model, suite) arm (the investigation's 1, 8, 40 or 50 cells), with the raw
  versus effective (recomputed where present) ``security`` successes that the AutoDojo and ROPE papers report;
* guard denials by query-echo variant, identity conflicts, release arms, units, issues.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def _ext(record: dict[str, Any], ns: str) -> dict[str, Any]:
    value = (record.get("ext") or {}).get(ns)
    return value if isinstance(value, dict) else {}


def report(corpus: Path) -> dict[str, Any]:
    files = sorted((corpus / "aer").rglob("*.aer.jsonl"))
    q8: dict[str, Counter[str]] = defaultdict(Counter)
    beside_violations: list[str] = []
    arms: dict[tuple[str, str], set[str] | None] = {}
    slice_files: Counter[str] = Counter()
    sizes: Counter[int] = Counter()
    slots: Counter[str] = Counter()
    security: Counter[str] = Counter()
    denials: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    trees: Counter[str] = Counter()
    units: Counter[str] = Counter()
    for path in files:
        recs = _records(path)
        header, seal = recs[0], recs[-1]
        units[str(header.get("unit"))] += 1
        issues.update({str(i.get("code")) for i in seal.get("issues", ())})
        task = header.get("task") or {}
        attack = str(task.get("attack_id"))
        arm = _ext(header, "rope").get("arm")
        trees[arm["tree"] if isinstance(arm, dict) else "main"] += 1
        by_id = {r.get("id"): r for r in recs}
        for r in recs:
            if r.get("k") == "decision" and "query_echo" in _ext(r, "rope"):
                denials[_ext(r, "rope")["query_echo"]] += 1
        judgements = [r for r in recs if r.get("k") == "judgement"]
        recorded = next((j for j in judgements if j.get("name") == "security" and "revises" not in j), None)
        recomputed = [j for j in judgements if j.get("origin") == "recomputed"]
        for j in recomputed:
            label = str(_ext(j, "rope").get("correction"))
            base = by_id.get(j.get("revises"))
            if base is None or base.get("name") != "security" or "revises" in base or base is not recorded:
                beside_violations.append(header["ex"])
                continue
            key = f"{label}|{attack}"
            q8[key]["logs"] += 1
            q8[key]["recorded_true"] += base.get("value") is True
            q8[key]["recomputed_true"] += j.get("value") is True
            q8[key]["changed"] += base.get("value") is not j.get("value")
        if attack == "autodojo":
            model = str(((by_id.get("agent") or {}).get("model") or {}).get("requested"))
            suite = str(task.get("suite"))
            slice_files[f"{model}/{suite}"] += 1
            cells = _ext(header, "autodojo").get("cache_cells")
            sizes[len(cells) if isinstance(cells, list) else 0] += 1
            key2 = (model, suite)
            current = set(cells) if isinstance(cells, list) else set()
            arms[key2] = current if key2 not in arms else (arms[key2] or set()) & current
            for r in recs:
                if r.get("k") == "fixture":
                    slots[str(_ext(r, "autodojo").get("cache_match", "unlinked"))] += 1
            if recorded is not None:
                security["recorded_true"] += recorded.get("value") is True
                newer = next((j for j in recomputed if j.get("revises") == recorded.get("id")), None)
                security["effective_true"] += (newer if newer is not None else recorded).get("value") is True
    totals: Counter[str] = Counter()
    for key, counts in q8.items():
        label = key.split("|", 1)[0]
        for name, value in counts.items():
            totals[f"{label}.{name}"] += value
    return {
        "aer_files": len(files),
        "units": dict(sorted(units.items())),
        "files_by_issue_code": dict(sorted(issues.items())),
        "release_trees": dict(sorted(trees.items())),
        "guard_denials": {"total": sum(denials.values()), **dict(sorted(denials.items()))},
        "q8_corrections": {
            "by_rule_and_attack": {k: dict(sorted(v.items())) for k, v in sorted(q8.items())},
            "by_rule": dict(sorted(totals.items())),
            "recomputed_not_beside_a_recorded_security": len(beside_violations),
        },
        "autodojo_slice": {
            "logs": sum(slice_files.values()),
            "logs_by_model_suite": dict(sorted(slice_files.items())),
            "slots_by_form": dict(sorted(slots.items())),
            "files_by_ambiguity_set_size": {str(k): v for k, v in sorted(sizes.items())},
            "arm_intersection_size": {f"{m}/{s}": len(v or ()) for (m, s), v in sorted(arms.items())},
            "security_true": dict(sorted(security.items())),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    data = report(args.corpus)
    args.out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: data[k] for k in ("aer_files", "units", "guard_denials")}, sort_keys=True))
    return 0 if not data["q8_corrections"]["recomputed_not_beside_a_recorded_security"] else 1


if __name__ == "__main__":
    sys.exit(main())
