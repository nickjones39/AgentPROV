"""Compact per-part digest of the committed L1 summaries (counts only)."""
import json, sys, pathlib
D = pathlib.Path(__file__).resolve().parents[1]
PARTS = ["zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor"]
for p in PARTS:
    d = json.loads((D / f"l1-{p}.json").read_text())
    print("==", p, d["code_commit"][:8], "elapsed", d.get("elapsed_s"))
    print(" L1-01", json.dumps(d["L1-01"]))
    l2 = d["L1-02"]; print(" L1-02", json.dumps({k: l2[k] for k in ("denominator_artefacts","by_primary_class","artefacts_with_class","parsed_ints_beyond_i_json")}), "aux", json.dumps(l2.get("auxiliary")))
    l3 = d["L1-03"]; print(" L1-03 with", json.dumps(l3["artefacts_with"]), "strings", {k: v["strings"] for k, v in l3["classes"].items()})
    l4 = d["L1-04"]; print(" L1-04", json.dumps({"byte": {k: l4["byte_identical"][k] for k in ("groups","artefacts_in_groups")}, "traj": {k: l4["trajectory_identical"][k] for k in ("groups","units_in_groups","units_with_fp","distinct_fp","facets_differing_in_groups")}}))
    l5 = d["L1-05"]; print(" L1-05 strata n", l5["strata"]["n"]); print("  facets", json.dumps({k: v for k, v in l5["facets"].items() if k not in ("dir","task")})[:3000]); print("  unit_facets", json.dumps(l5["unit_facets"])[:2500])
    print("  strata units", json.dumps(l5["strata"]["units"])[:4000])
    l6 = d["L1-06"]; print(" L1-06 with", json.dumps(l6["artefacts_with"]), "strings", {k: v["strings"] for k, v in l6["classes"].items()})
    for k, v in l6["classes"].items():
        if k.startswith("account"): print("   ", k, json.dumps(v["pointers"])[:800])
    l7 = d["L1-07"]; print(" L1-07", json.dumps(l7["artefacts"]), {k: (v["count"], v["forms"], v["parse_fail"], v["min_date"], v["max_date"], v["units_non_monotone"]) for k, v in l7["pointers"].items() if k.startswith("header") or k.startswith("samples:/started") or k=="samples:/events/*/timestamp"})
    print(" L1-08", json.dumps(d["L1-08"]))
