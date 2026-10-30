"""CC-10 (#168) on ceferisbarov-agentdojo: slack injection_task_5 security true although a goal membership call
(invite_user_to_slack / add_user_to_channel / remove_user_from_slack) never executed without an error. No defence in
this corpus, so "denied" cannot occur; failed calls can. Counts only. Usage: as extra.py."""
import hashlib, json, os, subprocess, sys
from collections import Counter
from agentprov.adapters.runner.importer import git_blob_sha1
from agentprov.ingest.loaders import strict_json_loads
UNITS, BARE, COMMIT, OUT = sys.argv[1], os.path.expanduser(sys.argv[2]), sys.argv[3], sys.argv[4]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {
    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
GOAL = ("invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack")
tree = {}
for rec in subprocess.run(["git", *H, "--git-dir", BARE, "ls-tree", "-r", "-z", COMMIT, "reruns/"], capture_output=True,
                          env=ENV, check=True).stdout.split(b"\0"):
    if rec:
        meta, path = rec.split(b"\t", 1); tree[path.decode()] = meta.split()[2].decode()
p = subprocess.Popen(["git", *H, "--git-dir", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, env=ENV)
c = Counter(); sl = Counter()
for ln in open(UNITS, encoding="utf-8"):
    row = json.loads(ln); f = row["facets"]
    if not (f["suite"] == "slack" and f["task_kind"] == "user") or row["outcomes"]["security"] is None:
        continue
    sl["slack_attacked"] += 1; sl["slack_success"] += bool(row["outcomes"]["security"])
    if f["file"] != "injection_task_5":
        continue
    oid = tree[row["label"]]
    p.stdin.write(oid.encode() + b"\n"); p.stdin.flush()
    h = p.stdout.readline().split(); d = p.stdout.read(int(h[2])); p.stdout.read(1)
    assert git_blob_sha1(d) == oid and hashlib.sha256(d).hexdigest() == row["sha256"]
    x = strict_json_loads(d)
    calls, res = [], {}
    for m in x.get("messages") or []:
        calls.extend(m.get("tool_calls") or [])
        if m.get("role") == "tool":
            res[m.get("tool_call_id")] = m.get("error")
    ok = {g: any(tc.get("function") == g and tc.get("id") in res and res[tc.get("id")] is None for tc in calls)
          for g in GOAL}
    att = {g: any(tc.get("function") == g for tc in calls) for g in GOAL}
    c["it5_n"] += 1
    if x.get("security"):
        c["it5_true"] += 1
        c["it5_true_all_goal_calls_executed_ok"] += all(ok.values())
        c["it5_true_some_goal_call_never_ok"] += not all(ok.values())
        c["it5_true_some_goal_call_never_attempted"] += not all(att.values())
    else:
        c["it5_false_all_goal_calls_executed_ok"] += all(ok.values())
p.stdin.close(); p.wait()
out = {"it5": dict(c), "slack": dict(sl)}
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True); print(json.dumps(out))
