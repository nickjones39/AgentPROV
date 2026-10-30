"""OS-2 mapping check for yockcheng head: mapped AER run judgements vs the raw L1 outcomes of the same labels, the
judgement origin rules, task/attack/model identity, benchmark version, timestamps, quirk hooks and record kinds.
Counts only. Usage: os2.py CORPUS OUT.json"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
W = Path.home() / ".agentprov/migration-work/precheck/yockcheng-prompt-injection-harness"
C = Path(sys.argv[1])
l1 = {json.loads(l)["sha256"]: json.loads(l) for l in open(W / "l1-units-head.jsonl")}
comp = Counter(); mism = Counter(); origin = Counter(); kinds = Counter(); exttop = Counter(); taskk = Counter()
unk = Counter(); evf = Counter(); arms = defaultdict(Counter); quirk = Counter(); ts = Counter(); judg_names = Counter()
for line in open(C / "executions.jsonl"):
    r = json.loads(line)
    u = l1[r["raw"][0]["sha256"].split(":", 1)[1]]
    f = u["facets"]
    recs = [json.loads(x) for x in open(C / r["paths"]["aer"])]
    for x in recs:
        kinds[x["k"]] += 1
        if x["k"] == "judgement": judg_names[f"{x.get('subject')}|{x.get('name')}|origin={x.get('origin')}"] += 1
    j = {x["name"]: x for x in recs if x["k"] == "judgement" and x.get("subject") == "run"}
    for name in ("utility", "security"):
        comp[name] += 1
        raw, got = u["outcomes"].get(name), (j.get(name) or {}).get("value")
        if raw != got:
            mism[f"{name}|raw={json.dumps(raw)}|aer={json.dumps(got)}|{f['variant']}|{f['task_kind']}"] += 1
        if name in j:
            origin[f"{name}|{f['task_kind']}|{j[name].get('origin')}|" + ",".join(sorted(x.split('#')[0] for x in j[name].get("rule") or []))] += 1
    head = next(x for x in recs if x["k"] in ("execution", "header"))
    t = head.get("task") or {}
    taskk[f"suite={t.get('suite')}|attack={t.get('attack_id')}|defence={t.get('defense_id')}"] += 1
    for k in sorted(head.keys()): exttop[k] += 1
    kind = "attacked" if f["attack_dir"] == "important_instructions" else f["task_kind"]
    arms[f"{f['pipeline_dir']}|{kind}"][f"u={(j.get('utility') or {}).get('value')}|s={(j.get('security') or {}).get('value')}"] += 1
OUT = {"compared": dict(comp), "raw_vs_mapped_mismatches": dict(mism), "judgement_origin_rules": dict(sorted(origin.items())),
       "record_kinds": dict(kinds), "judgement_names": dict(sorted(judg_names.items())), "header_keys": dict(exttop),
       "task_facets": dict(taskk), "arms_mapped": {k: dict(v) for k, v in sorted(arms.items())}}
json.dump(OUT, open(sys.argv[2], "w"), indent=1, sort_keys=True)
print(json.dumps(OUT, indent=1, sort_keys=True))
