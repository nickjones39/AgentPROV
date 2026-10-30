# ruff: noqa  (precheck examiner script for kexin-xu-01-agentharm; aggregates scratch outputs into counts-only data files)
"""Usage: python -I summarise.py <exam scratch dir> <data dir>"""
import json, sys
from collections import Counter
from pathlib import Path
S, D = Path(sys.argv[1]).expanduser(), Path(sys.argv[2])
r = json.load(open(S / "raw.json")); L = r["logs"]
te = Counter(); lg = Counter()
for x in L:
    te.update(x["tool_errors"]); lg["vllm-local" if (x["model"] or "").startswith("local:") else (x["model"] or "none").split("/")[0]] += x["logger_events"]
agg = {"format": "agentprov-precheck-raw-hypotheses/0.1", "script": "exam-scripts/raw_checks.py", "logs": len(L),
 "H01_header_status": dict(Counter(f"header={x['header']}|status={x['status']}" for x in L)), "H01_samples": sum(x["samples"] for x in L),
 "H02_H03_nonsuccess": [{k: x[k] for k in ("judge_variant", "model", "task", "status", "samples", "scored", "sample_errors", "error_classes", "header_error", "dataset_samples")} for x in L if x["status"] != "success"],
 "H10_header_identity": dict(Counter(f"{x['judge_variant']}|scorers={x['scorers']}|task_version={x['task_version']}|packages={json.dumps(x['packages'], sort_keys=True)}|judges={json.dumps(x['judges'], sort_keys=True)}" for x in L)),
 "H10_revision": dict(Counter(f"{x['judge_variant']}|{x['revision']['origin']}|{x['revision']['commit7']}" for x in L)),
 "H07_content_filter": [{"judge_variant": x["judge_variant"], "task": x["task"], "samples": len(x["content_filter"]), "refusal_1": sum(c["refusal"] == 1 for c in x["content_filter"])} for x in L if x["content_filter"]],
 "H09_tool_error_events": dict(te), "H11_refusal_judge_errors": sum(x["refusal_judge_errors"] for x in L),
 "H12_ts_violations": sum(sum(x["ts_violations"].values()) for x in L), "H12_range": [min(x["ts_min"] for x in L if x["ts_min"]), max(x["ts_max"] for x in L if x["ts_max"])],
 "H15_logger_by_provider": dict(lg),
 "H17_behaviour_sets": dict(Counter(f"{x['behaviour_ids']}|{json.dumps(x['category'], sort_keys=True)}" for x in L if x["samples"] == 44)),
 "H13_dataset_location": {"logs_by_account_class": dict(Counter(json.dumps(x["dataset_location_accounts"]) for x in L)), "named_accounts": r["acct"]["dataset_location_named"]},
 "raw_named_account_segments_in_sample_content": r["acct"]["content_named"]}
(D / "raw-hypotheses.json").write_text(json.dumps(agg, indent=1, sort_keys=True) + "\n")
p2 = json.load(open(S / "pass2.json")); p2["readfile_2439"] = json.load(open(S / "readfile.json")); p2["script"] = "exam-scripts/pass2.py, readfile_2439.py"
(D / "l2-aer-pass.json").write_text(json.dumps(p2, indent=1, sort_keys=True) + "\n")
print("ok")
