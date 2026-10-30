# ruff: noqa  (precheck examiner script for ast-survey-agentharm, committed as run; read-only analysis)
"""AER pass over a corpus: outcomes per arm, A2 classes, evidence classes, identity, safety net. Counts only.

Usage: python aer_pass.py <corpus> <out.json>
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

from agentprov.aer.reader import load_aer
from agentprov.artefacts import discover_catalogues, scan
from agentprov.sem.reader import load_sem

ROOT = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2])
CATS = tuple(discover_catalogues())


def one(row):
    r = {"c": Counter(), "ev": Counter(), "unk": Counter(), "net": Counter(), "net_ex": Counter(), "ident": Counter()}
    aer = load_aer(ROOT / row["paths"]["aer"], verify=True)
    recs = list(aer.records)
    h = aer.header
    task = h.get("task") or {}
    actors = {x["id"]: x for x in recs if x.get("k") == "actor"}
    model = (actors.get("agent", {}).get("model") or {}).get("requested")
    suite = task.get("suite") or task.get("benchmark")
    r["ident"][f"agent_model={model}"] += 1
    r["ident"][f"task.suite={task.get('suite')}"] += 1
    r["ident"][f"task.benchmark={task.get('benchmark')}"] += 1
    r["ident"][f"defence={task.get('defense_id')}|attack={task.get('attack_id')}"] += 1
    for aid, a in actors.items():
        r["ident"][f"actor:{aid}:{a.get('kind')}:model={(a.get('model') or {}).get('requested')}:version={a.get('version')}"] += 1
    split = "benign" if "benign" in json.dumps(task.get("task_id", "")) + json.dumps(h.get("ext", {}).get("inspect", {}).get("task", "")) else None
    js = {x.get("name"): x.get("value") for x in recs if x.get("k") == "judgement"}
    sample_id = ((h.get("ext") or {}).get("inspect") or {}).get("sample_metadata", {}).get("id")
    for x in [h, *recs]:
        r["ev"][f"{x.get('k')}:{x.get('ev')}"] += 1
        for p, v in (x.get("evf") or {}).items():
            r["ev"][f"evf:{v}"] += 1
        for p, v in (x.get("unk") or {}).items():
            r["unk"][f"{x.get('k')}:{p}:{v}"] += 1
        if x.get("k") == "model_call":
            r["c"][f"model_call:{x.get('role')}:finish={x.get('finish_reason')}:status={x.get('status')}"] += 1
        if x.get("k") == "tool_execution":
            r["c"][f"tool_execution:status={x.get('status')}"] += 1
            if x.get("error"):
                r["c"]["tool_execution:error_present"] += 1
    for iss in aer.seal.get("issues", ()):
        r["c"][f"seal_issue:{iss.get('code')}:{iss.get('severity')}"] += 1
    sem_refs = row["paths"].get("sem") or {}
    sem_records = None
    if sem_refs:
        sem = load_sem(ROOT / next(iter(sem_refs.values())))
        sem_records = sem.records
        for s in sem.records[1:]:
            if s.get("k") == "ann":
                r["c"][f"sem_ann:{s.get('type')}:{s.get('ev')}"] += 1
            elif s.get("k") == "claim" or "claim" in str(s.get("k")):
                r["c"][f"sem_claim:{s.get('type') or s.get('name')}"] += 1
    for f in scan([*aer.records, aer.seal], CATS, sem_records=sem_records):
        key = f"{f.detector}#{f.variant}|{'classified' if f.classified else 'UNCLASSIFIED'}|{','.join(f.entries)}"
        r["net"][key] += f.n
        r["net_ex"][key] += 1
    return {"ex": row["ex"], "model": model, "task_id": task.get("task_id"), "suite": suite, "sample_id": sample_id,
            "score": js.get("combined_scorer.score"), "refusal": js.get("combined_scorer.refusal"),
            "judgement_names": sorted(js), "parts": {k: dict(v) for k, v in r.items()}}


def main():
    rows = [json.loads(x) for x in (ROOT / "executions.jsonl").read_bytes().splitlines() if x]
    agg = defaultdict(Counter)
    per = []
    with Pool(2) as pool:
        for res in pool.imap_unordered(one, rows, chunksize=16):
            for k, v in res["parts"].items():
                agg[k].update(v)
            per.append({k: res[k] for k in ("ex", "model", "task_id", "suite", "sample_id", "score", "refusal", "judgement_names")})
    OUT.write_text(json.dumps({"n": len(rows), "agg": {k: dict(sorted(v.items())) for k, v in agg.items()},
                               "per_execution": sorted(per, key=lambda x: x["ex"])}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
