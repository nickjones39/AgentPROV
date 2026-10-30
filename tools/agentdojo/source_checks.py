"""Cross-checks of the Mandate and survey-runs corpora against the investigation's figures (docs/architecture D.6.15; phase 10).

    uv run python tools/agentdojo/source_checks.py --source mandate --corpus DIR.partial [--out CHECKS.json]
    uv run python tools/agentdojo/source_checks.py --source survey  --corpus DIR.partial [--out CHECKS.json]

Reads only AgentPROV-format files of a working corpus (``executions.jsonl`` and the AERs it lists) and prints numbers, never
source text. Each check pairs a figure measured from the AERs with the figure the investigation (``sources/`` and
``verify/`` reports of the research workspace) derived from the raw logs by its own scripts, so that agreement is an
independent test of the whole import path, not of the census alone.

* ``mandate``: the outcome table of verify/mandate-agentdojo-eval.md §3.4 (per pipeline and attack: runs, security True,
  utility True, decline messages), the decline and derived-allow counts by mode (49 / 191 and 6 / 137), the 5 tool-free
  runs, the message totals of §2, and the facts of the decline rows (every decline cites the decline rule, has no
  execution, is the error verbatim, and calls a tool the mode gates).
* ``survey``: the aggregates of verify/agent-security-tools-survey.md §2.4 (benign utility, utility under attack, mean
  security over the 949 attack pairs, solvability, per model), the message totals of §2.3, the 11 run errors (all
  gpt-oss) and the 48 iteration-capped traces per model.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

GATED = {
    "mandate_envelope": {"send_money", "schedule_transaction", "update_scheduled_transaction"},
    "mandate_scoped": {"send_money", "schedule_transaction", "update_scheduled_transaction", "update_password", "update_user_info"},
    "mandate_intent": {"send_money", "schedule_transaction", "update_scheduled_transaction", "update_password", "update_user_info"},
}


def _aers(corpus: Path) -> list[list[dict[str, Any]]]:
    out = []
    for line in (corpus / "executions.jsonl").read_bytes().splitlines():
        row = json.loads(line)
        out.append([json.loads(x) for x in (corpus / row["paths"]["aer"]).read_bytes().splitlines() if x.strip()])
    return out


def _judgement(records: list[dict[str, Any]], name: str) -> Any:
    return next((r["value"] for r in records if r.get("k") == "judgement" and r.get("name") == name), None)


def _pair(measured: Any, investigation: Any) -> dict[str, Any]:
    return {"measured": measured, "investigation": investigation, "equal": measured == investigation}


def mandate(aers: list[list[dict[str, Any]]]) -> dict[str, Any]:
    cells: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    declines_by_mode: Counter[str] = Counter()
    allows_by_mode: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    tool_free = violations = declines = 0
    for records in aers:
        header = records[0]
        defence = header["task"].get("defense_id")
        attack = header["task"].get("attack_id") or "none"
        key = f"{defence or 'baseline'} / {attack}"
        cell = cells[key]
        cell[0] += 1
        cell[1] += int(_judgement(records, "security") is True)
        cell[2] += int(_judgement(records, "utility") is True)
        calls = {f"{r['id']}#{k}": p for r in records if r.get("k") == "message" and r.get("role") == "assistant"
                 for k, p in enumerate(r.get("parts", ())) if p.get("t") == "tool_call"}
        executions = [r for r in records if r.get("k") == "tool_execution"]
        tool_free += int(not executions and not any(r.get("k") == "decision" for r in records))
        for r in records:
            if r.get("k") == "message":
                roles[str(r["role"])] += 1
            if r.get("k") == "decision":
                declines += 1
                cell[3] += 1
                declines_by_mode[str(defence)] += 1
                part = calls.get(r["subject"], {})
                bad = (r["verdict"] != "deny" or r["rule"][0] != "mandate.decline_prefix@1" or not str(r.get("reason", "")).startswith("MANDATE_DECLINE:")
                       or part.get("name") not in GATED.get(str(defence), set())
                       or any(e.get("call") == r["subject"] for e in executions))
                violations += int(bad)
        for e in executions:
            if "mandate" in (e.get("ext") or {}):
                allows_by_mode[str(defence)] += 1
    table = {k: {"runs": v[0], "security_true": v[1], "utility_true": v[2], "declines": v[3]} for k, v in sorted(cells.items())}
    expected = {  # verify/mandate-agentdojo-eval.md §3.4 (the README's headline rows are among them)
        "baseline / important_instructions": (144, 108, 118, 0), "baseline / tool_knowledge": (27, 19, 18, 0),
        "baseline / none": (9, 9, 9, 0), "mandate_envelope / important_instructions": (27, 3, 8, 39),
        "mandate_envelope / none": (9, 9, 1, 10), "mandate_intent / important_instructions": (144, 2, 99, 144),
        "mandate_intent / tool_knowledge": (27, 0, 9, 38), "mandate_intent / none": (9, 9, 9, 9),
    }
    got = {k: (v["runs"], v["security_true"], v["utility_true"], v["declines"]) for k, v in table.items()}
    return {
        "outcome_table": {"cells": table, **_pair(got, expected)},
        "declines": _pair(declines, 240),
        "declines_by_mode": _pair(dict(declines_by_mode), {"mandate_envelope": 49, "mandate_intent": 191}),
        "inferred_allows_by_mode": _pair(dict(allows_by_mode), {"mandate_envelope": 6, "mandate_intent": 137}),
        "tool_free_runs": _pair(tool_free, 5),
        "message_roles": _pair(dict(roles), {"assistant": 1621, "system": 396, "tool": 1390, "user": 396}),
        "decline_rows_violating_the_row_facts": _pair(violations, 0),
    }


def survey(aers: list[list[dict[str, Any]]]) -> dict[str, Any]:
    per: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    roles: Counter[str] = Counter()
    calls = 0
    errors: Counter[str] = Counter()
    capped: Counter[str] = Counter()
    for records in aers:
        header = records[0]
        agent = next(r for r in records if r.get("id") == "agent")
        model = agent["model"]["requested"]
        task, attack = header["task"]["task_id"], header["task"].get("attack_id")
        kind = "attack" if attack else ("solvability" if task.startswith("injection_task_") else "benign")
        bucket = per[model]
        bucket[f"{kind}_utility"][0] += int(_judgement(records, "utility") is True)
        bucket[f"{kind}_utility"][1] += 1
        if kind == "attack":
            bucket["attack_security"][0] += int(_judgement(records, "security") is True)
            bucket["attack_security"][1] += 1
        if (header.get("ext") or {}).get("agentdojo", {}).get("error"):
            errors[model] += 1
        if any(i.get("code") == "unexecuted_tool_call" for i in records[-1].get("issues", ())):
            capped[model] += 1
        for r in records:
            if r.get("k") == "message":
                roles[str(r["role"])] += 1
                calls += sum(1 for p in r.get("parts", ()) if p.get("t") == "tool_call")
    def pct(pair: list[int]) -> float:
        return round(100.0 * pair[0] / pair[1], 1)
    rates = {m: {"benign_utility": pct(b["benign_utility"]), "attack_utility": pct(b["attack_utility"]),
                 "attack_security": pct(b["attack_security"]), "solvability_utility": pct(b["solvability_utility"]),
                 "n": [b["benign_utility"][1], b["attack_utility"][1], b["solvability_utility"][1]]} for m, b in sorted(per.items())}
    expected = {  # verify/agent-security-tools-survey.md §2.4: benign / under attack / mean security / solvability
        "gpt-oss:120b": {"benign_utility": 67.0, "attack_utility": 54.9, "attack_security": 27.0, "solvability_utility": 68.6, "n": [97, 949, 35]},
        "qwen3-coder:30b": {"benign_utility": 57.7, "attack_utility": 36.6, "attack_security": 21.9, "solvability_utility": 60.0, "n": [97, 949, 35]},
        "qwen3:14b": {"benign_utility": 69.1, "attack_utility": 52.8, "attack_security": 17.6, "solvability_utility": 62.9, "n": [97, 949, 35]},
    }
    return {
        "aggregates_per_model": _pair(rates, expected),
        "message_roles": _pair(dict(roles), {"assistant": 13599, "system": 3243, "tool": 11237, "user": 3243}),
        "tool_calls": _pair(calls, 11286),
        "run_errors_per_model": _pair(dict(errors), {"gpt-oss:120b": 11}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=("mandate", "survey"), required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    aers = _aers(args.corpus)
    report = {"source": args.source, "executions": len(aers), "checks": (mandate if args.source == "mandate" else survey)(aers)}
    equal = all(c["equal"] for c in report["checks"].values() if isinstance(c, dict) and "equal" in c)
    report["all_equal"] = equal
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    print(json.dumps({"executions": len(aers), "all_equal": equal,
                      "unequal": [k for k, c in report["checks"].items() if isinstance(c, dict) and not c.get("equal", True)]}))
    return 0 if equal else 1


if __name__ == "__main__":
    sys.exit(main())
