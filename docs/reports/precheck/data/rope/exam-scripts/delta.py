"""Stored vs scratch delta on the same execution ids: counts of executions per differing pointer (no values)."""
import json, sys, re, importlib.util, collections
from pathlib import Path
spec = importlib.util.spec_from_file_location("p9", "tools/analysis2/exam2_p9diff.py")
p9 = importlib.util.module_from_spec(spec); spec.loader.exec_module(p9)
OLD, NEW, OUT = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser(), Path(sys.argv[3])
C = collections.Counter
def rows(p): return {r["ex"]: r for r in (json.loads(x) for x in (p / "executions.jsonl").read_bytes().splitlines() if x)}
old, new = rows(OLD), rows(NEW)
def strip(r): return re.sub(r"#.*$", "", r)
res = {"executions_new": len(new), "matched": 0, "only_new": 0,
       "aer_ptr": C(), "aer_rec_added": C(), "aer_rec_removed": C(), "aer_rule_swaps": C(), "aer_rule_added": C(), "aer_rule_removed": C(),
       "aer_files_differ": 0, "aer_records_old": 0, "aer_records_new": 0,
       "index_ptr": C(), "completeness": C(), "judgement_value_changes": C(), "judgements_new": C(), "judgements_old": C(),
       "sem_type_value_delta": C(), "sem_rule_delta": C(), "sem_ann_old": 0, "sem_ann_new": 0, "sem_header_ptr": C(), "sem_files_differ": 0,
       "prov_stmt_delta": C(), "prov_ev_delta": C(), "prov_files_differ": 0, "prov_bundle_kinds_delta": C(), "ex_with_ptr_examples": {}}
def aer(p):
    d = {}
    for line in p.read_bytes().splitlines():
        if line:
            r = json.loads(line); d[(r.get("k"), r.get("id"))] = r
    return d
def recname(r):
    k = r.get("k")
    if k == "activity": return f"activity:{r.get('name') or r.get('kind')}"
    if k == "judgement": return f"judgement:{r.get('name')}:{r.get('origin')}"
    return f"{k}:{r.get('kind','')}"
for ex, rn in sorted(new.items()):
    ro = old.get(ex)
    if ro is None: res["only_new"] += 1; continue
    res["matched"] += 1
    s = set(); p9.diff({k: v for k, v in ro.items() if k not in ("digests", "paths")}, {k: v for k, v in rn.items() if k not in ("digests", "paths")}, "", "", s)
    for x in s: res["index_ptr"][x] += 1
    res["completeness"][f"{ro.get('completeness')}->{rn.get('completeness')}"] += 1
    a, b = aer(OLD / ro["paths"]["aer"]), aer(NEW / rn["paths"]["aer"])
    res["aer_records_old"] += len(a); res["aer_records_new"] += len(b)
    if (OLD / ro["paths"]["aer"]).read_bytes() != (NEW / rn["paths"]["aer"]).read_bytes(): res["aer_files_differ"] += 1
    ptrs = set(); swaps = set(); radd = set(); rrem = set(); added = C(); removed = C()
    for key in set(a) | set(b):
        if key not in a: added[recname(b[key])] += 1; continue
        if key not in b: removed[recname(a[key])] += 1; continue
        x, y = a[key], b[key]
        if x == y: continue
        ps = set(); p9.diff(x, y, key[0], "", ps); ptrs |= ps
        ro_r = set(map(strip, x.get("rule") or [])); rn_r = set(map(strip, y.get("rule") or []))
        for r in ro_r - rn_r:
            tw = r.replace("@", "_unverified@")
            if tw in rn_r: swaps.add(f"{r} -> twin")
            else: rrem.add(r)
        for r in rn_r - ro_r:
            if r.replace("_unverified@", "@") not in ro_r: radd.add(r)
        if key[0] == "judgement" and x.get("value") != y.get("value"):
            res["judgement_value_changes"][f"{x.get('name')}:{x.get('origin')}:{x.get('value')}->{y.get('value')}"] += 1
    for k, v in added.items(): res["aer_rec_added"][f"{k} x{v}"] += 1
    for k, v in removed.items(): res["aer_rec_removed"][f"{k} x{v}"] += 1
    for p in ptrs: res["aer_ptr"][p] += 1; res["ex_with_ptr_examples"].setdefault(p, ex)
    for p in swaps: res["aer_rule_swaps"][p] += 1
    for p in radd: res["aer_rule_added"][p] += 1
    for p in rrem: res["aer_rule_removed"][p] += 1
    for r in b.values():
        if r.get("k") == "judgement": res["judgements_new"][f"{r.get('name')}:{r.get('origin')}:{r.get('by')}:rev={bool(r.get('revises'))}:{r.get('value')}"] += 1
    for r in a.values():
        if r.get("k") == "judgement": res["judgements_old"][f"{r.get('name')}:{r.get('origin')}:{r.get('by')}:rev={bool(r.get('revises'))}:{r.get('value')}"] += 1
    # SEM
    so = list((ro["paths"].get("sem") or {}).values()); sn = list((rn["paths"].get("sem") or {}).values())
    if so and sn:
        def sem(p):
            L = [json.loads(x) for x in (p).read_bytes().splitlines() if x]
            return L[0], L[1:]
        ho, ao = sem(OLD / so[0]); hn, an = sem(NEW / sn[0])
        hs = set(); p9.diff(ho, hn, "sem_header", "", hs)
        for x in hs: res["sem_header_ptr"][x] += 1
        res["sem_ann_old"] += len(ao); res["sem_ann_new"] += len(an)
        if (OLD / so[0]).read_bytes() != (NEW / sn[0]).read_bytes(): res["sem_files_differ"] += 1
        co = C((x.get("type"), json.dumps(x.get("value"), sort_keys=True)[:60] if not isinstance(x.get("value"), (dict, list)) else "obj", x.get("ev")) for x in ao)
        cn = C((x.get("type"), json.dumps(x.get("value"), sort_keys=True)[:60] if not isinstance(x.get("value"), (dict, list)) else "obj", x.get("ev")) for x in an)
        for k in set(co) | set(cn):
            if co[k] != cn[k]: res["sem_type_value_delta"]["|".join(map(str, k))] += cn[k] - co[k]
        ro_ = C(strip(r) for x in ao for r in x.get("rule") or []); rn_ = C(strip(r) for x in an for r in x.get("rule") or [])
        for k in set(ro_) | set(rn_):
            if ro_[k] != rn_[k]: res["sem_rule_delta"][k] += rn_[k] - ro_[k]
    # PROV
    for specn in rn["paths"].get("prov") or {}:
        pa, pb = OLD / ro["paths"]["prov"][specn]["json"], NEW / rn["paths"]["prov"][specn]["json"]
        if pa.read_bytes() == pb.read_bytes(): continue
        res["prov_files_differ"] += 1
        def stmts(p):
            d = json.loads(p.read_bytes()); c = C(); e = C()
            def bk(name):
                m = re.match(r"xd:bundle\.(core|inf|assess)", name); return m.group(1) if m else "other"
            for sec, v in d.items():
                if sec in ("bundle", "prefix") or not isinstance(v, dict): continue
                c[f"top:{sec}"] += len(v)
            for bn, bv in (d.get("bundle") or {}).items():
                for sec, v in bv.items():
                    if isinstance(v, dict):
                        c[f"{bk(bn)}:{sec}"] += len(v)
                        for st in v.values():
                            if isinstance(st, dict):
                                ev = st.get("apv:evidence") or st.get("apv:evidenceClass")
                                e[f"{bk(bn)}:{ev if isinstance(ev,str) else 'obj' if ev else 'none'}"] += 1
            return c, e
        ca, ea = stmts(pa); cb, eb = stmts(pb)
        for k in set(ca) | set(cb):
            if ca[k] != cb[k]: res["prov_stmt_delta"][k] += cb[k] - ca[k]
        for k in set(ea) | set(eb):
            if ea[k] != eb[k]: res["prov_ev_delta"][k] += eb[k] - ea[k]
out = {k: (dict(sorted(v.items(), key=lambda kv: (-kv[1] if isinstance(kv[1], int) else 0, kv[0]))) if isinstance(v, C) else v) for k, v in res.items()}
OUT.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: v for k, v in out.items() if k != "ex_with_ptr_examples"}, indent=1)[:20000])
