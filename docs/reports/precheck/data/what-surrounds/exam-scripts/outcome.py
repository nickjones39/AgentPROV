"""Pooled L2 outcome sanity: sample hijack rate (Wilson 95%) vs the sample-weighted paper rate (= population, H-06 exact),
gap rule of README section 4. argv: l2-runs-named.json pop.json l2out.json out.json"""
import json, sys, math
l2, pop, lo = (json.load(open(p)) for p in sys.argv[1:4])
cells = pop['H06_cells']; MS = {'us.anthropic.claude-sonnet-4-6':'Sonnet','us.anthropic.claude-haiku-4-5-20251001-v1:0':'Haiku','amazon.nova-micro-v1:0':'NovaMicro','amazon.nova-lite-v1:0':'NovaLite','amazon.nova-pro-v1:0':'NovaPro','mistral.ministral-3-8b-instruct':'Ministral','qwen.qwen3-32b-v1:0':'Qwen3'}
def wilson(k, n, z=1.96):
    p = k/n; d = 1+z*z/n; c = (p+z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d; return [round(c-h, 4), round(c+h, 4)]
exp = {}
for t, n in l2['identity']['tuples_model_defence_attack_suite'].items():
    m, _, a, _ = t.split('|'); a = 'clean' if a == 'none' else a; c = cells[f'{MS[m]}|{a}']
    e = exp.setdefault(a, [0, 0.0]); e[0] += n; e[1] += n*c['hijack']/c['n']
CH = {'tool_description': ['mcptox_p2','mcptox_p1','mcptox_p2_sys_explicit','mcptox_p2_sys_generic','mcptox_p2_sys_generic_b','mcptox_p2_sys_generic_long','mcptox_p2_sys_generic_role','mcptox_p2_userprefix_long'],
      'param_description': ['mcptox_p3'], 'tool_result': ['soft','imperative','urgent_authority','operator_spoof','mcptox_p1_toolresult','mcptox_p2_toolresult','mcptox_p2_toolresult_sysctx']}
popn = {}
for k, v in cells.items():
    a = k.split('|')[1]; p = popn.setdefault(a, [0, 0]); p[0] += v['n']; p[1] += v['hijack']
rows = []
groups = [(a, [a]) for a in sorted(exp)] + [(f'channel:{c}', arms) for c, arms in CH.items()]
for name, arms in groups:
    n = sum(lo['sample_by_arm'][a]['n'] for a in arms); k = sum(lo['sample_by_arm'][a]['hijack'] for a in arms)
    en = sum(exp[a][0] for a in arms); ek = sum(exp[a][1] for a in arms); er = ek/en
    pn = sum(popn[a][0] for a in arms); pk = sum(popn[a][1] for a in arms)
    w = wilson(k, n); gap = k/n - er
    flag = (n >= 20 and abs(gap) > 0.15) or (n >= 20 and (er < w[0]-0.05 or er > w[1]+0.05))
    rows.append({'arm': name, 'n': n, 'k': k, 'rate': round(k/n, 4), 'wilson95': w, 'expected_sample_weighted': round(er, 4), 'gap_pp': round(100*gap, 1),
                 'population': f'{pk}/{pn}', 'population_rate': round(pk/pn, 4), 'rule_applies': n >= 20, 'flag': flag})
json.dump(rows, open(sys.argv[4], 'w'), indent=1); [print(r) for r in rows]
