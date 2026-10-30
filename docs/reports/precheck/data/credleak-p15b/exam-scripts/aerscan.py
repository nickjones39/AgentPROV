"""credleak-p15b L2: per execution of the scratch corpus, does its AER/SEM/PROV hold (a) a [withhold] rule hit, (b) an
l2_check secret pattern, (c) a named account path (by digest class)? Executions with (b) but not (a) would be released
with a secret-like string; (c) gives the account-path exposure. Also: sampled runs with invocationError (raw), and the
withhold-rule count of the not-selected collector-log member. Counts and digests only.
Usage (worktree root): python -I aerscan.py <exam-scripts dir> <out.json>
"""
import sys, os, re, json, hashlib, collections
sys.path.insert(0, "tools/precheck"); sys.path.insert(0, sys.argv[1])
from l2_check import SECRET_PATTERNS, ACCOUNT_PATH
from l1_scan import GENERIC_ACCOUNTS
from rawlib import members, cells
W = os.path.expanduser("~/.agentprov/migration-work/precheck/credleak-p15b/l2-head-j2.partial")
WH = [re.compile(p.encode()) for p in ("CANARY[^_]", "[^_/]CANARY", "AKIA[0-9A-Z]{16}", r"sk-[A-Za-z0-9_\-]{20,256}")]
NAMED = re.compile(rb"/(?:home|Users)/([^/\s\"'<>\\]{1,64})/")
c = collections.Counter(); dg = collections.Counter(); kinds = collections.Counter()
for line in open(f"{W}/executions.jsonl"):
    row = json.loads(line); paths = [row["paths"]["aer"]] + list(row["paths"]["sem"].values()) + \
        [v["json"] for v in row["paths"]["prov"].values()]
    blob = b"".join(open(f"{W}/{p}", "rb").read() for p in paths)
    wh = any(rx.search(blob) for rx in WH); sec = [n for n, p in SECRET_PATTERNS.items() if p.search(blob)]
    acc = set()
    for m in NAMED.finditer(blob):
        n = m.group(1).decode("utf-8", "replace")
        if n.lower() not in GENERIC_ACCOUNTS: acc.add(hashlib.sha256(m.group(1)).hexdigest()[:12])
    c["executions"] += 1; c["withhold_hit"] += wh; c["secret_pattern_hit"] += bool(sec)
    c["secret_no_withhold"] += bool(sec) and not wh
    for n in sec:
        if not wh: kinds[n] += 1
    c["named_account_exec"] += bool(acc); c["named_account_exec_released"] += bool(acc) and not wh
    for a in acc: dg[a] += 1
S = set(json.load(open("docs/reports/precheck/data/credleak-p15b/l2-sample-head.json"))["labels"])
ie = sum(1 for l, d in cells() if l in S for r in d["runs"] if r.get("invocationError") is True)
log = {}
for l, data in members(lambda l: l.startswith("p15b-run-data/03-egress-axis/external-canary-collector-log/")):
    log[l.rsplit(".", 1)[-1] + ":" + str(len(log))] = sum(len(rx.findall(data)) > 0 for rx in WH)
out = dict(counts=dict(c), released_secret_pattern_kinds=dict(kinds), named_account_digests_exec=dict(dg),
           sampled_invocation_error_runs=ie, collector_log_members_rules_hit=log)
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
