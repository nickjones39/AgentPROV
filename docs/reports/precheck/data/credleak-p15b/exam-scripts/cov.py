"""credleak-p15b L1-05 roster coverage (16 comparison models x technique, roster layout only, model by directory with the
claude- prefix dropped) and per-technique population vs sample rates (hijack, exfil) with Wilson 95%. From L1 rows.
Usage (worktree root): python -I cov.py <out.json>"""
import sys, json, os, collections
sys.path.insert(0, "tools/analysis2"); from exam2_lib import wilson
S = set(json.load(open("docs/reports/precheck/data/credleak-p15b/l2-sample-head.json"))["labels"])
COMP = {"deepseek-v3.2","devstral-2-123b","gemini-3.1-pro-preview","glm-4.7-flash","gpt-5.5","gpt-oss-120b","gpt-oss-20b","mistral-large-3",
        "nemotron-super-3-120b","nova-2-lite","nova-pro","opus-4-7","opus-4-8","qwen3-235b","qwen3-coder-480b","sonnet-4-6"}
cov = collections.defaultdict(set); P = collections.defaultdict(collections.Counter); Q = collections.defaultdict(collections.Counter)
for l in open(os.path.expanduser("~/.agentprov/migration-work/precheck/credleak-p15b/l1-units-head.jsonl")):
    r = json.loads(l); f = r["facets"]; m = f["model"].replace("claude-", "")
    if f["layout_class"] == "roster" and m in COMP: cov[f["technique"]].add(m)
    for tgt in ([P[f["technique"]], Q[f["technique"]]] if r["label"] in S else [P[f["technique"]]]):
        tgt["n"] += r["n_units"]
        for k in ("hijackSucceeded", "exfiltrationDetected"): tgt[k] += r["outcomes"].get(k, {}).get("true", 0)
out = {"coverage": {t: dict(n=len(v), missing=sorted(COMP - v)) for t, v in sorted(cov.items())}, "rates": {}}
for t in sorted(P):
    row = {}
    for k in ("hijackSucceeded", "exfiltrationDetected"):
        lo, hi = wilson(Q[t][k], Q[t]["n"]) if Q[t]["n"] else (None, None)
        row[k] = dict(pop=[P[t][k], P[t]["n"], round(P[t][k] / P[t]["n"], 4)], sample=[Q[t][k], Q[t]["n"], round(Q[t][k] / Q[t]["n"], 4) if Q[t]["n"] else None],
                      wilson95=[round(lo, 4), round(hi, 4)] if lo is not None else None)
    out["rates"][t] = row
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True)
for t, v in out["coverage"].items(): print(t, v["n"], v["missing"])
for t, v in out["rates"].items(): print(t, v["hijackSucceeded"], v["exfiltrationDetected"])
