"""DL-1: record-level AER/SEM diff, stored corpus vs scratch import, same execution ids. Counts, pointers, rule ids only."""
import json, sys, collections, re, os
OLD, NEW, OUT = (os.path.expanduser(x) for x in sys.argv[1:4])

def idx(root):
    return {r["ex"]: r for r in (json.loads(x) for x in open(f"{root}/executions.jsonl") if x.strip())}

def recs(path):
    out = {}
    for line in open(path, "rb"):
        if line.strip():
            r = json.loads(line)
            out[(r.get("k"), r.get("id"))] = r
    return out

def rid(c):  # rule citation -> rule id@ver (drop pointer)
    return c.split("#", 1)[0]

def norm(p):
    return re.sub(r"/\d+", "/*", p)

oi, ni = idx(OLD), idx(NEW)
common = sorted(set(ni) & set(oi))
ex_by = collections.defaultdict(set)   # signature -> executions
rule_pairs = collections.Counter(); ev_pairs = collections.Counter(); evf_pairs = collections.Counter()
rec_only = collections.Counter(); field_changes = collections.Counter(); unk_added = collections.Counter(); unk_removed = collections.Counter()
actor_changes = collections.Counter(); completeness = collections.Counter(); issues_delta = collections.Counter(); status = collections.Counter()
header = collections.Counter()
for ex in common:
    o, n = oi[ex], ni[ex]
    completeness[(o.get("completeness"), n.get("completeness"))] += 1
    status[(o.get("status"), n.get("status"))] += 1
    for code in set(o.get("issues") or []) ^ set(n.get("issues") or []):
        issues_delta[("+" if code in (n.get("issues") or []) else "-") + code] += 1
    ro, rn = recs(f"{OLD}/{o['paths']['aer']}"), recs(f"{NEW}/{n['paths']['aer']}")
    for key in set(ro) ^ set(rn):
        sig = f"record_{'only_new' if key in rn else 'only_old'}:{key[0]}"
        rec_only[sig] += 1; ex_by[sig].add(ex)
        if key in rn and key[0] == "activity":
            ex_by["activity_new:" + str(rn[key].get("type"))].add(ex)
    for key in set(ro) & set(rn):
        a, b = ro[key], rn[key]
        if a == b:
            continue
        k = key[0]
        for f in set(a) | set(b):
            if a.get(f) == b.get(f):
                continue
            if f == "rule":
                ra = a.get(f) if isinstance(a.get(f), list) else [a.get(f)] if a.get(f) else []
                rb = b.get(f) if isinstance(b.get(f), list) else [b.get(f)] if b.get(f) else []
                sa, sb = {rid(x) for x in ra}, {rid(x) for x in rb}
                for x in sorted(sa - sb):
                    for y in sorted(sb - sa) or ["<none>"]:
                        pass
                sig = f"{k}/rule: -{sorted(sa - sb)} +{sorted(sb - sa)}"
                if sa == sb:
                    sig = f"{k}/rule: pointer-only"
                rule_pairs[sig] += 1; ex_by[f"{k}/rule"].add(ex)
            elif f == "ev":
                ev_pairs[f"{k}/ev {a.get(f)}->{b.get(f)}"] += 1; ex_by[f"{k}/ev"].add(ex)
            elif f == "evf":
                ea, eb = a.get(f) or {}, b.get(f) or {}
                for p in set(ea) | set(eb):
                    if ea.get(p) != eb.get(p):
                        evf_pairs[f"{k}/evf{norm(p)} {ea.get(p)}->{eb.get(p)}"] += 1; ex_by[f"{k}/evf{norm(p)}"].add(ex)
            elif f == "unk":
                ua, ub = a.get(f) or {}, b.get(f) or {}
                for p in set(ub) - set(ua):
                    unk_added[f"{k}/unk{norm(p)}={ub[p]}"] += 1; ex_by[f"{k}/unk{norm(p)}:added"].add(ex)
                for p in set(ua) - set(ub):
                    unk_removed[f"{k}/unk{norm(p)}={ua[p]}"] += 1; ex_by[f"{k}/unk{norm(p)}:removed"].add(ex)
                for p in set(ua) & set(ub):
                    if ua[p] != ub[p]:
                        unk_added[f"{k}/unk{norm(p)} {ua[p]}->{ub[p]}"] += 1; ex_by[f"{k}/unk{norm(p)}:changed"].add(ex)
            elif k == "execution" and f in ("profile", "rules"):
                header[f"{f}: {json.dumps(a.get(f), sort_keys=True)[:120]} -> {json.dumps(b.get(f), sort_keys=True)[:120]}"] += 1
                ex_by[f"execution/{f}"].add(ex)
            elif f in ("actor", "by"):
                actor_changes[f"{k}/{f} {a.get(f)}->{b.get(f)}"] += 1; ex_by[f"{k}/{f}"].add(ex)
            else:
                field_changes[f"{k}/{f}"] += 1; ex_by[f"{k}/{f}"].add(ex)
    # SEM: compare annotation types (different profiles: suites@1 vs @3)
    so = list((o["paths"].get("sem") or {}).values()); sn = list((n["paths"].get("sem") or {}).values())
    if so and sn:
        def ann(path):
            c = collections.Counter()
            for line in open(path, "rb"):
                if line.strip():
                    r = json.loads(line); c[f"{r.get('k')}:{r.get('type') or r.get('ann') or r.get('name')}"] += 1
            return c
        ca, cb = ann(f"{OLD}/{so[0]}"), ann(f"{NEW}/{sn[0]}")
        for t in set(ca) | set(cb):
            if ca[t] != cb[t]:
                ex_by[f"sem {t} {'+' if cb[t] > ca[t] else '-'}"].add(ex)
out = {"executions_compared": len(common), "only_new": len(set(ni) - set(oi)),
       "completeness_old_new": {f"{a}->{b}": c for (a, b), c in completeness.items()},
       "status_old_new": {f"{a}->{b}": c for (a, b), c in status.items()},
       "index_issue_codes_delta": dict(issues_delta),
       "header": dict(header), "records_only": dict(rec_only),
       "rule_changes": dict(rule_pairs.most_common()), "ev_changes": dict(ev_pairs.most_common()), "evf_changes": dict(evf_pairs.most_common()),
       "unk_changes_added": dict(unk_added.most_common()), "unk_removed": dict(unk_removed.most_common()),
       "actor_changes": dict(actor_changes.most_common()), "other_field_changes": dict(field_changes.most_common()),
       "executions_per_signature": {k: len(v) for k, v in sorted(ex_by.items(), key=lambda kv: -len(kv[1]))}}
json.dump(out, open(OUT, "w"), indent=1)
for k, v in out.items():
    if isinstance(v, dict):
        print("##", k, len(v))
        for kk, vv in list(v.items())[:60]:
            print("   ", vv, kk[:230])
    else:
        print("##", k, v)
