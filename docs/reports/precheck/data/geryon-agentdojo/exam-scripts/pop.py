"""geryon-agentdojo population pass over the 3,179 selected logs (raw, through agentprov.ingest; counts only).
Usage: pop.py EXAMDIR OUT.json"""
import sys, json, re
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[1])
import gx_lib
from pathlib import Path
W = Path.home() / ".agentprov/migration-work/precheck/geryon-agentdojo"
L1 = {json.loads(l)["label"]: json.loads(l) for l in open(W / "l1-units-head.jsonl")}
E = gx_lib.entries(); R = gx_lib.Reader()
DENY = re.compile(r"^ValidationError: The tool '[A-Za-z0-9_]+' is not allowed\.\. Please try other tools or arguments and continue to finish the user task: .*$", re.S)
DENY_NOS = re.compile(r"^ValidationError: The tool '[A-Za-z0-9_]+' is not allowed\.\. Please try other tools or arguments and continue to finish the user task: .*$")
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
GOAL5 = {"invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack"}
rows = []
agg = defaultdict(Counter)
for label in sorted(L1):
    u = L1[label]; f = u["facets"]
    v = R.load(E[label])
    ms = v.get("messages") or []
    rs, ls = f["model_dir"].split("/")
    m = re.match(r"logs-(\w+)-([AB])-r(\d)", ls)
    suite, cond, rep = m.group(1), m.group(2), int(m.group(3))
    last = ms[-1] if ms else None
    final_null = isinstance(last, dict) and last.get("role") == "assistant" and "content" in last and last["content"] is None
    final_calls = len(last.get("tool_calls") or []) if isinstance(last, dict) and last.get("role") == "assistant" else 0
    den = 0; den_dotall_only = 0; schema_err = 0; other_err = 0; tool_err = 0
    ph_present = 0; ph_nonnull = 0
    calls_by_id = {}
    goal_calls = 0; goal_denied = 0
    home_hits = 0; home_generic = 0; home_in_prior_text = 0
    seen_text = []
    for i, x in enumerate(ms):
        if not isinstance(x, dict):
            continue
        if x.get("role") == "assistant":
            for c in x.get("tool_calls") or []:
                if "placeholder_args" in c:
                    ph_present += 1
                    ph_nonnull += c["placeholder_args"] is not None
                for k, a in (c.get("args") or {}).items():
                    if isinstance(a, str):
                        for mm in HOME.finditer(a):
                            home_hits += 1
                            home_generic += mm.group(1).lower() in gx_lib.l1_scan.GENERIC_ACCOUNTS
                            home_in_prior_text += any(mm.group(0) in t for t in seen_text)
        if x.get("role") == "tool":
            err = x.get("error")
            fn = (x.get("tool_call") or {}).get("function")
            if err not in (None, ""):
                tool_err += 1
                if isinstance(err, str) and DENY_NOS.match(err):
                    den += 1
                elif isinstance(err, str) and DENY.match(err):
                    den_dotall_only += 1
                elif isinstance(err, str) and "Failed validating" in err:
                    schema_err += 1
                else:
                    other_err += 1
            if fn in GOAL5:
                goal_calls += 1
                goal_denied += bool(isinstance(err, str) and DENY.match(err))
        c = x.get("content")
        if isinstance(c, str):
            seen_text.append(c)
    trailing = final_calls if final_null or (isinstance(last, dict) and last.get("role") == "assistant") else 0
    r = dict(label=label, run_set=rs, logset=ls, suite=suite, cond=cond, rep=rep, model=f["pipeline_dir"], kind=f["task_kind"],
             ut=f["task_dir"], it=f["file"], utility=u["outcomes"]["utility"], security=u["outcomes"]["security"],
             final_role=(last or {}).get("role") if isinstance(last, dict) else None, final_null=final_null, final_calls=final_calls,
             denials=den, denials_dotall_only=den_dotall_only, schema_errors=schema_err, other_tool_errors=other_err, tool_errors=tool_err,
             ph_present=ph_present, ph_nonnull=ph_nonnull, goal5_calls=goal_calls, goal5_denied=goal_denied,
             home_hits=home_hits, home_generic=home_generic, home_in_prior_text=home_in_prior_text, fp=u["fp"], n_msgs=len(ms),
             error_present=u["outcomes"]["error_present"], variant=u["variant"])
    rows.append(r)
json.dump(rows, open(sys.argv[2], "w"))
print(len(rows))
