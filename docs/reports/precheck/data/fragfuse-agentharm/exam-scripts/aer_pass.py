# ruff: noqa  (precheck examiner script for fragfuse-agentharm; read-only analysis of a scratch corpus; counts only)
"""AER/SEM/PROV pass: outcomes per execution with container label, judgement names, evidence classes, seal issues,
account-path segments (kind, generic/named, 8-hex digest of the segment, pointer class; never the value), secret-like
shapes in AER strings (whole-string vs substring), artefact safety net.

Usage: python -I aer_pass.py <corpus> <out.json>
"""
from __future__ import annotations

import hashlib, json, os, re, sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "tools" / "precheck"))
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS, SECRET_PATTERNS  # noqa: E402
from agentprov.aer.reader import load_aer
from agentprov.artefacts import discover_catalogues, scan
from agentprov.sem.reader import load_sem

ROOT = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2])
CATS = tuple(discover_catalogues())
OPSEG = hashlib.sha256(Path.home().name.encode()).hexdigest()[:8]
_IDX = re.compile(r"/\d+(?=/|$)")


def d8(s): return hashlib.sha256(s.encode()).hexdigest()[:8]


def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{p}/{k if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,40}', str(k)) else '{k}'}")
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, p + "/*")
    elif isinstance(o, str):
        yield p, o


def acct(s):
    for kind, rx in ACCOUNT_PATTERNS.items():
        for m in rx.finditer(s):
            seg = m.group(1)
            yield kind, ("generic" if seg.lower() in GENERIC_ACCOUNTS else "named"), d8(seg)


def text_acct(stage, path, c, segs):
    t = path.read_text(errors="replace")
    for kind, gn, dg in acct(t):
        c[f"{stage}:{kind}:{gn}"] += 1
        segs[f"{stage}:{kind}:{gn}"].add(dg)
        if dg == OPSEG: c[f"{stage}:OPERATOR"] += 1


def one(row):
    c, ev, net, acc, sec = Counter(), Counter(), Counter(), Counter(), Counter()
    segs = defaultdict(set)
    aer = load_aer(ROOT / row["paths"]["aer"], verify=True)
    h, recs = aer.header, list(aer.records)
    task = h.get("task") or {}
    ext = (h.get("ext") or {}).get("inspect") or {}
    actors = {x["id"]: x for x in recs if x.get("k") == "actor"}
    model = (actors.get("agent", {}).get("model") or {}).get("requested")
    js = Counter(x.get("name") for x in recs if x.get("k") == "judgement")
    jv = {x.get("name"): x.get("value") for x in recs if x.get("k") == "judgement"}
    for x in [h, *recs]:
        ev[f"{x.get('k')}:{x.get('ev')}"] += 1
        for _, v in (x.get("evf") or {}).items():
            ev[f"evf:{v}"] += 1
        for p, s in walk(x):
            pc = f"{x.get('k')}:{p}"
            for kind, gn, dg in acct(s):
                acc[f"{kind}:{gn}|{pc}"] += 1
                segs[f"aer:{kind}:{gn}"].add(dg)
                if dg == OPSEG: acc["OPERATOR"] += 1
            for rule, rx in SECRET_PATTERNS.items():
                for m in rx.finditer(s):
                    sec[f"{rule}|{'whole' if m.group(0) == s.strip() else 'substring'}|{pc}"] += 1
    for iss in aer.seal.get("issues", ()):
        c[f"seal:{iss.get('code')}"] += 1
    sem_records = None
    for ref in (row["paths"].get("sem") or {}).values():
        sem_records = load_sem(ROOT / ref).records
        text_acct("sem", ROOT / ref, c, segs)
    for d in (row["paths"].get("prov") or {}).values():
        for ref in d.values():
            text_acct("prov", ROOT / ref, c, segs)
    for f in scan([*aer.records, aer.seal], CATS, sem_records=sem_records):
        net[f"{f.detector}#{f.variant}|{'classified' if f.classified else 'UNCLASSIFIED'}|{','.join(f.entries)}"] += f.n
    has_tool = any(x.get("k") == "tool_execution" for x in recs)
    return {"ex": row["ex"], "member": row["raw"][0]["sha256"], "model": model, "suite": task.get("suite"),
            "task_id": task.get("task_id"), "attack_id": task.get("attack_id"), "eval_id": ext.get("eval_id"),
            "task_args_d8": d8(json.dumps(ext.get("task_args"), sort_keys=True)),
            "score": jv.get("combined_scorer.score"), "refusal": jv.get("combined_scorer.refusal"),
            "judgements": dict(js), "status": row["status"], "completeness": row["completeness"], "tool": has_tool,
            "issues": row.get("issues", []),
            "agg": {"c": c, "ev": ev, "net": net, "acc": acc, "sec": sec},
            "segs": {k: sorted(v) for k, v in segs.items()}}


def main():
    rows = [json.loads(x) for x in (ROOT / "executions.jsonl").read_bytes().splitlines() if x]
    cont = {}
    for line in (ROOT / "raw" / "members.jsonl").read_bytes().splitlines():
        m = json.loads(line)
        if m.get("sha256"): cont[m["sha256"]] = m["container"]
    agg, segs, per = defaultdict(Counter), defaultdict(set), []
    acc_ex = Counter()
    with Pool(2) as pool:
        for r in pool.imap_unordered(one, rows, chunksize=8):
            for k, v in r.pop("agg").items():
                agg[k].update(v)
            for k, v in r.pop("segs").items():
                segs[k].update(v)
                acc_ex[k] += 1
            r["container"] = cont.get(r["member"])
            per.append(r)
    OUT.write_text(json.dumps({"n": len(rows), "agg": {k: dict(sorted(v.items())) for k, v in agg.items()},
                               "segments_distinct": {k: len(v) for k, v in sorted(segs.items())},
                               "segments_d8": {k: sorted(v) for k, v in sorted(segs.items())},
                               "executions_with": dict(sorted(acc_ex.items())),
                               "per_execution": sorted(per, key=lambda x: x["ex"])}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
