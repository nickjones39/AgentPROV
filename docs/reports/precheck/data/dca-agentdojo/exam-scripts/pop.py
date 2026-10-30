"""Population (L1) outcome rates per arm (model_dir) vs the deposit's own Table 1 (results/paper_tables/
main_results_from_results_xlsx.md, transcribed below), Wilson 95%, README section 4 gap rule. Counts only.
Usage (repo root): uv run python -I docs/reports/precheck/data/dca-agentdojo/exam-scripts/pop.py OUT.json"""
import json, os, sys
from collections import Counter, defaultdict
W = os.path.expanduser("~/.agentprov/migration-work/precheck/dca-agentdojo")
def wilson(k, n, z=1.959964):
    if not n: return [None, None]
    p = k/n; d = 1+z*z/n; c = p+z*z/(2*n); h = z*((p*(1-p)/n+z*z/(4*n*n))**.5)
    return [round(100*(c-h)/d, 2), round(100*(c+h)/d, 2)]
# deposit Table 1 (utility k, ASR k; n = 949), keyed by the TABLE_ROW_TO_LOG_DIR directory prefix
T = {"dca_direct/direct_agentdojo_gpt4omini_important_instructions_api": (378, 287),
     "camel/logs_camel_gpt4omini_fast/gpt-4o-mini-2024-07-18+camel": (193, 1),
     "camel/logs_camel_gpt4omini_fast/gpt-4o-mini-2024-07-18+camel+secpol": (144, 0),
     "drift/runs_agentdojo_full_gpt4omini_api_compat": (533, 0),
     "dca_direct/full_agentdojo_gpt4omini_causal_budgeted_api": (631, 0),
     "dca_direct/direct_agentdojo_qwen36_27b_ollama_important_instructions": (520, 150),
     "drift/runs_agentdojo_full_qwen36_27b_ollama": (569, 0),
     "camel/logs_camel_qwen36_27b_full_agentdojo/qwen3.6:27b+camel": (266, 0),
     "camel/logs_camel_qwen36_27b_full_agentdojo/qwen3.6:27b+camel+secpol": (256, 0),
     "dca_direct/full_agentdojo_qwen36_27b_ollama_causal_budgeted": (471, 0),
     "dca_direct/direct_agentdojo_gptoss20b_openrouter_important_instructions_api": (447, 321),
     "drift/runs_agentdojo_full_gptoss20b_compat_module": (446, 0),
     "camel/logs_camel_gptoss20b_openrouter_agentdojo/openai_gpt-oss-20b+camel": (321, 0),
     "camel/logs_camel_gptoss20b_openrouter_agentdojo/openai_gpt-oss-20b+camel+secpol": (256, 0),
     "dca_direct/full_agentdojo_gptoss20b_openrouter_causal_budgeted": (526, 3)}
def row(md):
    for k in T:
        if md == k or md.startswith(k + "/"): return k
c = defaultdict(Counter); suite = defaultdict(Counter)
for part in ("v1", "drift"):
    for l in open(f"{W}/l1-units-{part}.jsonl"):
        u = json.loads(l); f = u["facets"]; o = u["outcomes"]; md = f["model_dir"]
        kind = "attacked" if f["attack_dir"] != "none" else ("prepass" if f["task_kind"] == "prepass" else "clean")
        a = c[(part, md)]; a[f"{kind}_n"] += 1; a[f"{kind}_util"] += o["utility"] is True; a[f"{kind}_sec"] += o["security"] is True
        a[f"{kind}_err"] += o["error_present"] is True
        if kind == "attacked":
            s = suite[(part, md, f["suite"])]; s["n"] += 1; s["util"] += o["utility"] is True; s["sec"] += o["security"] is True
def cmp(k, n, ref):
    w = wilson(k, n); r = round(100*k/n, 2); gap = round(r - 100*ref/949, 2) if ref is not None else None
    flag = None
    if gap is not None and n >= 20:
        out = max(w[0] - 100*ref/949, 100*ref/949 - w[1], 0)
        flag = abs(gap) > 15 or out > 5
    return {"k": k, "n": n, "pct": r, "wilson95": w, "table_k": ref, "gap_pp": gap, "flag": flag}
arms = {}; tot = Counter()
for (part, md), a in sorted(c.items()):
    t = T.get(row(md)); e = {"part": part, "table_row": row(md)}
    for kind in ("attacked", "prepass", "clean"):
        n = a[f"{kind}_n"]
        if not n: continue
        e[kind] = {"n": n, "util": a[f"{kind}_util"], "sec": a[f"{kind}_sec"], "err": a[f"{kind}_err"]}
        tot[f"{part}_{kind}_n"] += n; tot[f"{part}_{kind}_sec"] += a[f"{kind}_sec"]; tot[f"{part}_{kind}_util"] += a[f"{kind}_util"]
    if "attacked" in e:
        n = e["attacked"]["n"]
        e["UA"] = cmp(e["attacked"]["util"], n, t[0] if t else None); e["ASR"] = cmp(e["attacked"]["sec"], n, t[1] if t else None)
        e["exact_match"] = bool(t) and (e["attacked"]["util"], e["attacked"]["sec"]) == t
        e["macro_suite"] = {m: round(sum(100*suite[(part, md, s)][m]/suite[(part, md, s)]["n"] for s in ("banking", "slack", "travel", "workspace"))/4, 2) for m in ("util", "sec")}
    if "clean" in e: e["clean_utility"] = cmp(e["clean"]["util"], e["clean"]["n"], None)
    arms[md] = e
out = {"arms": arms, "totals": dict(tot), "table_rows": len(T), "rows_matched": sum(1 for a in arms.values() if a.get("exact_match")),
       "flags": [m for m, a in arms.items() if (a.get("UA") or {}).get("flag") or (a.get("ASR") or {}).get("flag")]}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(json.dumps({k: out[k] for k in ("totals", "table_rows", "rows_matched", "flags")}))
for m, a in arms.items(): print(m[-60:], a.get("attacked"), a.get("exact_match"), a.get("clean"), a.get("prepass"))
