"""kongminos-agentdojo: OS-1 population rates (from pop.json), OS-2 raw vs mapped judgements on the 45-unit scratch corpus,
H8 exposure of the trajectory groups, H10 logs after 15:06:09 (UTC-12 margin). Counts only.
Usage (repo root): GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I <this> POP.json EXTRA.json OUT_OS1.json OUT_OS2.json"""
import json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kx_lib  # noqa: E402
from exam2_lib import wilson  # noqa: E402
def rate(k, n):
    lo, hi = wilson(k, n); return {"k": k, "n": n, "pct": round(100 * k / n, 2), "wilson95": [round(100 * lo, 2), round(100 * hi, 2)]}
pop = json.load(open(sys.argv[1])); ex = json.load(open(sys.argv[2])); O = pop["outcomes"]
def agg(arm, m, suites=("banking", "travel", "workspace")):
    return sum(O[f"{arm}|{s}"][m] for s in suites), sum(O[f"{arm}|{s}"]["n"] for s in suites)
nf_by = Counter(l.split("/")[3] for l in (r["label"] for r in pop["null_final"]))  # suite
rows = []
README = {"benign_utility": 88.16, "ua_874": 82.38, "asr_874": 3.89}
for s in ("banking", "travel", "workspace", None):
    ss = (s,) if s else ("banking", "travel", "workspace"); lab = s or "all"
    k, n = agg("benign", "utility", ss); rows.append({"arm": f"v4-flash/none/none/{lab}", "metric": "benign utility", **rate(k, n), "paper": README["benign_utility"] if not s else None})
    k, n = agg("attacked", "utility", ss); rows.append({"arm": f"v4-flash/none/tool_knowledge/{lab}", "metric": "UA (844 convention)", **rate(k, n), "paper": README["ua_874"] if not s else None})
    k, n = agg("attacked", "security", ss); rows.append({"arm": f"v4-flash/none/tool_knowledge/{lab}", "metric": "targeted ASR", **rate(k, n), "paper": README["asr_874"] if not s else None})
    e = sum(nf_by[x] for x in ss)
    if e:
        k, n = agg("attacked", "utility", ss); rows.append({"arm": f"v4-flash/none/tool_knowledge/{lab}", "metric": "UA without the empty-final logs (info)", **rate(k, n - e), "paper": None})
    k, n = agg("prepass", "utility", ss); rows.append({"arm": f"v4-flash/prepass/{lab}", "metric": "pre-pass utility (info)", **rate(k, n), "paper": None})
# README definition (874 attack-dir files)
ka = agg("attacked", "utility")[0] + agg("prepass", "utility")[0]; ks = agg("attacked", "security")[0] + agg("prepass", "security")[0]
rows.append({"arm": "README definition ad_*_attack (874)", "metric": "utility", **rate(ka, 874), "paper": 82.38})
rows.append({"arm": "README definition ad_*_attack (874)", "metric": "security", **rate(ks, 874), "paper": 3.89})
for r in rows:
    if r["paper"] is not None:
        r["gap_pp"] = round(r["pct"] - r["paper"], 2); lo, hi = r["wilson95"]
        r["outside_wilson_pp"] = round(max(lo - r["paper"], r["paper"] - hi, 0), 2)
        r["flag"] = (abs(r["gap_pp"]) > 15 and r["n"] >= 20) or r["outside_wilson_pp"] > 5
json.dump({"rows": rows}, open(sys.argv[3], "w"), indent=1)
for r in rows: print(r["arm"], r["metric"], r["k"], r["n"], r["pct"], r["wilson95"], r.get("paper"), r.get("gap_pp"), r.get("outside_wilson_pp"), r.get("flag"))
# OS-2
C = kx_lib.W / "l2-head-j2.partial"; l1 = {r["sha256"]: r for r in map(json.loads, open(kx_lib.W / "l1-units-head.jsonl"))}
diff = Counter(); arms = defaultdict(Counter); origins = Counter(); kinds = Counter(); ext = Counter()
for line in open(C / "executions.jsonl"):
    e = json.loads(line); row = l1[e["raw"][0]["sha256"].split(":")[1]]; f = row["facets"]
    recs = [json.loads(l) for l in open(C / e["paths"]["aer"])]; js = {}
    for r in recs:
        kinds[r.get("k")] += 1
        if r.get("k") == "judgement": js[r.get("name")] = r.get("value"); origins[f"{r.get('name')}|{r.get('origin')}"] += 1
        if "local_model_tag_count" in json.dumps(r.get("ext") or {}): ext["local_model_tag_count"] += 1
    for m in ("utility", "security"):
        diff["compared"] += 1; diff["differ"] += row["outcomes"][m] != js.get(m)
    arm = "attacked" if f["attack_dir"] != "none" else ("prepass" if f["task_kind"] == "prepass" else "benign")
    a = arms[f"{arm}|{f['suite']}"]; a["n"] += 1; a["utility"] += js.get("utility") is True; a["security"] += js.get("security") is True
os2 = {"judgements": dict(diff), "origins": dict(origins), "record_kinds": dict(kinds), "ext_local_model_tag_count_records": ext["local_model_tag_count"],
       "arms": {k: {**dict(v), "utility_rate": rate(v["utility"], v["n"]), **({"asr": rate(v["security"], v["n"])} if k.startswith("attacked") else {})} for k, v in sorted(arms.items())}}
json.dump(os2, open(sys.argv[4], "w"), indent=1, sort_keys=True); print(json.dumps({k: v for k, v in os2.items() if k != "arms"}))
for k, v in os2["arms"].items(): print(k, v["n"], v["utility"], v["security"], v["utility_rate"]["wilson95"], v.get("asr", {}).get("wilson95"))
# H8 exposure + H10
E = kx_lib.entries(); R = kx_lib.Reader(); byfp = defaultdict(list)
for r in l1.values(): byfp[r["fp"]].append(r)
h8 = Counter(); late = 0
def text(m):
    c = m.get("content"); return c if isinstance(c, str) else "".join(str(b.get("content") or "") for b in (c or []) if isinstance(b, dict))
for g in byfp.values():
    if len(g) < 2: continue
    exp = 0; calls = 0
    for r in g:
        ms = R.load(E[r["label"]]).get("messages") or []
        exp += any("<INFORMATION>" in text(m) for m in ms if m.get("role") == "tool"); calls += sum(len(m.get("tool_calls") or []) for m in ms)
    h8[f"group_size:{len(g)}|exposed_units:{exp}|calls_total:{calls}"] += 1
print(dict(h8))
for r in l1.values():
    t = R.load(E[r["label"]]).get("evaluation_timestamp") or ""; late += t > "2026-08-21 15:06:09"
print("logs after 15:06:09 naive:", late)
