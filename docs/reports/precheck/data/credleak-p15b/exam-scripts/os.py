"""credleak-p15b outcome sanity. (1) L2 mapping identity: AER outcomes of the sampled arms (l2-head.json) vs the raw
flags of the same labels (L1 rows). (2) Sample vs population per arm (model|scenario) with the README s4 gap rule.
(3) csv detail: missing v2 key, `errored` column definition, unmatched keys, payloadDelivered diff. Counts only.
Usage (worktree root): python -I os.py <exam-scripts dir> <out.json>
"""
import sys, json, os, csv, io, collections
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson
from rawlib import cells, members
W = os.path.expanduser("~/.agentprov/migration-work/precheck/credleak-p15b")
P = "docs/reports/precheck/data/credleak-p15b"
L2 = json.load(open(f"{P}/l2-head.json")); S = set(json.load(open(f"{P}/l2-sample-head.json"))["labels"])
M = ("hijackSucceeded", "exfiltrationDetected", "agentDetected", "displayedToUser")
pop = collections.defaultdict(collections.Counter); smp = collections.defaultdict(collections.Counter)
errdef = collections.Counter(); csvkey = collections.defaultdict(collections.Counter)
for label, d in cells():
    arm = f"{d['model']}|C4-baseline|{d['scenario']}"
    sec = label.split("/")[1]; mcsv = d["model"].replace("eu.anthropic.claude-", "anthropic.").replace("claude-", "")
    k = (sec, mcsv, d["technique"], d["scenario"]); f = label.rsplit("/", 1)[1]
    for r in d["runs"]:
        for tgt in ([pop[arm], smp[arm]] if label in S else [pop[arm]]):
            tgt["n"] += 1
            for m in M: tgt[m] += r.get(m) is True
        nc = sum(len(t.get("toolCalls") or []) for t in r["turns"])
        empty = all(not (t.get("assistantResponse") or "").strip() for t in r["turns"]) and nc == 0
        c = csvkey[k]; c["N"] += 1; c["N_noadd"] += not f.startswith("addendum-")
        c["ie"] += r.get("invocationError") is True; c["empty"] += empty; c["nocall"] += nc == 0
        c["ie_or_empty"] += (r.get("invocationError") is True) or empty
        c["ie_or_nocall"] += (r.get("invocationError") is True) or nc == 0
        c["tc_none"] += r.get("t0Completed") is None
        c["pd"] += r.get("payloadDelivered") is True and r.get("invocationError") is not True
        c["pd_all"] += r.get("payloadDelivered") is True
# (1) mapping identity
ident = collections.Counter(); mism = []
for arm, a in L2["outcomes"]["arms"].items():
    s = smp.get(arm)
    if s is None: ident["arm_missing_in_raw"] += 1; continue
    for m in M:
        if m in a:
            ok = a[m]["n"] == s["n"] and a[m]["k"] == s[m]; ident["ok" if ok else "mismatch"] += 1
            if not ok: mism.append((arm, m, a[m]["k"], a[m]["n"], s[m], s["n"]))
ident["sample_arms_raw"] = len(smp); ident["l2_arms"] = len(L2["outcomes"]["arms"])
ident["l2_runs"] = sum(a[M[0]]["n"] for a in L2["outcomes"]["arms"].values() if M[0] in a)
# (2) sample vs population gap rule (arms with >= 20 sampled runs)
flags = []; n20 = 0
for arm, s in smp.items():
    if s["n"] < 20: continue
    n20 += 1
    for m in M:
        p = pop[arm][m] / pop[arm]["n"]; r = s[m] / s["n"]; lo, hi = wilson(s[m], s["n"])
        gap = abs(r - p) * 100; excl = max(lo - p, p - hi, 0) * 100
        if gap > 15 or excl > 5:
            flags.append(dict(arm=arm, metric=m, n=s["n"], k=s[m], rate=round(r, 4), wilson95=[round(lo, 4), round(hi, 4)],
                              pop_n=pop[arm]["n"], pop_rate=round(p, 4), gap_pp=round((r - p) * 100, 1),
                              cells_pop=None))
# pooled sample vs population by metric
pooled = {m: dict(sample=[sum(s[m] for s in smp.values()), sum(s["n"] for s in smp.values())],
                  population=[sum(s[m] for s in pop.values()), sum(s["n"] for s in pop.values())]) for m in M}
# (3) csv detail
cs = {}
for lbl, data in members(lambda l: l in ("p15b-run-data/per-cell-counts.csv", "p15b-run-data/per-cell-counts-v2.csv")):
    rows = {tuple(r[:4]): r for r in csv.reader(io.StringIO(data.decode("utf-8"), newline="")) if len(r) == 10 and r[0] and r[0] != "section"}
    errm = collections.Counter(); unm = []; pdd = []
    for k, r in rows.items():
        c = csvkey.get(k)
        if not c: continue
        N, er = int(r[4]), int(r[9])
        for dfn in ("ie", "empty", "nocall", "ie_or_empty", "ie_or_nocall", "tc_none"): errm[dfn] += c[dfn] == er
        errm["keys"] += 1
        if N not in (c["N"], c["N_noadd"]): unm.append(dict(key="|".join(k), csv_N=N, raw_N=c["N"]))
        if int(r[8]) not in (c["pd"], c["pd_all"]): pdd.append(dict(key="|".join(k), csv=int(r[8]), raw=c["pd"], raw_all=c["pd_all"]))
    cs[lbl] = dict(errored_definition_matches=dict(errm), N_unmatched=unm, pd_diff=pdd,
                   roster_keys_without_row=sorted("|".join(k) for k in csvkey if k not in rows and not k[1].startswith(("anthropic.", "glm-5", "minimax", "global."))))
out = dict(format="credleak-p15b-exam-os/1", mapping_identity=dict(ident), mapping_mismatches=mism[:20],
           gap_rule=dict(arms_ge20=n20, flagged=len(flags), flags=flags), pooled=pooled, csv=cs)
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True)
print(json.dumps({k: v for k, v in out.items() if k != "gap_rule"}, indent=0, sort_keys=True)[:4000]); print("gap", n20, len(flags))
