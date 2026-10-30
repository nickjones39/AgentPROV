"""Build os1-population.json and os2-sample.json (counts only) for shreeyavarma-llm-safety."""
import json, sys, collections, os
from pathlib import Path
sys.path.insert(0, 'tools/analysis2')
from exam2_lib import wilson
W = Path.home()/'.agentprov/migration-work/precheck/shreeyavarma-llm-safety'
D = Path('docs/reports/precheck/data/shreeyavarma-llm-safety')
rows = [json.loads(l) for l in open(W/'l1-units-head.jsonl')]
raw = json.load(open(W/'exam/raw_checks.json'))
def rate(k, n):
    lo, hi = wilson(k, n)
    return {'k': k, 'n': n, 'rate_pct': round(100*k/n, 2) if n else None, 'wilson95_pct': [round(100*lo, 2), round(100*hi, 2)]}
arms = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
nooutcome = collections.Counter()
for r in rows:
    f = r['facets']; o = r['outcomes']
    arm = f"{f['h_pipeline']}|{f['attack_dir']}|{f['task_kind']}"
    if o.get('utility') is None: nooutcome[arm] += 1; continue
    a = arms[arm]
    a['utility'][1] += 1; a['utility'][0] += bool(o['utility'])
    if f['attack_dir'] == 'tool_knowledge':
        a['ASR'][1] += 1; a['ASR'][0] += bool(o['security'])
    else:
        a['benign_security_true'][1] += 1; a['benign_security_true'][0] += bool(o['security'])
os1 = {'format': 'agentprov-precheck-os1/0.1', 'corpus_id': 'shreeyavarma-llm-safety', 'part': 'head',
       'basis': 'raw outcome fields of the 672 L1 rows (l1-units-head.jsonl); logs without outcome keys excluded from denominators',
       'logs_without_outcome_by_arm': dict(nooutcome),
       'arms': {arm: {m: rate(*v) for m, v in ms.items()} for arm, ms in sorted(arms.items())}}
# pooled and IT split
it = raw['gpt4o_asr_by_injection_task']
lo = [it[f'injection_task_{i}'] for i in range(6)]; hi = [it[f'injection_task_{i}'] for i in range(6, 14)]
os1['gpt4o_tool_knowledge_asr_by_injection_task'] = {k: rate(*v) for k, v in it.items()}
os1['gpt4o_tool_knowledge_asr_it0_5_payload_lists_calls'] = rate(sum(x[0] for x in lo), sum(x[1] for x in lo))
os1['gpt4o_tool_knowledge_asr_it6_13_payload_lists_no_call'] = rate(sum(x[0] for x in hi), sum(x[1] for x in hi))
alla = [r for r in rows if r['facets']['attack_dir'] == 'tool_knowledge' and r['outcomes'].get('security') is not None]
os1['all_attacked_asr'] = rate(sum(bool(r['outcomes']['security']) for r in alla), len(alla))
comp = [r for r in rows if r['outcomes'].get('utility') is not None]
os1['all_complete_utility'] = rate(sum(bool(r['outcomes']['utility']) for r in comp), len(comp))
os1['all_complete_security_true'] = rate(sum(bool(r['outcomes']['security']) for r in comp), len(comp))
os1['prereg_H7_bracket'] = {'lo_k': 64, 'hi_k': 91, 'n': 560, 'observed_k': arms['gpt-4o-2024-05-13|tool_knowledge|user']['ASR'][0]}
os1['context_upstream_agentdojo_head_gpt4o_workspace_v1'] = {
    'note': 'context only, no verdict: agentdojo-upstream head L1 rows, runs/gpt-4o-2024-05-13/workspace (v0.k11, suite v1, injection tasks 0-5)',
    'tool_knowledge_ASR': rate(62, 240), 'tool_knowledge_UA': rate(94, 240), 'benign_utility': rate(25, 40)}
os1['context_results_page'] = 'v1 all-suite gpt-4o-2024-05-13 tool_knowledge utility 69.07, UA 57.71, ASR 34.50 (agentdojo.spylab.ai/results); context only'
json.dump(os1, open(D/'os1-population.json', 'w'), indent=1, sort_keys=True)
# OS-2
l2 = json.load(open(D/'l2-head.json'))
units = json.load(open(W/'exam/l2_units.json'))
byl = {r['label']: r for r in rows}
cmp = collections.Counter(); arms2 = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
for u in units:
    r = byl[u['label']]; f = r['facets']
    for m in ('utility', 'security'):
        rv = r['outcomes'].get(m); mv = u['judgements'].get(m, [None])[0]
        cmp['equal' if rv == mv else 'differ'] += 1
    if 'utility' not in u['judgements']: continue
    arm = f"{f['h_pipeline']}|{f['attack_dir']}|{f['task_kind']}"
    a = arms2[arm]; a['utility'][1] += 1; a['utility'][0] += bool(u['judgements']['utility'][0])
    if f['attack_dir'] == 'tool_knowledge':
        a['ASR'][1] += 1; a['ASR'][0] += bool(u['judgements']['security'][0])
os2 = {'format': 'agentprov-precheck-os2/0.1', 'corpus_id': 'shreeyavarma-llm-safety', 'part': 'head',
       'basis': 'mapped AER judgements of the 32 sampled executions (l2-head-j2.partial) vs the raw values of the same labels',
       'judgements_compared': dict(cmp), 'judgement_slots': 64,
       'arms_mapped': {arm: {m: rate(*v) for m, v in ms.items()} for arm, ms in sorted(arms2.items())},
       'l2_check_outcomes': l2['outcomes']['arms'],
       'note': 'no sampled arm reaches n >= 20, so the gap rule does not apply to the sample (README section 8 amendment 2.2); Wilson only'}
json.dump(os2, open(D/'os2-sample.json', 'w'), indent=1, sort_keys=True)
print(json.dumps(os1['arms'], indent=0)); print(os1['gpt4o_tool_knowledge_asr_it0_5_payload_lists_calls'], os1['gpt4o_tool_knowledge_asr_it6_13_payload_lists_no_call'], os1['all_attacked_asr'], os1['all_complete_utility'], os1['all_complete_security_true'])
print(os2['judgements_compared']); print(json.dumps(os2['arms_mapped'], indent=0))
