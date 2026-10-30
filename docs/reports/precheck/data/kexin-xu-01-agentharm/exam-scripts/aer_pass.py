# ruff: noqa  (precheck examiner script for kexin-xu-01-agentharm; read-only over a scratch corpus; counts and sha8 only)
"""Per-container mapped outcomes (AER judgements) for the L2 mapping check, judge/agent identity, record status counts,
and an account-segment census of AER/SEM/PROV files (named segments as sha256[:8], never names).
Usage: uv run python -I aer_pass.py <repo-root> <scratch corpus> <out.json>"""
import hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "tools/precheck"))
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS  # noqa: E402
C = Path(sys.argv[2]).expanduser(); OUT = Path(sys.argv[3])
sha8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
per = defaultdict(lambda: {"n": 0, "scored": 0, "refused": 0, "score_sum": 0.0, "status": Counter(), "completeness": Counter()})
ident = Counter(); rec = Counter(); acct = defaultdict(lambda: {"files": Counter(), "kind": None, "class": None})
def scan(path, layer):
    t = path.read_text("utf-8")
    for kind, rx in ACCOUNT_PATTERNS.items():
        for m in rx.finditer(t):
            a = m.group(1); cl = "generic" if a.lower() in GENERIC_ACCOUNTS else "named"
            d = acct[f"{cl}:{sha8(a)}"]; d["files"][layer] += 1; d["kind"] = kind; d["class"] = cl
for line in (C / "executions.jsonl").read_text().splitlines():
    r = json.loads(line); key = r["source_key"].split("#")[0].split(":", 1)[1]
    p = per[key]; p["n"] += 1; p["status"][r["status"]] += 1; p["completeness"][r["completeness"]] += 1
    recs = [json.loads(x) for x in (C / r["paths"]["aer"]).read_text().splitlines() if x]
    js = {x.get("name"): x.get("value") for x in recs if x.get("k") == "judgement"}
    if "combined_scorer.score" in js:
        p["scored"] += 1; p["score_sum"] += float(js["combined_scorer.score"]); p["refused"] += int(js.get("combined_scorer.refusal") == 1)
    for x in recs:
        if x.get("k") == "actor":
            ident[f"actor:{x.get('id')}:{x.get('kind')}:{((x.get('model') or {}).get('requested'))}"] += 1
        if x.get("k") in ("tool_execution", "model_call"): rec[f"{x['k']}:status={x.get('status')}"] += 1
        if x.get("k") == "execution": ident[f"bench={x['task'].get('benchmark')}|suite={x['task'].get('suite')}"] += 1
    scan(C / r["paths"]["aer"], "aer")
    for v in (r["paths"].get("sem") or {}).values(): scan(C / v, "sem")
    for v in (r["paths"].get("prov") or {}).values():
        for f in v.values(): scan(C / f, "prov")
out = {"per_container": {k[:12]: {**v, "mean": round(v["score_sum"] / v["scored"], 4) if v["scored"] else None,
                                  "status": dict(v["status"]), "completeness": dict(v["completeness"])} for k, v in per.items()},
       "identity": dict(ident), "records": dict(rec),
       "account_segments": {k: {"kind": v["kind"], "class": v["class"], "files": dict(v["files"])} for k, v in acct.items()}}
OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n"); print(len(per), len(acct))
