"""L2 mapping check on the scratch corpus: AER judgements of every sampled execution vs the raw results.csv row of the same
label; recomputed-hijack judgement; issue codes by producer generation; evidence classes of records; account-path component
class of /ext/wirelog/meta/source_quote (generic-name boolean only). argv: scripts_dir corpus out.json"""
import sys, os, json, glob, csv, io, re, collections
sys.path.insert(0, sys.argv[1]); from rawzip import members
C = collections.Counter
mem = members(); rows = {r['run_id']: r for r in csv.DictReader(io.StringIO(mem['results.csv'].decode('utf-8'), newline=''))}
GENERIC = {'user', 'username', 'ubuntu', 'admin', 'root', 'alice', 'bob', 'victim', 'you', 'yourname', 'name'}
res = C(); per = {}; ev = C(); codes = C(); home = C(); jnames = C()
for f in glob.glob(os.path.join(sys.argv[2], 'aer', '*', '*.aer.jsonl')):
    L = [json.loads(l) for l in open(f)]
    ex = L[0]; lab = next(a['origin']['label'] for a in ex['artifacts'] if a['role'] == 'primary'); d = lab.split('/')[1]
    model, arm, num = re.fullmatch(r'(.+?)__(.+)__(\d{4})', d).groups(); r = rows[d]
    J = {}
    for x in L:
        ev[(x.get('k'), x.get('ev'))] += 1
        if x.get('k') == 'judgement': J.setdefault(x['name'] + '|' + x['origin'], x['value']); jnames[x['name'] + '|' + x['origin'] + '|' + x['ev']] += 1
        if x.get('k') == 'seal':
            for i in x.get('issues', []): codes[(i.get('code'), 'runs1-154' if int(num) <= 154 else 'runs155+', 'meta_short' if 'source_dir' not in json.dumps(ex.get('ext', {})) else 'meta_has_source_dir')] += 1
    for k, col in (('hijack|checker', 'hijack'), ('exfiltration|checker', 'exfiltration'), ('silent|checker', 'silent'), ('call_order|checker', 'call_order')):
        res[f'{col}:' + ('eq' if J.get(k) == r[col] else 'ne')] += 1
    rec = [v for k, v in J.items() if k.startswith('hijack|') and not k.endswith('|checker')]
    res['recomputed_hijack_present'] += bool(rec); res['recomputed_eq_csv'] += bool(rec) and str(rec[0]) in (r['hijack'], {'1': 'True', '0': 'False'}[r['hijack']], {'1': 'true', '0': 'false'}[r['hijack']])
    c = per.setdefault(arm, C()); c['n'] += 1; c['hijack'] += J.get('hijack|checker') == '1'
    q = ex.get('ext', {}).get('wirelog', {}).get('meta', {}).get('source_quote')
    if isinstance(q, str):
        for m in re.finditer(r'/home/([^/\s"\']+)', q): home['generic' if m.group(1).lower() in GENERIC else 'other'] += 1
json.dump({'mapping_vs_raw': dict(res), 'sample_by_arm': {k: dict(v) for k, v in sorted(per.items())}, 'judgement_names': dict(jnames),
           'issue_codes_by_generation': {'|'.join(map(str, k)): v for k, v in sorted(codes.items())}, 'record_kind_ev': {f'{a}:{b}': n for (a, b), n in sorted(ev.items(), key=str)},
           'source_quote_home_component': dict(home)}, open(sys.argv[3], 'w'), indent=1, sort_keys=True)
print(open(sys.argv[3]).read()[:4000])
