"""menelaus29-ipi-multidomain: L1 population outcomes per author arm, H1-H8, H12, H16 from the committed L1 rows (no raw read); counts only."""
import json, math, os, sys, collections
U = os.path.expanduser('~/.agentprov/migration-work/precheck/menelaus29-ipi-multidomain/l1-units-head.jsonl')
rows = [json.loads(l) for l in open(U)]
for r in rows:
    f = r['facets']
    for k in ('model_dir', 'suite', 'task_dir', 'file', 'attack_dir', 'attack_class', 'task_kind', 'h_pipeline'): f.setdefault(k, f.get('h_suite') if k == 'suite' else '<none>')
def wilson(k, n, z=1.959964):
    if n == 0: return [0.0, 1.0]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]
def key(r):
    f = r['facets']; return (f['suite'], f['task_dir'], f['file'], f['attack_dir'])
def exp(r): return r['facets']['model_dir']
att = [r for r in rows if r['facets']['attack_class'] == 'attacked']
pre = [r for r in rows if r['facets']['task_kind'] == 'prepass']
out = {'n_units': len(rows), 'attacked': len(att), 'prepass': len(pre),
       'other': [r['label'] for r in rows if r not in att and r not in pre]}
# H1 counts per dir x suite x kind
c = collections.Counter(f"{exp(r)}|{r['facets']['suite']}|{'prepass' if r['facets']['task_kind']=='prepass' else r['facets']['attack_class']}" for r in rows)
out['H1_counts'] = dict(sorted(c.items()))
out['H1_prepass_outside_injection_task'] = sum(1 for r in pre if not r['facets']['task_dir'].startswith('injection_task_'))
out['H1_benign_user_task_logs'] = sum(1 for r in rows if r['facets']['task_kind'] == 'user' and r['facets']['attack_class'] == 'none')
def sel(prefix, suite=None, pred=lambda r: True, inj=False):
    return [r for r in att if exp(r).startswith(prefix) and (suite is None or r['facets']['suite'] == suite)
            and (inj or r['facets']['attack_dir'] != 'injecagent') and pred(r)]
REP = lambda r: r['facets']['task_dir'] in ('user_task_0', 'user_task_13') and r['facets']['file'] in ('injection_task_0', 'injection_task_1')
ARMS = [  # name, rows, paper ASR k/n, paper utility k (None = not reported)
    ('gemini35fl/none/baseline all', sel('data/baseline/raw/'), 0, 110, 90),
    ('gemini35fl/none/baseline workspace', sel('data/baseline/raw/', 'workspace'), 0, 52, 52),
    ('gemini35fl/none/baseline banking', sel('data/baseline/raw/', 'banking'), 0, 46, 26),
    ('gemini35fl/none/baseline slack', sel('data/baseline/raw/', 'slack'), 0, 12, 12),
    ('gemma4/none/parity all', sel('data/baseline_gemma4/r/'), 5, 110, None),
    ('gemma4/none/parity workspace', sel('data/baseline_gemma4/r/', 'workspace'), 0, 52, None),
    ('gemma4/none/parity banking', sel('data/baseline_gemma4/r/', 'banking'), 5, 46, None),
    ('gemma4/none/parity slack', sel('data/baseline_gemma4/r/', 'slack'), 0, 12, None),
    ('gemma4/none/full fresh160', sel('data/baseline_gemma4/full/', pred=lambda r: not REP(r)), 34, 160, 103),
    ('gemma4/none/full replication', sel('data/baseline_gemma4/full/', pred=REP), 6, 20, 10),
    ('gemma4/my_spotlighting/fresh160', sel('data/defended/g4/v1/fresh160/'), 4, 160, 115),
    ('gemma4/spotlighting_with_delimiting/replication_dev builtin', sel('data/defended/g4/v1/replication_dev/builtin/'), 4, 20, 10),
    ('gemma4/my_spotlighting/replication_dev custom', sel('data/defended/g4/v1/replication_dev/custom/'), 0, 20, 10),
    ('gemma4/my_spotlighting/adaptive v1', sel('data/adaptive/g4/v1/'), 1, 24, 14),
    ('gemma4/my_spotlighting/adaptive v2a (outcome-bearing)', sel('data/adaptive/g4/v2a/', pred=lambda r: r['outcomes']['security'] is not None), 1, 72, None),
    ('gemma4/my_spotlighting/adaptive v2a_repair', sel('data/adaptive/g4/v2a_repair/'), 0, 16, None),
    ('gemma4/my_spotlighting/adaptive v2a + repair (utility)', sel('data/adaptive/g4/v2a', pred=lambda r: r['outcomes']['security'] is not None), 1, 88, 71),
    ('gemma4/my_spotlighting/adaptive v2b', sel('data/adaptive/g4/v2b/'), 5, 33, 22),
    ('gemma4/none/diagnostics g4 + raw', sel('data/diagnostics/g4'), 2, 25, None),
]
arms = []
for name, rs, pk, pn, pu in ARMS:
    n = len(rs); k = sum(1 for r in rs if r['outcomes']['security'] is True); u = sum(1 for r in rs if r['outcomes']['utility'] is True)
    row = {'arm': name, 'n': n, 'paper_n': pn, 'asr_k': k, 'asr_pct': round(100 * k / n, 2) if n else None, 'asr_wilson': wilson(k, n),
           'paper_asr_k': pk, 'paper_asr_pct': round(100 * pk / pn, 2), 'asr_gap_pp': round(100 * k / n - 100 * pk / pn, 2) if n else None,
           'util_k': u, 'util_wilson': wilson(u, n), 'paper_util_k': pu}
    pp = 100 * pk / pn; lo, hi = row['asr_wilson']
    row['flag'] = bool(n and ((n >= 20 and abs(row['asr_gap_pp']) > 15) or pp < lo - 5 or pp > hi + 5))
    if pu is not None:
        row['util_gap_pp'] = round(100 * u / n - 100 * pu / pn, 2); lo, hi = row['util_wilson']; up = 100 * pu / pn
        row['util_flag'] = bool((n >= 20 and abs(row['util_gap_pp']) > 15) or up < lo - 5 or up > hi + 5)
    arms.append(row)
out['arms'] = arms
inj = [r for r in att if r['facets']['attack_dir'] == 'injecagent']
out['injecagent'] = {f"{exp(r)}|{r['facets']['suite']}|sec={r['outcomes']['security']}|util={r['outcomes']['utility']}": 1 for r in inj}
# H3: parity successes and key sets
g3 = [r for r in sel('data/baseline_gemma4/r/') if r['outcomes']['security']]
out['H3_parity_successes'] = sorted(f"{r['facets']['suite']}|{r['facets']['task_dir']}|{r['facets']['file']}|{r['facets']['attack_dir']}" for r in g3)
kg = {key(r) for r in att if exp(r).startswith('data/baseline_gemma4/r/')}
ki = {key(r) for r in att if exp(r).startswith('data/baseline/raw/')}
out['H3_keys'] = {'gemini': len(ki), 'gemma': len(kg), 'gemini_minus_gemma': sorted('|'.join(k) for k in ki - kg), 'gemma_minus_gemini': len(kg - ki)}
# H16 payload ids in parity dirs
pay = collections.Counter()
for r in att:
    if exp(r).startswith(('data/baseline/raw/', 'data/baseline_gemma4/r/')) and r['facets']['attack_dir'].startswith('corpus_'):
        pay[r['facets']['attack_dir'].split('_')[1]] += 1
out['H16_parity_payload_ids'] = {'n': len(pay), 'ids': dict(sorted(pay.items()))}
fullpay = {r['facets']['attack_dir'].split('_')[1] for r in att if exp(r).startswith('data/baseline_gemma4/full/')}
out['full_payload_ids'] = sorted(fullpay)
# H6 / H8
out['null_outcome_labels'] = [r['label'] for r in rows if r['outcomes']['security'] is None or r['outcomes']['utility'] is None]
out['flagged_labels'] = {r['label']: r['flags'] for r in rows if r['flags']}
st = [r for r in att if r['outcomes']['security'] is True]
out['H8_attacked_security_true'] = len(st)
out['H8_by_dir'] = dict(collections.Counter(exp(r) for r in st))
out['H7_diag_successes'] = sorted(f"{exp(r)}|{r['facets']['suite']}|{r['facets']['task_dir']}|{r['facets']['file']}|{r['facets']['attack_dir']}" for r in st if exp(r).startswith('data/diagnostics/g4'))
out['prepass_security'] = dict(collections.Counter(str(r['outcomes']['security']) for r in pre))
# H12: shared keys across adaptive arms (attacked / prepass), fp equality
ad = {}
for a in ('v1', 'v2a', 'v2a_repair', 'v2b'):
    ad[a] = {(key(r), r['facets']['attack_class']): r['fp'] for r in rows if exp(r) == f'data/adaptive/g4/{a}/results/raw/banking'}
sh = {}
names = list(ad)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = names[i], names[j]; common = set(ad[a]) & set(ad[b])
        sh[f'{a}&{b}'] = {'attacked': sum(1 for k in common if k[1] == 'attacked'), 'prepass': sum(1 for k in common if k[1] == 'none'),
                          'fp_equal': sum(1 for k in common if ad[a][k] == ad[b][k])}
out['H12_shared_keys'] = sh
fps = collections.Counter(r['fp'] for r in rows if r.get('fp')); out['fp_dup_groups'] = sum(1 for v in fps.values() if v > 1)
out['h_pipeline'] = dict(collections.Counter(r['facets']['h_pipeline'] for r in rows))
out['task_dirs_user_task_5'] = sum(1 for r in rows if r['facets']['task_dir'] == 'user_task_5')
json.dump(out, open(sys.argv[1], 'w'), indent=1)
for r in arms: print(r)
for k in out:
    if k not in ('arms', 'H1_counts'): print(k, json.dumps(out[k])[:700])
