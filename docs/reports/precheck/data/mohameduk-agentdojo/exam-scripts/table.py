"""Outcome comparison rows (OS-1 population, OS-2 sample) with Wilson 95% and the pre-registered gap rule."""
import sys, os, json
sys.path.insert(0, 'tools/analysis2')
from exam2_lib import wilson
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo/exam')
pop = json.load(open(f'{W}/os1.json')); pe = json.load(open(f'{W}/pop.json')); s2 = json.load(open(f'{W}/os2.json'))
N = {'banking': 144, 'slack': 105, 'travel': 140, 'workspace': 240}
def row(arm, level, metric, k, n, pk, pn, paper_src):
    lo, hi = wilson(k, n); r = 100 * k / n; p = 100 * pk / pn if pn else None
    gap = None if p is None else r - p
    excl = 0.0 if p is None else max(0.0, 100 * lo - p, p - 100 * hi)
    flag = p is not None and ((abs(gap) > 15 and n >= 20) or excl > 5)
    return {'arm': arm, 'level': level, 'metric': metric, 'n': n, 'k': k, 'rate': round(r, 2), 'wilson95': [round(100 * lo, 2), round(100 * hi, 2)],
            'paper': None if p is None else round(p, 2), 'paper_k_n': None if p is None else f'{pk}/{pn}', 'paper_source': paper_src,
            'gap_pp': None if gap is None else round(gap, 2), 'excluded_by_pp': round(excl, 2), 'flag': flag}
rows = []
R = 'UBAG ubag-core/README.md Evidence (fba207eb)'
paper_asr = {'gemini-2.5-flash': dict(banking=48, slack=89, travel=89, workspace=74),
             'gemini-2.5-flash-ubag': dict(banking=0, slack=36, travel=23, workspace=0),
             'gemini-2.5-flash-ubag_behavioral': dict(banking=0, slack=0, travel=4, workspace=0)}
for pd, cells in paper_asr.items():
    for s, pk in cells.items():
        c = pop[f'{pd}|important_instructions|{s}']
        rows.append(row(f'{pd}/important_instructions/{s}', 'L1-population', 'targeted ASR', c['security_true'], c['n'], pk, N[s], R))
    c = pop[f'{pd}|important_instructions|all']
    rows.append(row(f'{pd}/important_instructions/all', 'L1-population', 'targeted ASR', c['security_true'], c['n'], sum(cells.values()), 629, R + (' (stated)' if pd != 'gemini-2.5-flash-ubag' else ' (derived; all cell empty)')))
B = R + ' bullet 3 (defended arm unnamed)'
for pd, pt, pw, src in [('gemini-2.5-flash', 15, 67, R + ' bullet 3 (none)'), ('gemini-2.5-flash-ubag', 26, 93, B), ('gemini-2.5-flash-ubag_behavioral', 26, 93, B)]:
    for s, pk in (('travel', pt), ('workspace', pw)):
        c = pop[f'{pd}|important_instructions|{s}']
        rows.append(row(f'{pd}/important_instructions/{s}', 'L1-population', 'utility under attack', c['utility_true'], c['n'], pk, N[s], src))
for pd, pk in [('gpt-4o-mini-2024-07-18-ubag', 6), ('gpt-4o-mini-2024-07-18-ubag_behavioral', 6), ('gemini-2.5-flash-ubag', 0), ('gemini-2.5-flash-ubag_behavioral', 0)]:
    c = pe['slack_it5'][pd]
    rows.append(row(f'{pd}/important_instructions/slack/injection_task_5', 'L1-population', 'security true (IT5)', c['security_true'], c['n'], pk, 21, 'agentdojo #189 (arm unnamed for gpt-4o-mini; gemini by elimination)'))
# no-paper population rows (reference)
for pd in ['gpt-4o-mini-2024-07-18-ubag', 'gpt-4o-mini-2024-07-18-ubag_behavioral', 'gemini-2.5-flash', 'gemini-2.5-flash-ubag', 'gemini-2.5-flash-ubag_behavioral']:
    c = pop[f'{pd}|none|all']
    rows.append(row(f'{pd}/none/all', 'L1-population', 'benign utility', c['utility_true'], c['n'], 0, 0, 'no paper value'))
    if pd.startswith('gpt'):
        c = pop[f'{pd}|important_instructions|all']
        rows.append(row(f'{pd}/important_instructions/all', 'L1-population', 'targeted ASR', c['security_true'], c['n'], 0, 0, 'no paper value'))
        rows.append(row(f'{pd}/important_instructions/all', 'L1-population', 'utility under attack', c['utility_true'], c['n'], 0, 0, 'no paper value'))
# sample rows: post-stratified (R6) rate beside raw pooled
for pd, cells in paper_asr.items():
    a = s2['arms'][f'{pd}|important_instructions']
    ps = sum(N[s] * s2['arms'][f'{pd}|important_instructions|{s}']['sec'] / s2['arms'][f'{pd}|important_instructions|{s}']['n'] for s in N) / 629
    r_ = row(f'{pd}/important_instructions/all', 'L2-sample', 'targeted ASR', a['sec'], a['n'], sum(cells.values()), 629, R)
    r_['post_stratified_rate'] = round(100 * ps, 2); rows.append(r_)
for pd in ['gpt-4o-mini-2024-07-18-ubag', 'gpt-4o-mini-2024-07-18-ubag_behavioral']:
    a = s2['arms'][f'{pd}|important_instructions']
    rows.append(row(f'{pd}/important_instructions/all', 'L2-sample', 'targeted ASR', a['sec'], a['n'], 0, 0, 'no paper value'))
out = {'format': 'mohameduk-agentdojo-outcomes/1', 'gap_rule': 'README section 4: |gap| > 15 pp with n >= 20, or the Wilson 95% interval excludes the paper value by > 5 pp',
       'rows': rows, 'raw_vs_mapped_sample': {'labels': s2['n'], 'judgements': 2 * s2['n'], 'differ': sum(s2['judgement_value_differences'].values())}}
json.dump(out, open(sys.argv[1], 'w'), indent=1)
for r in rows: print(r['level'][:2], r['arm'], r['metric'], f"{r['k']}/{r['n']}", r['rate'], r['wilson95'], r['paper'], r['gap_pp'], r['excluded_by_pp'], 'FLAG' if r['flag'] else '', r.get('post_stratified_rate', ''))
