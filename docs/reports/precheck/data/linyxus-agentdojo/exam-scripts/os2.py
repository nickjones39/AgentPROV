"""OS-2: raw outcomes of the 127 sampled labels (L1 rows) by the l2_check arm key model|defence|attack and by stratum,
attacked user tasks only, for comparison with the mapped AER arms in l2-head.json. Counts only.
Usage (repo root): python3 -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/os2.py"""
import json, os
from collections import defaultdict
W = os.path.expanduser("~/.agentprov/migration-work/precheck/linyxus-agentdojo")
S = set(json.load(open("docs/reports/precheck/data/linyxus-agentdojo/l2-sample-head.json"))["labels"])
rows = [json.loads(l) for l in open(f"{W}/l1-units-head.jsonl")]
arm = defaultdict(lambda: [0, 0, 0]); st = defaultdict(lambda: [0, 0, 0])
for u in rows:
    if u["label"] not in S or u["facets"]["task_kind"] != "user" or u["outcomes"]["utility"] is None:
        continue
    p = u["facets"]["pipeline_dir"]
    m = p.replace("openrouter_", "", 1).replace("_", "/", 1).removesuffix("-tacit")
    k = f"{m}|{'tacit' if p.endswith('-tacit') else 'none'}|important_instructions"
    for d in (arm[k], st[u["stratum"].replace("pipeline_dir=openrouter_", "").replace("run_set_family=", "")]):
        d[0] += 1; d[1] += u["outcomes"]["utility"] is True; d[2] += u["outcomes"]["security"] is True
print(json.dumps({"arms_raw_n_util_sec": dict(sorted(arm.items())), "strata_raw_n_util_sec": dict(sorted(st.items()))}, indent=0))
