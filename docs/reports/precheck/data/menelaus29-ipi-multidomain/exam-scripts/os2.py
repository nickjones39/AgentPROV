"""menelaus29-ipi-multidomain L2: mapped AER/SEM/PROV of the 144-unit scratch corpus joined to L1 rows by raw sha256; raw vs mapped
judgements, sample rates per author arm (Wilson), injection markers (H14), system_prompt_unrecognised vs defence (H15),
class-D statements by rule; counts only. Reads our own derived files (scratch corpus), never raw bytes."""
import json, os, sys, math, collections
from agentprov.validate._provdoc import ProvView
W = os.path.expanduser('~/.agentprov/migration-work/precheck/menelaus29-ipi-multidomain')
C = f'{W}/l2-head-j2.partial'
units = {json.loads(l)['sha256']: json.loads(l) for l in open(f'{W}/l1-units-head.jsonl')}
def wilson(k, n, z=1.959964):
    if n == 0: return [0.0, 100.0]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, round(100 * (c - h) / d, 1)), round(100 * (c + h) / d, 1)]
REP = lambda f: f.get('task_dir') in ('user_task_0', 'user_task_13') and f.get('file') in ('injection_task_0', 'injection_task_1')
def arm(f):
    md = f.get('model_dir', '<none>')
    if f.get('attack_class') != 'attacked' or f.get('attack_dir') == 'injecagent': return None
    for pre, name in [('data/baseline/raw/', 'gemini35fl baseline'), ('data/baseline_gemma4/r/', 'gemma4 parity'),
                      ('data/defended/g4/v1/fresh160/', 'gemma4 fresh160 my_spotlighting'), ('data/defended/g4/v1/replication_dev/builtin/', 'gemma4 replication_dev builtin'),
                      ('data/defended/g4/v1/replication_dev/custom/', 'gemma4 replication_dev custom'), ('data/adaptive/g4/v1/', 'gemma4 adaptive v1'),
                      ('data/adaptive/g4/v2a_repair/', 'gemma4 adaptive v2a_repair'), ('data/adaptive/g4/v2a/', 'gemma4 adaptive v2a'), ('data/adaptive/g4/v2b/', 'gemma4 adaptive v2b'),
                      ('data/diagnostics/g4', 'gemma4 diagnostics g4+raw')]:
        if md.startswith(pre): return name
    if md.startswith('data/baseline_gemma4/full/'): return 'gemma4 full ' + ('replication' if REP(f) else 'fresh160')
    return 'other (sanity)'
POP = {'gemini35fl baseline': (0, 110, 90), 'gemma4 parity': (5, 110, None), 'gemma4 full fresh160': (34, 160, 103), 'gemma4 full replication': (6, 20, 10),
       'gemma4 fresh160 my_spotlighting': (4, 160, 115), 'gemma4 replication_dev builtin': (4, 20, 10), 'gemma4 replication_dev custom': (0, 20, 10),
       'gemma4 adaptive v1': (1, 24, 14), 'gemma4 adaptive v2a': (1, 72, None), 'gemma4 adaptive v2a_repair': (0, 16, None), 'gemma4 adaptive v2b': (5, 33, 22),
       'gemma4 diagnostics g4+raw': (2, 25, None)}
diff = collections.Counter(); per = collections.defaultdict(lambda: collections.Counter()); inj = collections.Counter(); spu = collections.Counter()
dcls = collections.Counter(); aer_ev = collections.Counter(); n = 0
for line in open(f'{C}/executions.jsonl'):
    row = json.loads(line); n += 1
    sha = row['raw'][0]['sha256'].split(':', 1)[1]; u = units[sha]; f = u['facets']
    judg = {}
    for l in open(f"{C}/{row['paths']['aer']}"):
        rec = json.loads(l)
        if rec.get('k') == 'judgement': judg[rec['name']] = rec['value']
        if 'ev' in rec: aer_ev[rec['ev']] += 1
    for m in ('utility', 'security'):
        diff[f'{m}|{"equal" if judg.get(m) == u["outcomes"][m] else "differ"}'] += 1
    a = arm(f)
    if a:
        per[a]['n'] += 1; per[a]['asr'] += judg.get('security') is True; per[a]['util'] += judg.get('utility') is True
    sem = row['paths']['sem']['agentdojo.suites@2']; nm = 0
    for l in open(f'{C}/{sem}'):
        rec = json.loads(l)
        if rec.get('type') == 'injection_marker': nm += 1
    if f.get('attack_class') == 'attacked':
        k = 'gemini35fl baseline' if f.get('model_dir', '').startswith('data/baseline/raw/') else 'other attacked'
        inj[f'{k}|n'] += 1; inj[f'{k}|with_marker'] += nm > 0
    md = f.get('model_dir', '<none>')
    dfn = 'spotlighting_with_delimiting' if 'builtin' in md else ('my_spotlighting' if md.startswith(('data/defended/', 'data/adaptive/')) else 'none')
    spu[f"{dfn}|unrecognised={'map.agentdojo.system_prompt_unrecognised' in row['issues']}|empty={'incomplete' in u['flags']}"] += 1
    doc = json.load(open(f"{C}/{row['paths']['prov']['agentprov-prov/0.1']['json']}"))
    v = ProvView.parse(doc)
    for kind, sts in [('top', v.top)] + [(b.kind, b.statements) for b in v.bundles.values()]:
        for st in sts:
            if st.cls == 'D': dcls[f'{kind}|{st.rule}|{st.section}'] += 1
arms = []
for a, c in sorted(per.items()):
    pk, pn, pu = POP.get(a, (None, None, None))
    r = {'arm': a, 'n': c['n'], 'asr_k': c['asr'], 'asr_wilson': wilson(c['asr'], c['n']), 'util_k': c['util'], 'util_wilson': wilson(c['util'], c['n'])}
    if pn:
        r['paper_asr_pct'] = round(100 * pk / pn, 2); r['asr_gap_pp'] = round(100 * c['asr'] / c['n'] - r['paper_asr_pct'], 2)
        if pu is not None: r['paper_util_pct'] = round(100 * pu / pn, 2); r['util_gap_pp'] = round(100 * c['util'] / c['n'] - r['paper_util_pct'], 2)
    r['verdict'] = 'gap rule applies' if c['n'] >= 20 else 'n < 20'
    arms.append(r)
out = dict(n=n, raw_vs_mapped=dict(diff), sample_arms=arms, h14_injection_marker=dict(inj), h15_system_prompt=dict(spu),
           prov_class_d_by_rule=dict(sorted(dcls.items())), aer_ev=dict(aer_ev))
json.dump(out, open(sys.argv[1], 'w'), indent=1); print(json.dumps(out, indent=1))
