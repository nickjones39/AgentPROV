"""OS-1: the 16 paper cells (TACIT 2603.00991v2 App. E.2 Table 4; LACUNA 2605.28617v1 Table 3) against the L1 population
(exam/pop.json): every single root and the latest-wins merge; best-matching source; Wilson 95 %; README section 4 gap rule;
#161 re-score (UT5 vacuous as false) of banking cells. Writes data/linyxus-agentdojo/os1-population.json (counts only).
Usage (repo root): uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/outcomes.py"""
import json, os, sys
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson  # noqa: E402
W = os.path.expanduser("~/.agentprov/migration-work/precheck/linyxus-agentdojo/exam")
P = json.load(open(f"{W}/pop.json"))
G, O = "openrouter_google_gemini-2.5-pro-tacit", "openrouter_openai_o4-mini-high-tacit"
PAPER = [  # (paper, pdir, suite, utility_k, n, attack_k)
    ("TACIT", G, "banking", 82, 144, 0), ("TACIT", G, "workspace", 283, 560, 0), ("TACIT", G, "slack", 42, 105, 0), ("TACIT", G, "travel", 90, 140, 0),
    ("TACIT", O, "banking", 85, 144, 0), ("TACIT", O, "workspace", 296, 560, 0), ("TACIT", O, "slack", 50, 105, 0), ("TACIT", O, "travel", 96, 140, 1),
    ("LACUNA", G, "banking", 91, 144, 0), ("LACUNA", G, "workspace", 315, 560, 4), ("LACUNA", G, "slack", 45, 105, 2), ("LACUNA", G, "travel", 89, 140, 1),
    ("LACUNA", O, "banking", 95, 144, 0), ("LACUNA", O, "workspace", 311, 560, 0), ("LACUNA", O, "slack", 52, 105, 1), ("LACUNA", O, "travel", 100, 140, 0)]


def r(k, n):
    lo, hi = wilson(k, n); return {"k": k, "n": n, "pct": round(100 * k / n, 2), "wilson95": [round(100 * lo, 2), round(100 * hi, 2)]}


def gap_rule(k, n, pk, pn):
    p = 100 * pk / pn; s = r(k, n); g = s["pct"] - p
    outside = max(s["wilson95"][0] - p, p - s["wilson95"][1], 0)
    return round(g, 2), round(outside, 2), (abs(g) > 15 and n >= 20) or outside > 5


rows = []
for paper, pdir, suite, uk, n, ak in PAPER:
    fam = "runs" if paper == "TACIT" else "lacuna-runs"
    srcs = {k.split("|")[0]: v for k, v in P["cells_per_root"].items() if k.split("|")[1] == pdir and k.split("|")[2] == suite and k.startswith(fam + "-")}
    m = (P["merge_tacit"] if paper == "TACIT" else P["merge_lacuna"]).get(f"{pdir}|{suite}")
    if m:
        srcs["merge_latest_wins"] = m
    cand = {s: v for s, v in srcs.items() if v["n"] == n}
    best = min(cand, key=lambda s: (abs(cand[s]["utility_k"] - uk) + abs(cand[s]["attack_k"] - ak), s), default=None)
    row = {"paper": paper, "pipeline_dir": pdir, "suite": suite, "paper_utility": r(uk, n), "paper_attack_k": ak,
           "sources": {s: {"n": v["n"], "utility_k": v["utility_k"], "attack_k": v["attack_k"], "utility_k_ut5_vacuous_false": v["utility_k_ut5fix"]} for s, v in sorted(srcs.items())}}
    if best:
        b = cand[best]; g, out, fires = gap_rule(b["utility_k"], b["n"], uk, n)
        row.update(best_source=best, utility=r(b["utility_k"], b["n"]), attack=r(b["attack_k"], b["n"]), utility_gap_pp=g,
                   utility_outside_wilson_pp=out, gap_rule_fires=fires,
                   exact=b["utility_k"] == uk and b["attack_k"] == ak,
                   within_one=abs(b["utility_k"] - uk) <= 1 and abs(b["attack_k"] - ak) <= 1,
                   utility_ut5_vacuous_false=r(b["utility_k_ut5fix"], b["n"]) if suite == "banking" else None)
    else:
        row.update(best_source=None, note="no released log for this cell")
    rows.append(row)
json.dump({"format": "agentprov-precheck-os1/0.1", "corpus_id": "linyxus-agentdojo", "basis": "exam/pop.json (raw utility/security, attacked complete logs)", "cells": rows},
          open("docs/reports/precheck/data/linyxus-agentdojo/os1-population.json", "w"), indent=1, sort_keys=True)
for x in rows:
    print(x["paper"], x["pipeline_dir"][11:22], x["suite"], x.get("best_source"), x.get("utility", {}).get("pct"), x.get("utility", {}).get("wilson95"), x["paper_utility"]["pct"],
          x.get("utility_gap_pp"), x.get("utility_outside_wilson_pp"), x.get("gap_rule_fires"), "A", x.get("attack", {}).get("k"), x["paper_attack_k"], x.get("exact"), (x.get("utility_ut5_vacuous_false") or {}).get("pct"))
