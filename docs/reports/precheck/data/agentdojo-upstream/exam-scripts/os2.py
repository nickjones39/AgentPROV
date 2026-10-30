"""agentdojo-upstream OS-2 mapping check: mapped AER run judgements vs raw L1 outcomes of the same labels; plus
sample-level structural counts (empty assistant turns, system-prompt variant labels, load_environment activities).
Counts only. Usage: os2.py OUT.json"""
import json, sys
from collections import Counter
from pathlib import Path

W = Path.home() / ".agentprov/migration-work/precheck/agentdojo-upstream"
OUT = {}
for part in ("head", "2024-06"):
    l1 = {json.loads(l)["sha256"]: json.loads(l) for l in open(W / f"l1-units-{part}.jsonl")}
    C = W / f"l2-{part}-j2.partial"
    comp = Counter(); mism = Counter(); origin = Counter(); empt = Counter(); sysvar = Counter(); act = Counter()
    for line in open(C / "executions.jsonl"):
        r = json.loads(line)
        u = l1[r["raw"][0]["sha256"].split(":", 1)[1]]
        f = u["facets"]
        recs = [json.loads(x) for x in open(C / r["paths"]["aer"])]
        j = {x["name"]: x for x in recs if x["k"] == "judgement" and x.get("subject") == "run"}
        for name in ("utility", "security"):
            comp[name] += 1
            raw, got = u["outcomes"].get(name), (j.get(name) or {}).get("value")
            if raw != got:
                mism[f"{name}|raw={json.dumps(raw)}|aer={json.dumps(got)}|{f['variant']}"] += 1
            if name in j:
                origin[f"{name}|{j[name].get('origin')}|" + ",".join(sorted(x.split('#')[0] for x in j[name].get("rule") or []))] += 1
        local = f["pipeline_dir"].startswith(("Meta-SecAlign", "meta-llama_Llama-3.3"))
        grp = "local" if local else "api"
        empt["executions_" + grp] += 1
        n_empty = 0
        for x in recs:
            if x["k"] == "message" and x.get("role") == "assistant":
                parts = x.get("parts") or []
                if not any(p.get("t") == "tool_call" for p in parts) and all((p.get("text") or "").strip() == "" for p in parts if p.get("t") == "text"):
                    n_empty += 1
            if x["k"] == "message" and ((x.get("ext") or {}).get("agentdojo") or {}).get("system_prompt_variant"):
                sysvar[x["ext"]["agentdojo"]["system_prompt_variant"]] += 1
            if x["k"] == "activity":
                act[f"{x.get('type')}|{f['attack_class']}"] += 1
        act[f"_executions|{f['attack_class']}"] += 1
        if n_empty:
            empt["with_empty_assistant_turn_" + grp] += 1
    OUT[part] = {"compared": dict(comp), "raw_vs_mapped_mismatches": dict(mism), "judgement_origin_rules": dict(sorted(origin.items())),
                 "empty_assistant_turn_without_call": dict(empt), "system_prompt_variant_labels": dict(sysvar), "activities": dict(act)}
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True)
for p, r in OUT.items():
    print(p, r["compared"], r["raw_vs_mapped_mismatches"], r["empty_assistant_turn_without_call"], r["system_prompt_variant_labels"], r["activities"])
