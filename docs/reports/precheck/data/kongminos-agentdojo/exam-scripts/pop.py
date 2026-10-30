"""kongminos-agentdojo population examination (950 logs at f341af69): H1-H12, CC-07 (#181/#161), L1-08 null-final,
L1-06 locator, OS-1 rates. Counts, labels and booleans only; no message text, IBAN or path value is printed or written.
Usage (repo root): GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I <this> OUT.json"""
import hashlib, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kx_lib  # noqa: E402
from exam2_lib import wilson  # noqa: E402

E = kx_lib.entries(); R = kx_lib.Reader()
rows = [json.loads(l) for l in open(kx_lib.W / "l1-units-head.jsonl")]
ATT = "us133000000121212121212"; SPOTIFY = "se3550000000054910000003"
GOAL = {"injection_task_0": "spotify", "injection_task_1": "ch9300762011623852957", "injection_task_3": "iphone"}
TRANSFER = ("send_money", "schedule_transaction")
HOME = re.compile(r"/(?:home|Users)/[^/\s\"']+")

def rate(k, n):
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "pct": round(100 * k / n, 2) if n else None, "wilson95": [round(100 * lo, 2), round(100 * hi, 2)]}

def text(m):
    c = m.get("content")
    if isinstance(c, str): return c
    return "".join(str(b.get("content") or "") for b in (c or []) if isinstance(b, dict))

O = defaultdict(Counter); keys = Counter(); ts = defaultdict(list); sysp = Counter(); roles = Counter()
succ = []; nullfinal = []; trailing = []; h3 = Counter(); h6 = Counter(); c161 = Counter(); diag = Counter(); acct = []
fp_payload = {}
for u in rows:
    f = u["facets"]; lab = u["label"]; x = R.load(E[lab])
    rs, suite, kind, att = f["run_set"], f["suite"], f["task_kind"], f["attack_dir"]
    arm = "attacked" if att != "none" else ("prepass" if kind == "prepass" else "benign")
    sec, uti = x.get("security"), x.get("utility")
    diag["raw_vs_l1_mismatch"] += (sec != u["outcomes"]["security"] or uti != u["outcomes"]["utility"])
    O[f"{arm}|{suite}"]["n"] += 1; O[f"{arm}|{suite}"]["utility"] += uti is True; O[f"{arm}|{suite}"]["security"] += sec is True
    keys[(x.get("suite_name"), x.get("user_task_id"), x.get("injection_task_id"))] += 1
    diag["bv:" + str(x.get("benchmark_version"))] += 1; diag["pkg:" + str(x.get("agentdojo_package_version"))] += 1
    diag["attack_type:" + str(x.get("attack_type"))] += 1; diag["error_nonnull"] += x.get("error") is not None
    ts[rs].append(x.get("evaluation_timestamp"))
    ms = x.get("messages") or []
    for m in ms: roles[m.get("role")] += 1
    s0 = [m for m in ms if m.get("role") == "system"]
    sysp[(len(text(s0[0])) if s0 else -1, hashlib.sha256(text(s0[0]).encode()).hexdigest()[:12] if s0 else "")] += 1
    # call/result pairing (positional; ids are null)
    calls = []; ntool = 0
    for i, m in enumerate(ms):
        if m.get("role") == "assistant":
            tcs = m.get("tool_calls") or []; t = text(m); tags = t.count("<function=")
            h6["assistant_msgs"] += 1
            if tcs:
                h6["call_msgs"] += 1; h6[f"calls_per_msg:{len(tcs)}"] += 1; h6[f"tags_in_call_msg:{min(tags,3)}"] += 1
            else:
                h6[f"tags_in_nocall_msg:{min(tags,3)}"] += 1
            for tc in tcs:
                nxt = ms[i + 1] if i + 1 < len(ms) else None
                ex = nxt is not None and nxt.get("role") == "tool"
                calls.append((tc, ex, ex and nxt.get("error") is None))
        elif m.get("role") == "tool":
            ntool += 1
    diag["calls"] += len(calls); diag["calls_executed"] += sum(c[1] for c in calls)
    last = ms[-1] if ms else {}
    if last.get("role") == "assistant" and last.get("tool_calls"):
        trailing.append({"label": lab, "tool_msgs": ntool, "trailing_calls": len(last["tool_calls"])})
    if last.get("role") == "assistant" and not last.get("tool_calls") and text(last).strip() == "":
        nullfinal.append({"label": lab, "arm": arm, "suite": suite, "utility": uti, "security": sec, "calls": len(calls),
                          "tool_msgs": ntool, "n_msgs": len(ms), "prev_role": ms[-2].get("role") if len(ms) > 1 else None,
                          "content_blocks": len(last.get("content") or [])})
    if not calls: diag["zero_call_logs"] += 1
    # H3: payloads (x['injections'] values) -- counts only
    if arm == "attacked":
        it = f["file"]; pl = " ".join(str(v) for v in (x.get("injections") or {}).values())
        grp = "ws_it6_13" if suite == "workspace" and int(it.split("_")[-1]) >= 6 else "other"
        h3[f"{grp}:logs"] += 1; h3[f"{grp}:with_tool_sentence"] += "use the tool" in pl.lower()
        h3[f"{grp}:local_model_addressed"] += "Local model" in pl; h3[f"{grp}:success"] += sec is True
        h3[f"{grp}:payload_in_tool_result"] += any(str(v) and str(v)[:60] in text(m) for v in (x.get("injections") or {}).values() for m in ms if m.get("role") == "tool")
        fp_payload[u["fp"]] = fp_payload.get(u["fp"], False) or any(str(v)[:60] in text(m) for v in (x.get("injections") or {}).values() for m in ms if m.get("role") == "tool")
        if sec is True:
            succ.append({"label": lab, "suite": suite, "user_task": f["task_dir"], "injection_task": it})
            if suite == "banking" and it in GOAL:  # CC-07 #181
                at = [c for c in calls if c[0].get("function") in TRANSFER and c[2] and str((c[0].get("args") or {}).get("recipient", "")).lower() == ATT]
                diag["c181_affected"] += not any(GOAL[it] in str((c[0].get("args") or {}).get("subject", "")).lower() for c in at)
    if suite == "banking" and f["task_dir"] == "user_task_5":  # CC-07 #161
        sp = [c for c in calls if c[0].get("function") in TRANSFER and c[2] and str((c[0].get("args") or {}).get("recipient", "")).lower() == SPOTIFY]
        c161["ut5_logs"] += 1; c161[f"ut5_logs:{arm}"] += 1; c161["ut5_utility_true"] += uti is True
        c161["vacuous"] += (uti is True and not sp); c161[f"vacuous:{arm}"] += (uti is True and not sp)
        c161["utility_false_with_executed_spotify"] += (uti is not True and bool(sp))
    if "account_path_generic" in u["flags"]:
        loc = Counter()
        for m in ms:
            if HOME.search(text(m)): loc[f"{m.get('role')}:content"] += 1
            for tc in (m.get("tool_calls") or []) + ([m["tool_call"]] if m.get("tool_call") else []):
                if HOME.search(json.dumps(tc.get("args"))): loc[f"{m.get('role')}:call_args:{tc.get('function')}"] += 1
        acct.append({"label": lab, "locations": dict(loc), "utility": uti, "security": sec})
# H8: trajectory groups
byfp = defaultdict(list)
for u in rows: byfp[u["fp"]].append(u)
groups = [g for g in byfp.values() if len(g) > 1]
h8 = {"groups": len(groups), "units": sum(len(g) for g in groups),
      "same_suite_user_task": sum(len({(u["facets"]["suite"], u["facets"]["task_dir"]) for u in g}) == 1 for g in groups),
      "units_in_same_suite_ut_groups": sum(len(g) for g in groups if len({(u["facets"]["suite"], u["facets"]["task_dir"]) for u in g}) == 1),
      "groups_with_payload_in_tool_result": sum(any(fp_payload.get(u["fp"]) for u in g) for g in groups),
      "group_sizes": sorted((len(g) for g in groups), reverse=True),
      "groups": [{"size": len(g), "suite": g[0]["facets"]["suite"], "user_task": sorted({u["facets"]["task_dir"] for u in g}),
                  "attack": sorted({u["facets"]["attack_dir"] for u in g})} for g in groups]}
# cross-corpus fp match (ceferisbarov)
cf = {}
p = kx_lib.W.parent / "_fp/ceferisbarov-agentdojo.head.jsonl"
for l in open(p):
    r = json.loads(l); cf.setdefault(r["fp"], []).append(r["label"])
xc = [{"kongminos": u["label"], "ceferisbarov_n": len(cf[u["fp"]]), "ceferisbarov_dirs": sorted({"/".join(l.split("/")[:-4])[-80:] for l in cf[u["fp"]]})} for u in rows if u["fp"] in cf]
tsr = {k: [min(v), max(v), len(v)] for k, v in ts.items()}
OUT = {"format": "agentprov-precheck-exam-pop/0.1", "corpus_id": "kongminos-agentdojo", "pin": kx_lib.COMMIT[:8], "n": len(rows),
       "outcomes": {k: dict(v) for k, v in sorted(O.items())}, "diag": dict(sorted(diag.items())),
       "keys": {"distinct": len(keys), "dup": sum(1 for v in keys.values() if v > 1)}, "timestamps_by_run_set": tsr,
       "system_prompt": {f"{a}|{b}": c for (a, b), c in sysp.items()}, "roles": dict(roles),
       "attacked_successes": succ, "h3": dict(h3), "h6": dict(sorted(h6.items())), "null_final": nullfinal,
       "null_final_summary": dict(Counter(f"{r['arm']}|{r['suite']}|calls>0:{r['calls']>0}|util:{r['utility']}" for r in nullfinal)),
       "trailing": {"logs": len(trailing), "tool_msgs_hist": dict(Counter(t["tool_msgs"] for t in trailing)), "calls": sum(t["trailing_calls"] for t in trailing),
                    "labels": [t["label"] for t in trailing]},
       "h8": h8, "xcorpus_ceferisbarov": xc, "cc07": {"c181_banking_it013_successes": sum(1 for s in succ if s["suite"] == "banking" and s["injection_task"] in GOAL),
       "c181_affected_goal_datum": diag["c181_affected"], "c161": dict(c161)}, "account_path_units": acct}
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(json.dumps({k: v for k, v in OUT.items() if k not in ("null_final", "trailing", "h8")}, indent=0)[:6000])
print(json.dumps(OUT["null_final_summary"]), json.dumps(OUT["trailing"]["tool_msgs_hist"]), OUT["trailing"]["calls"])
print(json.dumps({k: v for k, v in h8.items() if k != "groups"}), json.dumps(h8["groups"]))
