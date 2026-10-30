"""Write the counts-only derived data files for the dossier (no labels of flagged artefacts, no values)."""
import json, re, ast
from pathlib import Path
X = Path.home() / ".agentprov/migration-work/precheck/geryon-agentdojo/exam"
D = Path.cwd() / "docs/reports/precheck/data/geryon-agentdojo"  # run from the repository root
os1 = json.load(open(X / "os1.json")); rr = json.load(open(X / "runrec.json"))
os2 = json.load(open(X / "os2.json")); cmp_ = json.load(open(X / "os_cmp.json"))
q = (X / "quirks.out").read_text().split("\ndenials per set ")
quirks = json.loads(q[0])
rest = q[1].split("\nhome logs by set ")
den = ast.literal_eval(rest[0]); rest2 = rest[1].split("\nfinal_null by set ")
home = [{"run_set": k[0], "suite": k[1], "cond": k[2], "task": k[4], "logs": v} for k, v in ast.literal_eval(rest2[0])]
fn = [{"run_set": k[0], "log_set": k[1], "pending_calls": k[2], "logs": v} for k, v in ast.literal_eval(rest2[1].strip())]
h = (X / "h10_h13.out").read_text().splitlines()
h10 = ast.literal_eval(h[0].split("H10 ", 1)[1])
h10b = (X / "h10b.out").read_text().splitlines()
ut15 = ast.literal_eval((X / "ut15.out").read_text().strip())
os1_out = {"format": "agentprov-precheck-geryon-os1/1", "unit": "attacked logs (user_task_* / important_instructions); pre-passes excluded",
           "source": "L1 raw outcome fields (l1-units-head.jsonl), pairs from results/pairs.json (42 banking within-policy pairs) and the 36 run records (results/<run set>/<suite>-<cond>-r<n>.json, not selected by the profile)",
           "logs": os1, "run_records": rr}
extra = {"format": "agentprov-precheck-geryon-l1-extra/1", "quirk_counts": quirks, "denials_per_log_set": den,
         "account_path_generic_logs_by_cell": home, "null_final_mapper_rule_by_log_set": fn,
         "h10_slack_it5": h10, "h10_slack_it5_effect": {"logs": ast.literal_eval(h10b[0]), "pairs": ast.literal_eval(h10b[1].split("pairs ", 1)[1])},
         "h13": h[1:], "banking_ut15_confound": ut15,
         "licence": "LICENSE blob 11,348 bytes contains 'Copyright 2026'; no '[yyyy]' placeholder"}
os2_out = {"format": "agentprov-precheck-geryon-os2/1", "mapping_check": os2, "population_vs_sample": cmp_}
for name, obj in (("os1-population.json", os1_out), ("os2-sample.json", os2_out), ("l1-extra.json", extra)):
    s = json.dumps(obj, indent=1, sort_keys=True)
    assert not re.search(r"/Users/|/home/[^<]|~/", s), name
    (D / name).write_text(s + "\n")
    print(name, len(s))
