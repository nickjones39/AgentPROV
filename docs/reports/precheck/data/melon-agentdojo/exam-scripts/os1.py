import json, sys
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[2])
from exam2_lib import wilson
rows = json.load(open("pop.json"))["rows"]
paper = {  # (model, defence, attack): (UA k/144, ASR k/144) from README / report (research.json reported_results)
 ("gpt-4o-2024-05-13","melon_sm","direct"):(52.08,0.00), ("gpt-4o-2024-05-13","melon_sm","important_instructions"):(33.33,2.08),
 ("gpt-4o-2024-05-13","melon_sm","ignore_previous"):(52.78,0.00), ("gpt-4o-2024-05-13","melon_at","direct"):(62.50,0.00),
 ("gpt-4o-2024-05-13","melon_at","important_instructions"):(43.06,13.19), ("gpt-4o-2024-05-13","melon_at","ignore_previous"):(60.42,0.00),
 ("gpt-4o-2024-05-13","melon","direct"):(38.19,0.00), ("gpt-4o-2024-05-13","melon_r","direct"):(45.83,2.08),
 ("gpt-4o-2024-05-13","melon","important_instructions"):(29.86,0.00), ("gpt-4o-2024-05-13","melon","ignore_previous"):(37.50,0.00),
 ("gpt-4o-2024-05-13","melon_r","important_instructions"):(44.44,8.33), ("gpt-4o-2024-05-13","melon_r","ignore_previous"):(43.06,2.78),
}
bu_paper = {("gpt-4o-2024-05-13","melon_sm"):88.89, ("gpt-4o-2024-05-13","melon_at"):100.0}
cells = defaultdict(list)
for r in rows:
    cells[(r["model"], r["defence"], r["suite"], r["attack"])].append(r)
def gap_flag(rate, lo, hi, paper_v, n):
    g = rate - paper_v
    outside = max(lo - paper_v, paper_v - hi, 0)
    return round(g, 2), (abs(g) > 15 and n >= 20) or outside > 5
out = []
for (m, dfn, s, a), rs in sorted(cells.items()):
    comp = [r for r in rs if r["utility"] is not None]
    inc = len(rs) - len(comp)
    n = len(comp)
    ku = sum(1 for r in comp if r["utility"]); ks = sum(1 for r in comp if r["security"])
    row = {"model": m, "defence": dfn, "suite": s, "attack": a, "logs": len(rs), "incomplete": inc, "n": n}
    if a == "none":
        lo, hi = wilson(ku, n); row["BU"] = {"k": ku, "rate": round(100*ku/n, 2) if n else None, "wilson95": [round(100*lo,2), round(100*hi,2)]}
        p = bu_paper.get((m, dfn)) if s == "banking" else None
        if p is not None:
            g, f = gap_flag(100*ku/n, 100*lo, 100*hi, p, n); row["BU"].update(paper=p, gap_pp=g, flag=f)
    else:
        for name, k in (("UA", ku), ("ASR", ks)):
            lo, hi = wilson(k, n); d = {"k": k, "rate": round(100*k/n, 2) if n else None, "wilson95": [round(100*lo,2), round(100*hi,2)]}
            p = paper.get((m, dfn, a)) if s == "banking" else None
            if p is not None:
                pv = p[0] if name == "UA" else p[1]
                if not n: continue
                g, f = gap_flag(100*k/n, 100*lo, 100*hi, pv, n); d.update(paper=pv, gap_pp=g, flag=f)
                # k/144 convention (incomplete counted as utility False / security True, as an AgentDojo run error would be)
                k144 = k + (inc if name == "ASR" else 0)
                d["k_of_144_conv"] = f"{k144}/{len(rs)}" if len(rs) == 144 else None
                d["paper_k_of_144"] = round(pv*144/100)
            row[name] = d
    out.append(row)
# README rows with 0 gpt-4o logs: check every gpt-4o-mini cell for an exact k/144 match
matches = []
for (pm, pd, pa), (ua, asr) in paper.items():
    pk = (round(ua*144/100), round(asr*144/100))
    for (m, dfn, s, a), rs in cells.items():
        if s != "banking" or a == "none" or len(rs) != 144: continue
        ku = sum(1 for r in rs if r["utility"]); ks = sum(1 for r in rs if r["security"])
        if (ku, ks) == pk:
            matches.append({"paper_row": f"{pm}|{pd}|{pa}", "paper_k": list(pk), "matching_cell": f"{m}|{dfn}|{a}", "cell_k": [ku, ks]})
json.dump({"cells": out, "exact_k144_matches": matches}, open("os1.json", "w"), indent=1)
for r in out: print(json.dumps(r))
print("MATCHES"); [print(json.dumps(x)) for x in matches]
