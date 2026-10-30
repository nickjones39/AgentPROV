"""Compact per-part digest of the committed L2 check files and code identity (counts only)."""
import json, pathlib
D = pathlib.Path(__file__).resolve().parents[1]
for p in ["zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor"]:
    d = json.loads((D / f"l2-{p}.json").read_text()); s = json.loads((D / f"l2-sample-{p}.json").read_text())
    c = d["commands"]; e = d["executions"]
    print("==", p, d["code"], "sample n", d["sample"]["n"], "sha", d["sample"]["sha256"][:12], "sample keys", [k for k in s if k not in ("labels", "units", "strata")][:20])
    print(" strata", {k: (len(v) if isinstance(v, list) else v) for k, v in (s.get("strata") or {}).items()} if isinstance(s.get("strata"), dict) else s.get("strata"))
    print(" join", json.dumps(d["sample_join"])[:400])
    print(" exec", json.dumps(e))
    print(" validate", c["validate"]["exit_code"], json.dumps(c["validate"]["counters"]), c["validate"]["issues_by_code"])
    print(" recompute", c["recompute_dry_run"]["exit_code"], {k: c["recompute_dry_run"]["counters"][k] for k in ("identical", "changed_explained", "unexplained_change", "failed", "selected")})
    print(" determinism", {k: c["determinism"][k] for k in ("files_a", "files_b", "n_differ", "index_identical")})
    print(" verify", c["verify_chain"]["exit_code"], c["verify_chain"]["issues_by_code"])
    print(" identity", json.dumps(d["identity"])[:1500])
    print(" issues", json.dumps(d["issues"]))
    pr = d["prov"]; print(" prov checked", json.dumps(pr["checked"]), "ev", json.dumps(pr["evidence_by_bundle_class"]), "twin", pr["unverified_twin_by_bundle_class"], "native", pr["native_unverified_rule_by_bundle_class"], "mixed", pr["mixed_twin_and_native_by_bundle_class"])
    print(" a3", {k: {kk: v[kk] for kk in ("count", "executions", "by")} for k, v in pr["a3"].items()})
    print(" redaction", json.dumps({k: d["redaction"][k] for k in ("executions_hit", "files_scanned", "files_too_large", "hits", "l1_flags_of_sampled_labels")})[:1500])
    w = d.get("withholding"); print(" withhold", json.dumps({k: w[k] for k in w if k != "policy"}) if w else None)
    print(" outcomes", json.dumps(d["outcomes"]["arms"])[:600])
    k = json.loads((D / f"code-{p}.json").read_text()); print(" code", json.dumps(k)[:3400])
