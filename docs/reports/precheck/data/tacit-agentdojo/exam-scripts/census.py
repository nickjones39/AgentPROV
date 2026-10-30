"""Raw census of tacit-agentdojo head through agentprov.ingest. Counts and labels only (no content, no names)."""
import collections as co, datetime as dt, json, os, re, subprocess, sys, tomllib
from agentprov.ingest.loaders import strict_json_loads
REPO = sys.argv[1]; OUT = sys.argv[2]
BARE = os.path.expanduser("~/.agentprov/staging/10c/tacit/Tacit.git"); C = "995692d3cd42c32e08cf0db8a5fae55fec272f1a"
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
TOOLS = tomllib.load(open(f"{REPO}/src/agentprov/adapters/agentdojo/semantics/agentdojo.suites-2/suite_tools.toml", "rb"))["versions"]["v1.2.2"]["suites"]
TOOLS = {k: set(v) for k, v in TOOLS.items()}
rows = [json.loads(l) for l in open(os.path.expanduser("~/.agentprov/migration-work/precheck/tacit-agentdojo/l1-units-head.jsonl"))]
labels = [r["label"] for r in rows]
# batch read blobs
p = subprocess.Popen(["git", "-C", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=ENV)
def read(label):
    p.stdin.write(f"{C}:{label}\n".encode()); p.stdin.flush()
    head = p.stdout.readline().split(); n = int(head[2]); data = p.stdout.read(n); p.stdout.read(1); return data
def text_of(m):
    c = m.get("content")
    if c is None: return None
    if isinstance(c, str): return c
    return "".join(b.get("content") or "" for b in c if isinstance(b, dict) and b.get("type") == "text")
R = co.defaultdict(co.Counter); ts = co.defaultdict(list); per = {}
MEMBER = {"invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack"}
it5 = []
for label in labels:
    d = strict_json_loads(read(label)); parts = label.split("/"); model, pipe, suite, ut, att, f = parts[2:8]; f = f[:-5]
    key = f"{model}|{suite}|{att}"
    R["benchmark_version"][d.get("benchmark_version")] += 1; R["package"][d.get("agentdojo_package_version")] += 1
    R["error_nonnull"][d.get("error") is not None] += 1; R["pipeline_name"][f"{pipe}:{d.get('pipeline_name')}"] += 1
    R["attack_type"][f"{att}:{d.get('attack_type')}"] += 1
    R["suite_agrees"][d.get("suite_name") == suite] += 1; R["ut_agrees"][d.get("user_task_id") == ut] += 1
    inj = d.get("injection_task_id")
    R["inj_agrees"][(inj is None and f == "none") or inj == f] += 1
    if att == "none" and inj is not None: R["benign_with_inj"][True] += 1
    if ut.startswith("injection_task"): R["prepass_logs"][True] += 1
    msgs = d["messages"]; R["roles_first2"][f"{msgs[0]['role']},{msgs[1]['role']}"] += 1
    if msgs[0]["role"] == "system": R["sysprompt_len"][len(text_of(msgs[0]) or "")] += 1
    try: t = dt.datetime.fromisoformat(d["evaluation_timestamp"]); ts[(model, suite, att)].append((t, label))
    except Exception: R["ts_bad"][True] += 1
    # tool calls
    calls = []; more_tags = 0; null_ids = 0; ids = co.Counter(); tag_only = 0; ph = co.Counter()
    for i, m in enumerate(msgs):
        if m["role"] == "assistant":
            tcs = m.get("tool_calls") or []
            txt = text_of(m) or ""
            if "<function=" in txt and not tcs:
                tag_only += 1; R["tag_only_final"][i == len(msgs) - 1] += 1; R["tag_only_by_stratum"][key] += 1
                R["tag_only_logs_outcome"][f"{att}:u={d.get('utility')}:s={d.get('security')}"] += 1
            if "<function=" in txt and tcs and txt.count("<function=") > len(tcs): R["more_tags_than_calls_turns"][model] += 1; more_tags += 1
            if "<function=" in txt: R["turns_with_tag"][model] += 1
            if "<tool_call>" in txt and not tcs: R["qwen_style_tag_no_call"][model] += 1
            for tc in tcs:
                calls.append((i, tc)); ph["null" if tc.get("placeholder_args") is None else "set"] += 1
                if tc.get("id") is None: null_ids += 1
                else: ids[tc["id"]] += 1
    R["null_ids_by_model"][model] += null_ids; R["logs_with_null_ids_by_model"][model] += bool(null_ids)
    R["dup_ids_logs"][any(v > 1 for v in ids.values())] += 1
    R["tag_only_turns_by_model"][model] += tag_only; R["placeholder_args"].update(ph)
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    R["tool_msgs_with_error"]["n"] += sum(1 for m in tool_msgs if m.get("error"))
    R["tool_msgs"]["n"] += len(tool_msgs)
    # off-set tool names and their result errors
    for m in tool_msgs:
        fn = (m.get("tool_call") or {}).get("function")
        if fn is not None and fn not in TOOLS[suite]:
            R["offset_tool_results"]["error" if m.get("error") else "no_error"] += 1
            R["offset_trailing_slash"][fn.endswith("/")] += 1
            R["offset_by_model"][model] += 1
    for i, tc in calls:
        if tc["function"] not in TOOLS[suite]: R["offset_calls"]["n"] += 1; R["offset_calls_slash"][tc["function"].endswith("/")] += 1; R["offset_calls_by_model"][model] += 1
    # unexecuted trailing calls
    last = msgs[-1]
    if last["role"] == "assistant" and last.get("tool_calls"): R["trailing_unexecuted_logs"][model] += 1; R["trailing_unexecuted_calls"]["n"] += len(last["tool_calls"])
    # final answer
    fa = [m for m in msgs if m["role"] == "assistant"]
    if last["role"] == "assistant" and not last.get("tool_calls"):
        t = text_of(last)
        c = last.get("content")
        if c is None: R["final_content_none"][model] += 1
        elif t.strip() == "": R["final_empty_text"][model] += 1; R["final_empty_blocks"][f"{len(c) if isinstance(c, list) else 'str'}"] += 1; R["final_empty_outcome"][f"{att}:u={d.get('utility')}:s={d.get('security')}"] += 1
    if last["role"] != "assistant": R["last_role_not_assistant"][last["role"]] += 1
    # H12 slack IT5
    if suite == "slack" and f == "injection_task_5" and d.get("security") is True:
        bad = [m for m in tool_msgs if (m.get("tool_call") or {}).get("function") in MEMBER and m.get("error")]
        exe = [m for m in tool_msgs if (m.get("tool_call") or {}).get("function") in MEMBER and not m.get("error")]
        it5.append({"label": label, "member_calls_ok": len(exe), "member_calls_err": len(bad)})
    per[label] = {"more_tags": more_tags, "null_ids": null_ids, "tag_only_final": tag_only, "trailing_unexec": int(last["role"] == "assistant" and bool(last.get("tool_calls"))), "empty_final": int(last["role"] == "assistant" and not last.get("tool_calls") and last.get("content") is not None and (text_of(last) or "").strip() == ""), "offset_calls": sum(1 for _i, tc in calls if tc["function"] not in TOOLS[suite])}
p.stdin.close()
# H9 / H3
order = {}
for (model, suite, att), v in ts.items():
    v.sort(); order[f"{model}|{suite}|{att}"] = {"min": v[0][0].isoformat(), "max": v[-1][0].isoformat(), "n": len(v), "max_label": v[-1][1].split("/", 2)[2]}
viol = {}
for model in ("llama3.1-8b-instruct", "qwen3-4b-instruct"):
    for s in ("banking", "slack", "travel", "workspace"):
        b = max(t for t, _ in ts[(model, s, "none")]); a = [t for t, _ in ts[(model, s, "important_instructions")] if t < b]
        viol[f"{model}|{s}"] = len(a)
allts = [t for v in ts.values() for t, _ in v]
out = {k: dict(v) for k, v in R.items()}
out["ts_range"] = [min(allts).isoformat(), max(allts).isoformat()]; out["ts_by_cell"] = order; out["attacked_before_last_benign"] = viol
out["slack_it5_successes"] = it5; out["n_logs"] = len(labels)
json.dump({k: v for k, v in per.items() if any(v.values())}, open(OUT.replace(".json", "-labels.json"), "w"), indent=0, sort_keys=True)
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True, default=str)
print(json.dumps(out, indent=1, sort_keys=True, default=str))
