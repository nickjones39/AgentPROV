"""Build exam.json for sentry-agentdojo from l1-head.json, l2-head.json, os1-population.json and cc07.json (no raw read).
Usage (repo root): uv run python -I docs/reports/precheck/data/sentry-agentdojo/exam-scripts/exam_build.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pop_wilson import wilson
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L1 = json.load(open(f"{D}/l1-head.json")); L2 = json.load(open(f"{D}/l2-head.json"))
P = json.load(open(f"{D}/os1-population.json")); C = json.load(open(f"{D}/cc07.json"))
def r(k, n): return {"k": k, "n": n, "pct": round(100*k/n, 2) if n else None, "wilson95": wilson(k, n)}
pop_util = {"deepseek-v4-flash|important_instructions": (170, 215), "deepseek-v4-flash|injecagent": (42, 45),
            "deepseek-v4-flash|none": (73, 84), "gpt-4o-mini|important_instructions": (79, 175), "gpt-4o-mini|none": (62, 82),
            "openrouter-free-router|important_instructions": (32, 46), "openrouter-free-router|none": (17, 23)}
paper = {"deepseek-v4-flash|important_instructions": {"unfiltered": "18/215 (8%)", "filtered": "18/198 (9%)"},
         "deepseek-v4-flash|injecagent": {"unfiltered": "0/45", "filtered": "0/42"},
         "gpt-4o-mini|important_instructions": {"unfiltered": "72/175 (41%)", "filtered": "72/153 (47%)"}}
l2map = {"deepseek-v4-flash|important_instructions": "deepseek-v4-flash|none|important_instructions",
         "deepseek-v4-flash|injecagent": "deepseek-v4-flash|none|injecagent", "deepseek-v4-flash|none": "deepseek-v4-flash|none|none",
         "gpt-4o-mini|important_instructions": "gpt-4o-mini|none|important_instructions", "gpt-4o-mini|none": "gpt-4o-mini|none|none",
         "openrouter-free-router|important_instructions": "none|none|important_instructions", "openrouter-free-router|none": "none|none|none"}
rows = []
for a, (ku, nu) in pop_util.items():
    pa = P["arms"].get(a) or {}
    s = L2["outcomes"]["arms"][l2map[a]]
    att = "none" not in a.split("|")[1]
    row = {"arm": a, "population_utility": r(ku, nu), "sample_utility": s["utility"]}
    if att:
        row |= {"population_asr_judged": r(pa["sec_true"], pa["judged"]), "population_asr_paper_filter": r(pa["paper_kept_sec_true"], pa["paper_kept"]),
                "sample_asr": s["attack_success"], "paper": paper.get(a, "none of record"),
                "cc07_181_rescored": {k: C["arms"][a][k]["goal_rescore"] for k in ("all", "kept")} if a in C["arms"] else None}
        sa = s["attack_success"]; pp = 100*pa["sec_true"]/pa["judged"]
        lo, hi = sa["wilson95"]
        row["sample_gap_pp"] = round(100*sa["rate"]-pp, 2)
        row["sample_flag"] = sa["n"] >= 20 and (abs(100*sa["rate"]-pp) > 15 or pp < 100*lo-5 or pp > 100*hi+5)
    rows.append(row)
exam = {"format": "agentprov-precheck-exam/0.1", "corpus_id": "sentry-agentdojo", "part": "head", "code_commit": L1["code_commit"],
 "l1": {"L1-01": {"walked": 782, "selected": 674, "not_selected": 83, "context": 4, "absent_blob": 21, "units": 674, "expected": 674, "match": True},
        "L1-02": {"ok": 674, "of": 674}, "L1-03": L1["L1-03"]["artefacts_with"] | {"note": "#214-class residues in tool content; variation selectors = emoji; 0 bidi/control/zero-width/U+FFFD"},
        "L1-04": {"byte_identical_groups": 0, "trajectory_groups": 0, "cross_corpus_groups_with_sentry": 0},
        "L1-05": {"strata": 26, "facets": {k: L1["L1-05"]["facets"][k] for k in ("pipeline_dir", "attack_dir", "suite", "log_set")}, "prereg_cells_match": True},
        "L1-06": {"artefacts_with": 0, "aux": 0}, "L1-10": {"files_screened": 4, "hits": 0, "operator_home_hits": 0},
        "L1-07": {"evaluation_timestamp": {"n": 674, "naive": 674, "parse_fail": 0, "min": "2026-07-09", "max": "2026-07-22"}, "by_log_set": P["timestamps_by_log_set"],
                  "note": "start_time/end_time pointers are calendar tool arguments (benchmark dates 2023-2025), not run times; 1 unit non-monotone there is benchmark content"},
        "L1-08": {"incomplete": 4, "trailing_calls": 5, "trailing_calls_with_empty_final_text": 2, "zero_tool_call_logs": 5, "empty": 0, "error_present": 0}},
 "headers": P["headers"], "system_prompt": P["system_prompt"], "incomplete": P["incomplete"], "h6": P["h6"],
 "outcomes": rows, "banking_three_paper_sets": {"files": 114, "security_true": 31},
 "cc07": {"c181_per_injection_task": C["per_injection_task"], "c181_totals": {"it013_successes": 34, "affected_goal_datum": 13, "affected_precedence_only": 17},
          "c161": P["cc07_161"], "c161_totals": {"ut5_logs": 17, "ut5_utility_true": 17, "vacuous": 2}},
 "l2": {"n": 130, "validate": "130/130 passed (aer,sem,prov,linkage; shacl not implemented; regression n/a)", "recompute_dry_run": "130 identical, 0 unexplained",
        "determinism": "j1 vs j2: 531 files each, 0 differ, index identical", "verify_chain": "exit 0; checksums.absent on working tree only",
        "executions": L2["executions"], "a3": L2["prov"]["a3"], "evidence": {"aer_ev": {"O": 1980, "I": 1757, "D": 0},
        "prov_by_bundle_class": L2["prov"]["evidence_by_bundle_class"], "twin": 21558, "mixed": 2928, "native_unverified": 0},
        "identity": {"model": {"deepseek-v4-flash": 60, "gpt-4o-mini": 40, "unresolved": 30}, "defence_none": 130, "direct_mismatches": 0},
        "outcome_mapping_check": P["l2_mapping_check"], "redaction": {"files_scanned": 398, "hits": 0}, "withholding": "no policy (L1-06 0)"}}
json.dump(exam, open(f"{D}/exam.json", "w"), indent=1, sort_keys=True)
for x in rows: print(x["arm"], x.get("sample_gap_pp"), x.get("sample_flag"))
