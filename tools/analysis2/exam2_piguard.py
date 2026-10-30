# ruff: noqa: B007, B905, UP031  (analysis script, committed as run; style-only)
"""Examination 2, S01: identical trajectories across defences of one model in AgentDyn (read-only).

For every model and every pair of its defence arms, executions are matched on the cell (suite, user task, attack,
injection task). A pair is "identical" when the message lists are equal after dropping provider call ids (roles, text,
tool-call names and arguments, tool results and errors; JCS comparison). For identical and non-identical pairs it
records whether the run timestamp, the duration, the raw object, the git blob and the origin commit agree, how many
defence decisions (and of which verdict) each run holds, whether a payload was visible (SEM injection marker
`present`), and whether utility/security agree.

Output: a JSON report of counts and a few example ex-id pairs. No source text.

Usage: ``python tools/analysis2/exam2_piguard.py --corpus DIR --out REPORT.json [--jobs 4]``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from agentprov.io.canonical import jcs_bytes

_ROOT: Path | None = None


def _init(root: str) -> None:
    global _ROOT
    _ROOT = Path(root)


def facts(row: dict[str, Any]) -> dict[str, Any]:
    assert _ROOT is not None
    lines = (_ROOT / row["paths"]["aer"]).read_bytes().split(b"\n")
    f: dict[str, Any] = {"ex": row["ex"]}
    msgs = []
    decisions: Counter = Counter()
    redacted_msgs = 0
    judg = {}
    for line in lines:
        if not line:
            continue
        r = json.loads(line)
        k = r.get("k")
        if k == "execution":
            t = r.get("task") or {}
            f["cell"] = [t.get("suite"), t.get("task_id"), t.get("attack_id"), t.get("attack_target_id")]
            f["defence"] = t.get("defense_id")
            a = (r.get("artifacts") or [{}])[0]
            f["raw"] = a.get("sha256")
            o = a.get("origin") or {}
            f["blob"] = o.get("blob_sha1")
            f["commit"] = o.get("commit")
            f["pipeline"] = ((r.get("ext") or {}).get("agentdojo") or {}).get("pipeline_name")
        elif k == "actor" and r.get("kind") == "llm_agent":
            f["model"] = (r.get("model") or {}).get("requested")
        elif k == "scope" and r.get("kind") == "run":
            t = r.get("t") or {}
            f["ts"] = (t.get("raw") or {}).get("start") or t.get("start_naive")
            f["dur"] = t.get("dur_s")
        elif k == "message":
            parts = []
            for p in r.get("parts") or []:
                q = {kk: vv for kk, vv in p.items() if kk not in ("provider_call_id", "responds_to")}
                parts.append(q)
            msgs.append([r.get("role"), parts])
            if r.get("role") == "tool" and str(r.get("actor", "")).startswith("def"):
                redacted_msgs += 1
        elif k == "decision":
            decisions[str(r.get("verdict"))] += 1
        elif k == "judgement":
            judg[r.get("name")] = r.get("value")
    f["traj"] = hashlib.sha256(jcs_bytes(msgs)).hexdigest()[:20]
    f["n_msgs"] = len(msgs)
    f["decisions"] = dict(decisions)
    f["redacted_tool_msgs"] = redacted_msgs
    f["judg"] = judg
    present = 0
    for ref, p in (row["paths"].get("sem") or {}).items():
        for line in (_ROOT / p).read_bytes().split(b"\n"):
            if b'"injection_marker"' in line:
                r = json.loads(line)
                if (r.get("value") or {}).get("status") == "present":
                    present += 1
    f["present_markers"] = present
    return f


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {
        "same_ts": a.get("ts") == b.get("ts"),
        "same_dur": a.get("dur") == b.get("dur"),
        "same_raw": a.get("raw") == b.get("raw"),
        "same_blob": a.get("blob") == b.get("blob"),
        "same_commit": a.get("commit") == b.get("commit"),
        "dec_a": sum(a["decisions"].values()),
        "dec_b": sum(b["decisions"].values()),
        "present_a": a["present_markers"] > 0,
        "present_b": b["present_markers"] > 0,
        "same_judg": a["judg"] == b["judg"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    root = Path(a.corpus).expanduser()
    rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
    rows.sort(key=lambda r: r["ex"])
    with Pool(a.jobs, initializer=_init, initargs=(str(root),)) as pool:
        fs = list(pool.imap(facts, rows, chunksize=64))
    by: dict[tuple, dict[str, dict]] = defaultdict(dict)  # (model, cell) -> defence -> facts
    dup_cells = 0
    for f in fs:
        key = (f.get("model"), tuple(f.get("cell") or ()))
        d = str(f.get("defence"))
        if d in by[key]:
            dup_cells += 1
        by[key][d] = f
    pairs: dict[str, dict[str, Any]] = {}
    for (model, _cell), arms in by.items():
        for d1, d2 in combinations(sorted(arms), 2):
            name = f"{model}|{d1}|{d2}"
            st = pairs.setdefault(name, {"cells": 0, "identical": 0, "id": Counter(), "nonid": Counter(),
                                        "id_len": Counter(), "examples": [], "id_dec": Counter()})
            fa, fb = arms[d1], arms[d2]
            st["cells"] += 1
            cmp = compare(fa, fb)
            same = fa["traj"] == fb["traj"]
            bucket = st["id"] if same else st["nonid"]
            for k, v in cmp.items():
                if isinstance(v, bool):
                    bucket[f"{k}={v}"] += 1
            if same:
                st["identical"] += 1
                st["id_len"][fa["n_msgs"]] += 1
                st["id_dec"][f"a{min(cmp['dec_a'], 3)}_b{min(cmp['dec_b'], 3)}"] += 1
                if len(st["examples"]) < 3 and fa["n_msgs"] >= 9:
                    st["examples"].append([fa["ex"], fb["ex"], fa["n_msgs"]])
    # same-arm determinism baseline: none
    out = {"executions": len(fs), "duplicate_model_cell_defence": dup_cells, "pairs": {}}
    for name, st in sorted(pairs.items()):
        out["pairs"][name] = {"cells": st["cells"], "identical": st["identical"],
                              "identical_flags": dict(st["id"]), "nonidentical_flags": dict(st["nonid"]),
                              "identical_lengths": dict(sorted(st["id_len"].items())),
                              "identical_decisions": dict(st["id_dec"]), "examples": st["examples"]}
    # per-arm summary
    arm: dict[str, Counter] = defaultdict(Counter)
    for f in fs:
        k = f"{f.get('model')}|{f.get('defence')}"
        arm[k]["runs"] += 1
        arm[k]["with_decision"] += int(bool(f["decisions"]))
        arm[k]["with_present_marker"] += int(f["present_markers"] > 0)
        for v, n in f["decisions"].items():
            arm[k][f"decisions_{v}"] += n
    out["arms"] = {k: dict(v) for k, v in sorted(arm.items())}
    ts = Counter(f.get("ts") for f in fs)
    out["timestamps_shared_by_more_than_one_run"] = sum(1 for v in ts.values() if v > 1)
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
