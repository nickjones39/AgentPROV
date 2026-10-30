"""L2 (scratch j2 corpora, our derived AER): CD-24 judgement naming, raw-vs-mapped side_task_success per label,
sample outcome rates per arm with Wilson 95%, and the PR position of side-task successes. Counts only."""
import json, glob, math, re, sys, pathlib, collections as C
W = pathlib.Path.home() / ".agentprov/migration-work/precheck/controlarena-persistent"
PARTS = ["zip-3-001", "zip-3-002", "zip-3-003", "batch-runs", "auditor"]
def wilson(k, n, z=1.959964):
    if not n: return None
    p = k/n; d = 1+z*z/n; c = (p+z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*(c-h), 1), round(100*(c+h), 1)]
out = {}; arms = C.defaultdict(C.Counter); pos = C.Counter(); cd24 = C.Counter(); mism = C.Counter()
for p in PARTS:
    l1 = {}
    for line in (W / f"l1-units-{p}.jsonl").open():
        r = json.loads(line); l1[r["sha256"]] = r
    per_label = C.defaultdict(lambda: [0, 0, []])
    for f in glob.glob(str(W / f"l2-{p}-j2.partial/aer/*/*.aer.jsonl")):
        lines = open(f).read().splitlines(); h = json.loads(lines[0])
        cont = h["artifacts"][0]["origin"].get("container"); lab = h["artifacts"][0]["origin"].get("label", "")
        m = re.match(r"samples/PR(\d+)_", lab); pr = int(m.group(1)) if m else None
        names = C.Counter(); side = None
        for l in lines[1:]:
            r = json.loads(l)
            if r.get("k") != "judgement": continue
            n = r["name"]; names["bare_score" if n == "score" else ("score.<key>" if n.startswith("score.") else ("sample_score" if "generated_by" not in r else "other_event"))] += 1
            if n == "side_task_success.side_task_success": side = r.get("value")
        cd24["executions"] += 1; cd24["with_bare_score"] += names["bare_score"] > 0; cd24["with_score_key"] += names["score.<key>"] > 0; cd24["with_sample_score_dup"] += names["sample_score"] > 0
        u = l1.get(cont); cd24["joined"] += u is not None
        if u is None: continue
        pl = per_label[u["label"]]; pl[0] += 1; pl[1] += side == "C"; pl[2].append((pr, side == "C"))
        st = "+".join(sorted(u.get("unit_facets", {}).get("side_task_name", {}))) or "<none>"
        a = arms[f"{p} | {u['facets'].get('experiment')} | {st}"]; a["n"] += 1; a["C"] += side == "C"
    for lab, (n, c, prs) in per_label.items():
        u = next(r for r in l1.values() if r["label"] == lab)
        raw = u["outcomes"].get("score.side_task_success.side_task_success", {}).get('"C"', 0)
        mism["labels"] += 1; mism["equal"] += raw == c; mism["n_equal_units"] += n == u["n_units"]
        if c:
            last = max(x for x, _ in prs if x is not None)
            for x, s in prs:
                if s:
                    pos["C_at_last_PR" if x == last else "C_before_last_PR"] += 1
                    if "gradual_f3m1" in str(u["facets"].get("experiment")): pos["gradual_f3m1:" + ("last" if x == last else "before_last")] += 1
out["cd24"] = dict(cd24); out["raw_vs_mapped_side_task_C_per_label"] = dict(mism); out["C_position"] = dict(pos)
out["arms"] = {k: {"n": v["n"], "C": v["C"], "rate": round(100*v["C"]/v["n"], 1), "wilson": wilson(v["C"], v["n"])} for k, v in sorted(arms.items())}
json.dump(out, open(sys.argv[1], "w"), indent=1); print(json.dumps(out, indent=None))
