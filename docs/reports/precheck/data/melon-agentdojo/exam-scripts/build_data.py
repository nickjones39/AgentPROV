import json, sys
from collections import Counter, defaultdict
D = sys.argv[1]
sys.path.insert(0, sys.argv[2])
from exam2_lib import wilson
pop = json.load(open("pop.json")); rows = pop["rows"]
os1 = json.load(open("os1.json")); s2 = json.load(open("os2_rows.json"))
idx = {(r["model"], r["defence"], r["suite"], r["attack"], r["task"], r["inj"]): r for r in rows}
# partial-arm same-cell control
ctrl = {}
for dfn in ("melon", "melon_r", "melon_rp"):
    part = [r for r in rows if r["model"] == "gpt-4o-2024-05-13" and r["defence"] == dfn and r["attack"] == "direct" and r["suite"] == "banking"]
    comp = [r for r in part if r["utility"] is not None]
    e = {"logs": len(part), "n_complete": len(comp), "UA_k": sum(1 for r in comp if r["utility"]),
         "user_tasks": dict(sorted(Counter(r["task"] for r in part).items())), "dates": dict(sorted(Counter(r["date"] for r in part).items()))}
    for other in ("melon_sm", "melon_at"):
        ks = [idx.get(("gpt-4o-2024-05-13", other, "banking", "direct", r["task"], r["inj"])) for r in part]
        ks = [k for k in ks if k and k["utility"] is not None]
        e[f"same_cells_{other}"] = {"n": len(ks), "UA_k": sum(1 for k in ks if k["utility"])}
    ctrl[dfn] = e
may = Counter(r["pdir"] for r in rows if r["date"] < "2026-06-01")
os1_out = {"format": "melon-agentdojo-os1/1", "basis": "raw utility/security of the 1,911 logs at xwsdid/MELON@71d99dff (agentprov.ingest strict parse); incomplete logs (keys absent) excluded from n and reported; k_of_144_conv counts an incomplete log as utility False / security True",
           "paper": "README + report/MELON_SATM_AT_补充内容.md values (research.json reported_results); k = round(rate*144/100)",
           "gap_rule": "README section 4: |gap| > 15 pp with n >= 20, or the Wilson 95% interval excludes the paper value by > 5 pp",
           "cells": os1["cells"], "exact_k144_matches_any_cell": os1["exact_k144_matches"],
           "partial_arm_same_cell_control": ctrl, "may_logs_by_pipeline_dir": dict(may),
           "no_defence_row_check": {"readme": {"direct": [62, 80], "important_instructions": "45.83/51.30 (ASR not k/144)", "ignore_previous": "44.44/52.37 (ASR not k/144)"},
                                    "fork_undefended_logs": 0,
                                    "upstream_copies_agentdojo_head_gpt-4o-2024-05-13_banking": {"direct": [101, 17, 144], "important_instructions": [100, 90, 144], "ignore_previous": [99, 12, 144]},
                                    "verdict": "no released log reproduces the README No Defense row"}}
json.dump(os1_out, open(f"{D}/os1-population.json", "w"), indent=1, ensure_ascii=False)
# OS-2
c = Counter()
for r in s2:
    if r["aer_u"] == "absent": c["incomplete_absent_both"] += 1; continue
    c["utility_equal" if r["raw_u"] == r["aer_u"] else "utility_differ"] += 1
    c["security_equal" if r["raw_s"] == r["aer_s"] else "security_differ"] += 1
    c["security_origin_" + str(r["s_origin"])] += 1
pooled = {}
for name, sel in [("gpt-4o melon_sm+melon_at attacked", lambda x: x["model"].startswith("gpt-4o-2024") and x["defence"] in ("melon_sm", "melon_at") and x["attack"] != "none"),
                  ("all attacked", lambda x: x["attack"] != "none"), ("gpt-4o-mini attacked", lambda x: x["model"].startswith("gpt-4o-mini") and x["attack"] != "none"),
                  ("pre-pass (BU)", lambda x: x["attack"] == "none")]:
    ss = [x for x in s2 if sel(x) and x["aer_u"] != "absent"]
    w = Counter((x["model"], x["defence"], x["suite"], x["attack"]) for x in ss)
    strata = defaultdict(list)
    for x in rows:
        if sel(x) and x["utility"] is not None: strata[(x["model"], x["defence"], x["suite"], x["attack"])].append(x)
    def sw(key): return round(100 * sum(w[k] * sum(1 for x in strata[k] if x[key]) / len(strata[k]) for k in w) / sum(w.values()), 2)
    ku = sum(1 for x in ss if x["aer_u"]); ks = sum(1 for x in ss if x["aer_s"])
    pooled[name] = {"n": len(ss), "UA_or_BU": {"k": ku, "rate": round(100*ku/len(ss), 2), "wilson95": [round(100*v, 2) for v in wilson(ku, len(ss))], "population_sample_weighted": sw("utility")}}
    if "pre-pass" not in name:
        pooled[name]["ASR"] = {"k": ks, "rate": round(100*ks/len(ss), 2), "wilson95": [round(100*v, 2) for v in wilson(ks, len(ss))], "population_sample_weighted": sw("security")}
json.dump({"format": "melon-agentdojo-os2/1", "labels": len(s2), "raw_vs_mapped": dict(c), "pooled_sample": pooled,
           "note": "mapped = AER judgement values of the j2 scratch corpus; raw = L1 population scan of the same labels; per-arm sample rates are in l2-head.json (n = 5 per cell, no arm reaches n >= 20)"},
          open(f"{D}/os2-sample.json", "w"), indent=1)
# defence-authored content
agg = defaultdict(Counter)
syspat = Counter()
for r in rows:
    for k, v in r["counts"].items():
        agg[r["pdir"]][k] += v
        if v: agg[r["pdir"]]["logs_with_" + k] += 1
    pat = "+".join(f"{('idx0' if i == 0 else 'idx1' if i == 1 else 'later')}:{dg}:{n}" for i, dg, n, _, _ in r["system"])
    syspat[f"{r['pdir']}|{pat}"] += 1
json.dump({"format": "melon-agentdojo-defence-content/1",
           "basis": "1,911 logs, raw; fixed texts matched exactly (base-MELON stop message, AgentDojo PI sentinel, MELON-R SANITIZE marker); CJK = Han/CJK punctuation; system messages by sha256 prefix and length",
           "per_pipeline_dir": {k: dict(sorted(v.items())) for k, v in sorted(agg.items())},
           "system_message_patterns": dict(sorted(syspat.items())),
           "sanitize_marker": {"tool_messages": 120, "logs": 101, "whole_message": 8, "partial": 112, "by_dir": {"gpt-4o-mini-2024-07-18-melon_r": {"messages": 119, "logs": 100, "whole": 7}, "gpt-4o-2024-05-13-melon_r": {"messages": 1, "logs": 1, "whole": 1}},
                               "second_marker_not_at_pin": {"tool_messages": 4, "occurrences": 5, "dirs": {"gpt-4o-2024-05-13-melon_r": 3, "gpt-4o-2024-05-13-melon_rp": 1}}},
           "block_messages": {"assistant_cjk_tool_calls_null": 3, "dir": "gpt-4o-mini-2024-07-18-melon_r", "ending": "CJK full stop (final-route BLOCK)", "pre_route_ascii_dot": 0},
           "prepass_interventions": {"prepass_logs": 88, "with_sentinel": 0, "with_sanitize": 0, "with_recovery_system": 0},
           "l2_mapping_j2": {"stop_message": {"n": 34, "role": "assistant", "actor": "agent", "generated_by_model_call": 34, "rule": "agentdojo.assistant_msg_has_one_call_unverified@1#/generated_by"},
                             "sentinel_tool_results": {"n": 34, "actor": "def0", "decisions": 34},
                             "system_messages": {"agentdojo_default@idx0 actor=bench": 131, "melon_r_prompt@idx0 actor=bench (RECOVERY text)": 3, "default prompt at later index, actor=none, variant=none": 3, "129-char SECURITY WARNING insert, actor=none": 8},
                             "block_messages_sampled": 0},
           "detection_stats_json": pop["detection_stats"]}, open(f"{D}/defence-content.json", "w"), indent=1, ensure_ascii=False)
print("ok")
