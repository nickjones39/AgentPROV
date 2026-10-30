import json, sys, collections
sys.path.insert(0, 'tools/analysis2')
from exam2_lib import wilson
from pathlib import Path
C = Path(sys.argv[1]).expanduser(); L1 = Path(sys.argv[2]).expanduser(); out = Path(sys.argv[3])
rows = {}
for l in open(L1):
    r = json.loads(l); rows[r['sha256']] = r
N_h = collections.Counter(r['stratum'] for r in rows.values())
M = {'prov-deepseek-chat':'deepseek-chat','google_gemini-2.5-flash':'gemini-2.5-flash','prov-gpt-5-nano':'gpt-5-nano','meta-llama_llama-3.3-70b-instruct':'llama-3.3-70b','qwen_qwen-2.5-72b-instruct':'qwen-2.5-72b','z-ai_glm-4.6':'glm-4.6'}
logged = {'deepseek-chat':(84.0,4.3),'gemini-2.5-flash':(39.0,8.6),'gpt-5-nano':(73.5,1.5),'llama-3.3-70b':(36.2,8.8),'qwen-2.5-72b':(40.3,14.5),'glm-4.6':(83.5,7.5)}
paper = {'deepseek-chat':(84.2,4.4),'gemini-2.5-flash':(39.0,8.7),'gpt-5-nano':(73.5,1.5),'llama-3.3-70b':(36.3,8.8),'qwen-2.5-72b':(40.2,14.6),'glm-4.6':(83.6,7.6)}
mism = collections.Counter(); samp = []
marker = {}
for l in open(C/'executions.jsonl'):
    n = json.loads(l)
    sha = n['raw'][0]['sha256'].split(':', 1)[1]
    r = rows[sha]
    j = {}
    for x in open(C/n['paths']['aer']):
        rec = json.loads(x)
        if rec.get('k') == 'judgement': j[rec.get('name')] = rec.get('value')
    present = False
    for x in open(C/n['paths']['sem']['agentdojo.suites@2']):
        rec = json.loads(x)
        if rec.get('type') == 'injection_marker' and (rec.get('value') or {}).get('status') == 'present': present = True
    for f in ('utility', 'security'):
        raw = r['outcomes'][f]
        a = j.get(f)
        if raw != a: mism[(f, str(raw), str(a))] += 1
        else: mism[(f, 'equal')] += 1
    samp.append((r['stratum'], M[r['facets']['model_folder']], r['facets']['attack'], j.get('utility'), j.get('security'), present))
n_h = collections.Counter(s[0] for s in samp)
def post(rowsel, val):
    # post-stratified mean over strata present in the selection: sum_h N_h * mean_h / sum_h N_h
    by = collections.defaultdict(list)
    for s in rowsel: by[s[0]].append(1 if val(s) else 0)
    num = sum(N_h[h] * (sum(v)/len(v)) for h, v in by.items()); den = sum(N_h[h] for h in by)
    return 100 * num / den if den else None
res = []
for m in logged:
    sel_all = [s for s in samp if s[1] == m]; sel_att = [s for s in sel_all if s[2] != 'benign']
    for metric, sel, val, lg, pp in (('utility', sel_all, lambda s: s[3] is True, logged[m][0], paper[m][0]),
                                     ('asr', sel_att, lambda s: s[4] is True, logged[m][1], paper[m][1])):
        k = sum(1 for s in sel if val(s)); n = len(sel); lo, hi = wilson(k, n); ps = post(sel, val)
        gap_logged = ps - lg; gap_paper = ps - pp
        excl = max(0.0, 100*lo - pp, pp - 100*hi)
        flag = (n >= 20 and abs(gap_paper) > 15) or excl > 5
        res.append(dict(model=m, metric=metric, n=n, k=k, unweighted=round(100*k/n, 2), wilson95=[round(100*lo, 2), round(100*hi, 2)],
                        post_stratified=round(ps, 2), logged=lg, paper=pp, gap_pp_vs_logged=round(gap_logged, 2), gap_pp_vs_paper=round(gap_paper, 2),
                        interval_excludes_paper_by_pp=round(excl, 2), flag=flag))
# pooled per attack ASR
for a in ('direct', 'important_instructions', 'injecagent'):
    sel = [s for s in samp if s[2] == a]; k = sum(1 for s in sel if s[4] is True); n = len(sel); lo, hi = wilson(k, n)
    res.append(dict(model='all', metric=f'asr:{a}', n=n, k=k, unweighted=round(100*k/n, 2), wilson95=[round(100*lo, 2), round(100*hi, 2)], post_stratified=round(post(sel, lambda s: s[4] is True), 2)))
att = [s for s in samp if s[2] != 'benign']
h16 = dict(n=len(att), k=sum(1 for s in att if s[5]), post_stratified=round(post(att, lambda s: s[5]), 2), population_e2=82.24)
json.dump(dict(raw_vs_aer=[[*k, v] for k, v in sorted(mism.items())], rates=res, surfaced_payload=h16), open(out, 'w'), indent=1)
print(dict(mism)); [print(r) for r in res]; print(h16)
