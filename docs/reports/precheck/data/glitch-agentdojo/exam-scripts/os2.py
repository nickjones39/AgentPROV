"""OS-2 mapping check on the 100 sampled labels: raw (L1 rows + raw denials via the pinned clone) vs mapped AER
(judgements, denial decisions), denial evidence class in PROV, system-prompt variant labels. Counts only."""
import sys, json
from collections import Counter
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import common
W = Path.home() / ".agentprov/migration-work/precheck/glitch-agentdojo"
C = W / "l2-head-j2.partial"
l1 = {json.loads(l)["sha256"]: json.loads(l) for l in open(W / "l1-units-head.jsonl")}
PFX = "DENIED by the gateway: "
rows = [json.loads(l) for l in open(C / "executions.jsonl")]
labels = {}
for r in rows:
    u = l1[r["raw"][0]["sha256"].split(":", 1)[1]]; labels[u["label"]] = (r, u)
raw_den = {}
for lab, o in common.logs():
    if lab in labels:
        raw_den[lab] = sum(1 for m in o.get("messages") or [] if m.get("role") == "tool" and isinstance(m.get("error"), str) and m["error"].startswith(PFX))
comp = Counter(); mism = Counter(); den = Counter(); sysv = Counter(); prov_den = Counter(); kinds = Counter()
for lab, (r, u) in labels.items():
    recs = [json.loads(x) for x in open(C / r["paths"]["aer"])]
    j = {x["name"]: x for x in recs if x["k"] == "judgement" and x.get("subject") == "run"}
    for name in ("utility", "security"):
        comp[name] += 1
        if u["outcomes"].get(name) != (j.get(name) or {}).get("value"): mism[name] += 1
    d = [x for x in recs if x["k"] == "decision" and any("defence_denial" in y for y in x.get("rule") or [])]
    den["raw_denials"] += raw_den[lab]; den["aer_denial_decisions"] += len(d)
    den["aer_deny_verdicts"] += sum(1 for x in d if str(x.get("verdict")).lower() in ("deny", "denied"))
    if raw_den[lab] != len(d): den["executions_count_differs"] += 1
    if raw_den[lab]: den["executions_with_raw_denial"] += 1
    te = [x for x in recs if x["k"] == "tool_execution"]
    kinds["tool_executions"] += len(te)
    for x in recs:
        if x["k"] == "message":
            v = ((x.get("ext") or {}).get("agentdojo") or {}).get("system_prompt_variant")
            if v: sysv[f"{u['facets']['pipeline_dir']}|{v}"] += 1
    if u["facets"]["pipeline_dir"].endswith("-glitch"): kinds["glitch_arm_execs"] += 1
out = {"compared": dict(comp), "raw_vs_mapped_mismatches": dict(mism), "denials": dict(den), "system_prompt_variant_labels": dict(sysv), "other": dict(kinds),
       "paths_keys": sorted(rows[0]["paths"].keys())}
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True); print(json.dumps(out, indent=1))
