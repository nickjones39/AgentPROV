"""H9: per pair x split x domain cell with a changed re-judged value, |gap to paper| with the stored vs the original
attack_success (micro). Usage: python -I h9.py <pop.json> <raw.json> <out.json>"""
import json, sys
pop = json.load(open(sys.argv[1])); raw = json.load(open(sys.argv[2]))["rejudged_by_cell"]
cells = {f"{c['pair']}|{c['split']}|{c['domain']}": c for c in pop["cells"]}
res = []; better = {"stored": 0, "original": 0, "tie": 0}
for key, ch in raw.items():
    ft = ch.get("False->True", 0); tf = ch.get("True->False", 0)
    if not (ft or tf) or key not in cells or "paper" not in cells[key]:
        continue
    c = cells[key]; ko = c["k"] - ft + tf; so = 100 * c["k"] / c["n"]; oo = 100 * ko / c["n"]
    gs, go = abs(so - c["paper"]), abs(oo - c["paper"])
    w = "stored" if gs < go else ("original" if go < gs else "tie"); better[w] += 1
    res.append({"cell": key, "n": c["n"], "F->T": ft, "T->F": tf, "stored": round(so, 2), "original": round(oo, 2),
                "paper": c["paper"], "closer": w})
json.dump({"closer_counts": better, "cells": res}, open(sys.argv[3], "w"), indent=1)
print(better); [print(r) for r in res]
