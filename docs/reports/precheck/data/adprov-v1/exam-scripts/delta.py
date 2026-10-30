"""Delta of a scratch sample vs the stored corpus on the same execution ids (counts and labels only)."""
import json, re, sys, collections
from pathlib import Path
OLD, NEW, OUT = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser(), Path(sys.argv[3])
def index(root): return {r['ex']: r for r in (json.loads(l) for l in (root/'executions.jsonl').read_text().splitlines() if l)}
oi, ni = index(OLD), index(NEW)
C = collections.Counter
res = collections.defaultdict(C)
exs_with = collections.defaultdict(set)
def rid(r): return re.sub(r'#.*$', '', r)
def recs(path): return [json.loads(l) for l in path.read_text().splitlines() if l]
def bkind(b):
    return b.split('.')[1] if b.startswith('xd:bundle.') else b
for ex, n in sorted(ni.items()):
    o = oi[ex]
    # ---- index row
    for k in sorted(set(n) | set(o)):
        if k in ('digests', 'paths', 'stages'): continue
        if n.get(k) != o.get(k):
            v = (str(o.get(k))[:40], str(n.get(k))[:40]) if k in ('profile', 'status', 'completeness') else ('changed',)
            res['index'][(k,) + v] += 1; exs_with['index:' + k].add(ex)
    if n.get('issues') != o.get('issues'):
        res['index'][('issues_codes_changed',)] += 1
    st_o = {k: (v if isinstance(v, str) else json.dumps(v, sort_keys=True)) for k, v in o['stages'].items()}
    st_n = {k: (v if isinstance(v, str) else json.dumps(v, sort_keys=True)) for k, v in n['stages'].items()}
    res['index'][('stages_old', json.dumps(st_o, sort_keys=True))] += 0
    # ---- AER
    ao, an = recs(OLD/o['paths']['aer']), recs(NEW/n['paths']['aer'])
    if [r.get('id') for r in ao] != [r.get('id') for r in an]:
        res['aer'][('record_ids_or_order_differ',)] += 1
    for ro, rn in zip(ao, an):
        k = rn.get('k')
        keys = set(ro) | set(rn)
        for f in sorted(keys):
            if ro.get(f) == rn.get(f): continue
            if f == 'ev':
                res['aer_ev'][(k, ro.get('ev'), rn.get('ev'))] += 1
            elif f == 'evf':
                eo, en = ro.get('evf') or {}, rn.get('evf') or {}
                for p in sorted(set(eo) | set(en)):
                    if eo.get(p) != en.get(p):
                        res['aer_evf'][(k, re.sub(r'/\d+', '/*', p), eo.get(p), en.get(p))] += 1
            elif f == 'rule':
                so, sn = sorted(rid(x) for x in ro.get('rule') or []), sorted(rid(x) for x in rn.get('rule') or [])
                for x in set(so) - set(sn): res['aer_rule_removed'][(k, x)] += 1
                for x in set(sn) - set(so): res['aer_rule_added'][(k, x)] += 1
            elif k == 'execution':
                if f in ('profile', 'rules'):
                    vo, vn = ro.get(f) or {}, rn.get(f) or {}
                    for kk in sorted(set(vo) | set(vn)):
                        if vo.get(kk) != vn.get(kk):
                            val = lambda v: (v[:19] if isinstance(v, str) else v)
                            res['aer_execution'][(f, kk, str(val(vo.get(kk))), str(val(vn.get(kk))))] += 1
                else:
                    res['aer_execution'][(f, 'changed')] += 1
            elif k == 'seal':
                if f == 'issues':
                    for io_, in_ in zip(ro.get('issues') or [], rn.get('issues') or []):
                        for kk in set(io_) | set(in_):
                            if io_.get(kk) != in_.get(kk):
                                res['aer_seal_issue'][(io_.get('code'), kk, str(io_.get(kk))[:60] if kk == 'rule' else 'changed', str(in_.get(kk))[:60] if kk == 'rule' else '')] += 1
                    if len(ro.get('issues') or []) != len(rn.get('issues') or []): res['aer_seal_issue'][('count_changed',)] += 1
                else:
                    res['aer_seal'][(f,)] += 1
            else:
                res['aer_other'][(k, f)] += 1; exs_with[f'aer_other:{k}:{f}'].add(ex)
    # ---- SEM
    (ro_ref, op), = o['paths']['sem'].items(); (rn_ref, np_), = n['paths']['sem'].items()
    so, sn = recs(OLD/op), recs(NEW/np_)
    if [r.get('id') for r in so] != [r.get('id') for r in sn]:
        res['sem'][('record_ids_or_order_differ',)] += 1
    for ro, rn in zip(so, sn):
        k = rn.get('k')
        for f in sorted(set(ro) | set(rn)):
            if ro.get(f) == rn.get(f): continue
            if k == 'sem' and f in ('profile', 'rules', 'ns'):
                vo, vn = ro.get(f) or {}, rn.get(f) or {}
                for kk in sorted(set(vo) | set(vn)):
                    if vo.get(kk) != vn.get(kk):
                        v = lambda x: x[:24] if isinstance(x, str) else json.dumps(x)[:40]
                        res['sem_header'][(f, kk, v(vo.get(kk)), v(vn.get(kk)))] += 1
            elif f == 'rule':
                for x in set(map(rid, ro.get('rule') or [])) ^ set(map(rid, rn.get('rule') or [])):
                    res['sem_rule'][(rn.get('type') or k, 'added' if x in map(rid, rn.get('rule') or []) else 'removed', x)] += 1
            elif f == 'value' and rn.get('type') == 'injection_marker':
                vo, vn = ro.get('value') or {}, rn.get('value') or {}
                if not (isinstance(vo, dict) and isinstance(vn, dict)):
                    res['sem_marker'][('value_type', type(vo).__name__, type(vn).__name__, str(vo)[:20] if isinstance(vo, str) else '', str(vn)[:20] if isinstance(vn, str) else '')] += 1
                    continue
                for kk in set(vo) | set(vn):
                    if vo.get(kk) != vn.get(kk):
                        res['sem_marker'][(kk, str(vo.get(kk))[:20], str(vn.get(kk))[:20])] += 1
            elif f == 'aer_digest':
                res['sem'][('aer_digest',)] += 1
            elif f == 'ev':
                res['sem'][('ev', rn.get('type'), ro.get('ev'), rn.get('ev'))] += 1
            else:
                res['sem'][(k, rn.get('type'), f)] += 1
    # ---- PROV
    po, pn = (json.loads((OLD/o['paths']['prov']['agentprov-prov/0.1']['json']).read_text()),
              json.loads((NEW/n['paths']['prov']['agentprov-prov/0.1']['json']).read_text()))
    for tag, doc in (('old', po), ('new', pn)):
        def walk(sec, bk):
            for st, xs in sec.items():
                if st in ('prefix', 'bundle'): continue
                for sid, x in xs.items():
                    ec = (x.get('apv:evidenceClass') or {}).get('$') if isinstance(x, dict) else None
                    res['prov_stmt_' + tag][(bk, st, ec)] += 1
                    if isinstance(x, dict) and 'apv:afterCausal' in x:
                        res['prov_afterCausal_' + tag][(bk, st)] += 1
                    if isinstance(x, dict) and any('unverified' in m for m in (x.get('apv:method') or []) if isinstance(m, str)):
                        res['prov_unverified_method_' + tag][(bk, st, ec)] += 1
        walk({k: v for k, v in doc.items() if k != 'bundle'}, 'top')
        for b, sec in doc.get('bundle', {}).items():
            walk(sec, bkind(b))
    # ---- validation row
def ser(c): return [[*k, v] for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))]
out = {'old': str(OLD).replace(str(Path.home()), '~'), 'new': str(NEW).replace(str(Path.home()), '~'), 'executions_compared': len(ni),
       'missing_in_old': sum(1 for e in ni if e not in oi), 'sections': {k: ser(v) for k, v in res.items()},
       'executions_with': {k: len(v) for k, v in exs_with.items()}}
OUT.write_text(json.dumps(out, indent=1, default=str) + '\n')
