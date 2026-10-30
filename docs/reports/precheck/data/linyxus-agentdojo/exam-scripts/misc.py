"""linyxus-agentdojo: H9 (timestamp month by family/model key), H12 on L2 (AER tool_execution names vs the sampled raw logs'
agent tool results and backend traces), H14 (pipeline_name_mismatch by run set in the sample), CC-10 (slack IT5 successes:
which env functions the executed trace holds), L1-06 secret origin (digest only: does the value occur in upstream
agentdojo 0.1.35 suites; file paths of benchmark data only). Counts only.
Usage (repo root): uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/misc.py OUT.json"""
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lx_lib  # noqa: E402
from l1_scan import SECRET_PATTERNS  # noqa: E402

E = lx_lib.entries(); R = lx_lib.Reader()
rows = [json.loads(l) for l in open(lx_lib.W / "l1-units-head.jsonl")]
UP = os.path.expanduser("~/.agentprov/upstream/github.com/ethz-spylab/agentdojo.git")
OUT = {"h9": Counter(), "cc10_it5": Counter(), "h12_l2": {}, "h14_sample": Counter(), "secret_origin": {}}
GEN = SECRET_PATTERNS["generic-credential-assignment"]
SLACK_FN = ("invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack")
for u in rows:
    f = u["facets"]; x = R.load(E[u["label"]])
    ts = x.get("evaluation_timestamp") or ""
    OUT["h9"][f"{f['run_set_family']}|{ts[:7]}|model_key={'model' in x}"] += 1
    if f["suite"] == "slack" and f["file"] == "injection_task_5" and x.get("security") is True and f["task_kind"] == "user":
        bt = x.get("backend_tool_traces") or []
        names = {t.get("function") for t in bt}
        OUT["cc10_it5"]["successes"] += 1
        OUT["cc10_it5"]["all_three_in_trace"] += all(n in names for n in SLACK_FN)
        for n in SLACK_FN:
            OUT["cc10_it5"][f"has_{n}"] += n in names
        OUT["cc10_it5"][f"src:{x.get('tool_trace_source')}"] += 1
    so = x.get("tacit_secure_output")
    if isinstance(so, str) and GEN.search(so):
        mt = GEN.search(so); val = re.split(r"[:=]", mt.group(0), maxsplit=1)[1].strip(" \"'")
        # same value in the benchmark's own text? (prefix of the value, git grep -F; only paths and counts printed)
        p = subprocess.run(["git", "--git-dir", UP, "grep", "-c", "-F", "-f", "-", "089ed468", "--", "src/agentdojo/data"],
                           input=val[:24], capture_output=True, text=True,
                           env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"})
        OUT["secret_origin"] = {"value_prefix_len": 24, "upstream_089ed468_files": [l.rsplit(":", 1)[0].split(":", 1)[1] for l in p.stdout.splitlines()],
                                "in_tool_result_of_same_log": any(val in json.dumps(m.get("content")) for m in (x.get("messages") or []) if m.get("role") == "tool")
                                or any(val in json.dumps(t) for t in (x.get("backend_tool_traces") or []))}
# L2: AER tool_execution names vs raw sampled logs
sample = json.load(open("docs/reports/precheck/data/linyxus-agentdojo/l2-sample-head.json"))["labels"]
raw_tool_results = 0; raw_bt = 0; raw_names = Counter()
for lab in sample:
    x = R.load(E[lab]); ms = x.get("messages") or []
    raw_tool_results += sum(1 for m in ms if m.get("role") == "tool")
    raw_bt += len(x.get("backend_tool_traces") or [])
    for m in ms:
        if m.get("role") == "tool":
            raw_names[(m.get("tool_call") or {}).get("function")] += 1
    if x.get("pipeline_name", "").replace("/", "_") != lab.split("/")[1] or "/" not in x.get("pipeline_name", ""):
        OUT["h14_sample"][lab.split("/")[0]] += 1
aer_names = Counter(); kinds = Counter()
for p in glob.glob(str(lx_lib.W / "l2-head-j2.partial/aer/*/*.aer.jsonl")):
    for l in open(p):
        r = json.loads(l)
        if r.get("k") == "tool_execution":
            aer_names[r.get("name")] += 1
        if r.get("k") == "activity":
            kinds[str(r.get("name") or r.get("kind"))] += 1
OUT["h12_l2"] = {"sampled_logs": len(sample), "raw_agent_tool_results": raw_tool_results, "raw_backend_trace_calls": raw_bt,
                 "aer_tool_execution": sum(aer_names.values()), "aer_names": dict(aer_names), "raw_names": {str(k): v for k, v in raw_names.items()},
                 "aer_activity_names": dict(kinds)}
OUT = {k: (dict(sorted(v.items())) if isinstance(v, Counter) else v) for k, v in OUT.items()}
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(json.dumps(OUT, indent=0))
