"""credleak-p15b follow-ups to pop.py: extcanary in-harness flags by technique, run overlap by the census rule
(next run's first turn before this run's first turn + durationMs), per-run fingerprint groups vs tool calls, and the
origin of each named account path (first seen in agent-authored text or in environment output). Counts and digests only.
Usage: python -I extra.py <exam-scripts dir> <worktree root> <out.json>
"""
import sys, re, json, os, hashlib, collections
from datetime import datetime, timedelta
sys.path.insert(0, sys.argv[1]); from rawlib import cells
ROOT, OUT = sys.argv[2], sys.argv[3]
sys.path.insert(0, f"{ROOT}/tools/precheck"); from l1_scan import GENERIC_ACCOUNTS
C = collections.Counter
ACC = {"users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"), "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")}
def ts(s): return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")
def strs(o):
    if isinstance(o, str): yield o
    elif isinstance(o, dict):
        for v in o.values(): yield from strs(v)
    elif isinstance(o, list):
        for v in o: yield from strs(v)
ext = C(); ext_n = C(); ov = C(); calls = {}; first = {}
acc_origin = collections.defaultdict(C)
for label, d in cells():
    f = label.rsplit("/", 1)[1]; tech = d.get("technique")
    prev = None
    for i, r in enumerate(d.get("runs", [])):
        turns = r.get("turns", [])
        calls[(label, f"/runs/{i}")] = sum(len(t.get("toolCalls") or []) for t in turns)
        if f.startswith("extcanary__"):
            ext_n[tech] += 1
            for k in ("exfiltrationDetected", "hijackSucceeded"):
                ext[f"{tech}:{k}:{r.get(k)}"] += 1
        if turns:
            t0 = ts(turns[0]["timestamp"])
            if prev is not None:
                ov["pairs"] += 1; ov["overlap_first_turn_plus_durationMs"] += t0 < prev
            prev = t0 + timedelta(milliseconds=r.get("durationMs") or 0)
        # account origin: order of appearance within the run (agent text/inputs vs tool output / user message)
        seen = {}
        for t in turns:
            seq = [("user_message", t.get("userMessage") or ""), ("assistant", t.get("assistantResponse") or "")]
            for c in t.get("toolCalls") or []:
                seq += [("tool_input", s) for s in strs(c.get("input"))] + [("tool_output", c.get("output") or "")]
            for src, s in seq:
                for kind, rx in ACC.items():
                    for m in rx.finditer(s):
                        n = m.group(1)
                        if n.lower() in GENERIC_ACCOUNTS: continue
                        key = f"{kind}:{hashlib.sha256(n.encode('utf-8','surrogatepass')).hexdigest()[:12]}"
                        if key not in seen: seen[key] = src; acc_origin[key][f"first_in:{src}"] += 1
        # NOTE: assistantResponse is recorded per turn after the calls; ordering inside a turn is approximate.
fp = collections.defaultdict(list)
for line in open(os.path.expanduser("~/.agentprov/migration-work/precheck/_fp/credleak-p15b.head.jsonl")):
    x = json.loads(line); fp[x["fp"]].append((x["label"], x.get("unit")))
groups = [g for g in fp.values() if len(g) > 1]
fpres = dict(groups=len(groups), units=sum(map(len, groups)), unresolved=sum(1 for g in groups for u in g if u not in calls),
             groups_with_a_call_run=sum(1 for g in groups if any(calls.get(u, 0) for u in g)),
             runs_with_calls_in_groups=sum(1 for g in groups for u in g if calls.get(u, 0)))
out = dict(format="credleak-p15b-exam-extra/1", extcanary_runs=dict(ext_n), extcanary_flags=dict(sorted(ext.items())),
           overlap=dict(ov), fingerprints=fpres, account_first_seen={k: dict(v) for k, v in sorted(acc_origin.items())})
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
print(json.dumps(out, indent=0, sort_keys=True))
