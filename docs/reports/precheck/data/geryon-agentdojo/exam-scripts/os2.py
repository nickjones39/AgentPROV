"""OS-2 on the j2 sample: mapped AER run judgements vs raw L1 outcomes of the same labels; denials (decision records)
vs the raw denial count of the same label; tool executions vs raw tool messages; sample rates per log-set class with
Wilson 95%. Counts only. Usage: os2.py pop.json OUT.json"""
import sys, json
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, __import__("os").getcwd() + "/tools/analysis2")  # run from the repository root
from exam2_lib import wilson
W = Path.home() / ".agentprov/migration-work/precheck/geryon-agentdojo"
C = W / "l2-head-j2.partial"
L1 = {json.loads(l)["sha256"]: json.loads(l) for l in open(W / "l1-units-head.jsonl")}
POP = {r["label"]: r for r in json.load(open(sys.argv[1]))}
comp = Counter(); mism = Counter(); origin = Counter(); den = Counter(); arms = defaultdict(Counter); dec_by = Counter()
for line in open(C / "executions.jsonl"):
    r = json.loads(line)
    u = L1[r["raw"][0]["sha256"].split(":", 1)[1]]
    p = POP[u["label"]]
    recs = [json.loads(x) for x in open(C / r["paths"]["aer"])]
    j = {x["name"]: x for x in recs if x["k"] == "judgement" and x.get("subject") == "run"}
    for name in ("utility", "security"):
        comp[name] += 1
        raw, got = u["outcomes"].get(name), (j.get(name) or {}).get("value")
        if raw != got:
            mism[f"{name}|raw={json.dumps(raw)}|aer={json.dumps(got)}"] += 1
        if name in j:
            origin[f"{name}|{p['kind']}|" + ",".join(sorted(x.split('#')[0] for x in j[name].get("rule") or []))] += 1
    decs = [x for x in recs if x["k"] == "decision"]
    nd = sum(1 for x in decs if any("defence_denial_message" in str(y) for y in x.get("rule") or []))
    den["raw_denials"] += p["denials"] + p["denials_dotall_only"]; den["aer_denial_decisions"] += nd
    den["executions_denials_equal"] += (nd == p["denials"] + p["denials_dotall_only"])
    for x in decs:
        dec_by[f"{x.get('verdict')}|cond={p['cond']}|ev={x.get('ev')}"] += 1
    te = sum(1 for x in recs if x["k"] == "tool_execution")
    den["aer_tool_executions"] += te
    den["raw_tool_messages_minus_denials"] += sum(1 for _ in [0]) * 0
    # sample arms: (run_set class, condition, suite) on attacked logs
    if p["kind"] == "user":
        a = f"{p['run_set']}|{p['suite']}|{p['cond']}"
        arms[a]["n"] += 1; arms[a]["asr"] += (j.get("security") or {}).get("value") is True
        arms[a]["util"] += (j.get("utility") or {}).get("value") is True
        b = f"{p['model']}|{'progent' if p['cond']=='B' else 'none'}"
        arms["model_defence:" + b]["n"] += 1; arms["model_defence:" + b]["asr"] += (j.get("security") or {}).get("value") is True
        arms["model_defence:" + b]["util"] += (j.get("utility") or {}).get("value") is True
def wr(k, n):
    lo, hi = wilson(k, n); return {"k": k, "n": n, "pct": round(100 * k / n, 2), "wilson95": [round(100 * lo, 2), round(100 * hi, 2)]}
OUT = {"compared": dict(comp), "raw_vs_mapped_mismatches": dict(mism), "judgement_origin_rules": dict(sorted(origin.items())),
       "denials": dict(den), "decisions": dict(dec_by),
       "sample_arms": {a: {"asr": wr(c["asr"], c["n"]), "utility": wr(c["util"], c["n"])} for a, c in sorted(arms.items())}}
json.dump(OUT, open(sys.argv[2], "w"), indent=1, sort_keys=True)
print(json.dumps({k: v for k, v in OUT.items() if k != "sample_arms"}, indent=0))
for a, v in OUT["sample_arms"].items():
    print(a, v["asr"]["k"], "/", v["asr"]["n"], v["asr"]["pct"], v["asr"]["wilson95"], "U", v["utility"]["k"], v["utility"]["pct"])
