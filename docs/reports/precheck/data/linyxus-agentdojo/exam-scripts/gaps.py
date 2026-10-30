"""linyxus-agentdojo: investigate the flagged cells (counts only, no text).
G1 runs-2 gemini-tacit slack (39/105 attack successes): successes by injection task, by tool_trace_source, with/without
   backend traces; slack successes by IT over all attacked slack cells (CC-10: IT5 membership).
G2 lacuna-runs-1 gemini-tacit travel (57/140 vs paper 89) and lacuna-runs-0 o4-tacit workspace (261/560 vs paper 311):
   per-log features vs the matching TACIT root cell: logs with 0 backend traces, 0 eval_scala calls, tool-error results,
   last message role, median duration, utility by user task; timestamp span.
Usage (repo root): uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/gaps.py OUT.json"""
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lx_lib  # noqa: E402

E = lx_lib.entries(); R = lx_lib.Reader()
rows = [json.loads(l) for l in open(lx_lib.W / "l1-units-head.jsonl")]
G = {"G1": ("runs-2", "openrouter_google_gemini-2.5-pro-tacit", "slack"),
     "G1_ref": ("runs-4", "openrouter_google_gemini-2.5-pro-tacit", "slack"),
     "G2a": ("lacuna-runs-1", "openrouter_google_gemini-2.5-pro-tacit", "travel"),
     "G2a_ref": ("runs-4", "openrouter_google_gemini-2.5-pro-tacit", "travel"),
     "G2b": ("lacuna-runs-0", "openrouter_openai_o4-mini-high-tacit", "workspace"),
     "G2b_ref": ("runs-2", "openrouter_openai_o4-mini-high-tacit", "workspace")}
OUT = {"cells": {}, "slack_successes_by_it": {}}
slack = defaultdict(Counter)
for u in rows:
    f = u["facets"]
    if f["task_kind"] != "user":
        continue
    key = (f["run_set"], f["pipeline_dir"], f["suite"])
    if f["suite"] == "slack" and u["outcomes"]["security"] is True:
        slack[f"{f['run_set']}|{f['pipeline_dir']}"][f["file"]] += 1
    for g, k in G.items():
        if k != key:
            continue
        x = R.load(E[u["label"]]); ms = x.get("messages") or []
        c = OUT["cells"].setdefault(g, {"cell": "|".join(k), "logs": 0, "feat": Counter(), "dur": [], "ts": [], "by_it_sec": Counter(),
                                        "ut_util": Counter(), "prompt_len": Counter()})
        c["logs"] += 1
        calls = [tc for m in ms for tc in (m.get("tool_calls") or [])]
        errs = sum(1 for m in ms if m.get("role") == "tool" and m.get("error"))
        bt = x.get("backend_tool_traces") or []
        F = c["feat"]
        F["utility_true"] += x.get("utility") is True; F["security_true"] += x.get("security") is True
        F["zero_backend_traces"] += not bt; F["zero_tool_calls"] += not calls
        F["logs_with_tool_error"] += errs > 0; F["tool_errors"] += errs
        F["has_secure_output"] += "tacit_secure_output" in x
        F["secure_output_empty"] += x.get("tacit_secure_output") == ""
        F[f"last_role:{ms[-1].get('role') if ms else None}"] += 1
        F[f"src:{x.get('tool_trace_source')}"] += 1
        F["utility_true_zero_backend"] += x.get("utility") is True and not bt
        F["utility_false_zero_backend"] += x.get("utility") is not True and not bt
        sp = next((m for m in ms if m.get("role") == "system"), None)
        c["prompt_len"][hashlib.sha256(json.dumps(sp.get("content"), sort_keys=True).encode()).hexdigest()[:12] if sp else "none"] += 1
        if isinstance(x.get("duration"), (int, float)):
            c["dur"].append(x["duration"])
        c["ts"].append(x.get("evaluation_timestamp") or "")
        if x.get("security") is True:
            c["by_it_sec"][f["file"]] += 1
        c["ut_util"][f["task_dir"]] += x.get("utility") is True
for g, c in OUT["cells"].items():
    c["feat"] = dict(sorted(c["feat"].items())); c["by_it_sec"] = dict(sorted(c["by_it_sec"].items()))
    c["median_duration_s"] = round(statistics.median(c.pop("dur")), 1) if c.get("dur") else None
    ts = sorted(t for t in c.pop("ts") if t); c["ts_span"] = [ts[0], ts[-1]] if ts else None
    c["ut_util"] = dict(sorted(c["ut_util"].items())); c["system_prompt_sha256_12"] = dict(c.pop("prompt_len"))
OUT["slack_successes_by_it"] = {k: dict(sorted(v.items())) for k, v in sorted(slack.items())}
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True)
for g, c in OUT["cells"].items():
    print(g, c["cell"], c["logs"], c["feat"], "dur", c["median_duration_s"], c["ts_span"], "sec_by_it", c["by_it_sec"], "prompts", c["system_prompt_sha256_12"])
print(OUT["slack_successes_by_it"])
