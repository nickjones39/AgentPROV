"""OS-1: population rates per arm x suite (travel IT0-5) vs the paper/workbook counts (prereg section 4); Wilson 95%,
gap rule (>15 pp with n>=20, or >5 pp outside the interval); macros; perf utility and duration. Reads exam/pop.json."""
import json, math, sys
d = json.load(open(sys.argv[1])); sec, perf = d['sec'], d['perf']
def wil(k, n, z=1.959964):
    p = k / n; den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(100 * max(0, c - h), 2), round(100 * min(1, c + h), 2)]
PAPER = {  # counts: (asr, uua) per suite banking/144, slack/105, travel/120, workspace/560
 'agentspec': {'banking': (6, 58), 'slack': (43, 19), 'travel': (41, 29), 'workspace': (20, 311)},
 'pvagent': {'banking': (0, 53), 'slack': (0, 5), 'travel': (19, 48), 'workspace': (4, 283)},
 'seagent': {'banking': (0, 65), 'slack': (0, 26), 'travel': (0, 49), 'workspace': (0, 312)},
 'seagent-RF': {'banking': (0, 81), 'slack': (0, 40), 'travel': (0, 65), 'workspace': (0, 383)}}
PERF = {'baseline': 75.12, 'pvagent': 34.0025, 'seagent': 47.1425, 'seagent-RF': 70.045}
LAT = {'baseline': 10.7525, 'pvagent': 19.225, 'seagent': 11.27, 'seagent-RF': 10.81}
rows = []; macro = {}
for a in ['agentspec', 'baseline', 'pvagent', 'seagent', 'seagent-RF']:
    ma = []; mu = []
    for s in ['banking', 'slack', 'travel', 'workspace']:
        n = sec[f'{a}|{s}|n']; ka = sec[f'{a}|{s}|asr']; ku = sec[f'{a}|{s}|uua']
        ma.append(100 * ka / n); mu.append(100 * ku / n)
        for met, k, ref in (('ASR', ka, PAPER.get(a, {}).get(s, (None,))[0]), ('UUA', ku, PAPER.get(a, {}).get(s, (None, None))[1])):
            r = 100 * k / n; w = wil(k, n); row = {'arm': a, 'suite': s, 'metric': met, 'n': n, 'k': k, 'rate': round(r, 2), 'wilson95': w}
            if ref is not None:
                pr = 100 * ref / n; g = r - pr; row.update(paper_k=ref, paper=round(pr, 2), gap_pp=round(g, 2), off_runs=k - ref,
                    gap_rule=bool((abs(g) > 15 and n >= 20) or (pr < w[0] - 5 or pr > w[1] + 5)))
            rows.append(row)
    macro[a] = {'asr': round(sum(ma) / 4, 4), 'uua': round(sum(mu) / 4, 4)}
pv140 = {'n': sec['pvagent|travel|n'] + d['pv_it6']['pvagent|n'], 'asr_k': sec['pvagent|travel|asr'] + d['pv_it6']['pvagent|asr'], 'uua_k': sec['pvagent|travel|uua'] + d['pv_it6']['pvagent|uua']}
perf_m = {}
for a in PERF:
    us = [100 * perf[f'{a}|{s}|ut'] / perf[f'{a}|{s}|n'] for s in ['banking', 'slack', 'travel', 'workspace']]
    perf_m[a] = {'utility_macro': round(sum(us) / 4, 4), 'paper': PERF[a], 'gap_pp': round(sum(us) / 4 - PERF[a], 4),
                 'per_suite': [f"{perf[f'{a}|{s}|ut']}/{perf[f'{a}|{s}|n']}" for s in ['banking', 'slack', 'travel', 'workspace']],
                 'duration_macro_s': round(sum(d['perf_duration_mean'][f'{a}|{s}'] for s in ['banking', 'slack', 'travel', 'workspace']) / 4, 4), 'paper_latency_s': LAT[a]}
us = [100 * perf[f'agentspec|{s}|ut'] / perf[f'agentspec|{s}|n'] for s in ['banking', 'slack', 'travel', 'workspace']]
perf_m['agentspec'] = {'utility_macro': round(sum(us) / 4, 4), 'paper': None}
out = {'rows': rows, 'macro': macro, 'paper_macro': {'agentspec': [20.715, 34.5225], 'pvagent': [4.135, 33.0275], 'seagent': [0, 41.61], 'seagent-RF': [0, 54.2275], 'baseline(provenance README)': [47.18, 52.09]},
       'pvagent_travel_140': pv140, 'it6_subset': d['pv_it6'], 'perf': perf_m,
       'flagged': [r for r in rows if r.get('gap_rule')], 'cells_off_gt1': [(r['arm'], r['suite'], r['metric'], r['off_runs']) for r in rows if abs(r.get('off_runs', 0)) > 1]}
json.dump(out, open(sys.argv[2], 'w'), indent=1)
print(json.dumps({k: out[k] for k in ('macro', 'pvagent_travel_140', 'perf', 'flagged', 'cells_off_gt1')}))
print([(r['arm'], r['suite'], r['metric'], r['k'], r['n'], r.get('paper_k')) for r in rows])
