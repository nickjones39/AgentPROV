import sys, collections, json, re
sys.path.insert(0, sys.argv[1])
from rawload import load
C = collections.Counter
res = collections.defaultdict(C)
it_calls = collections.defaultdict(C)   # injection task -> payload tool-call count classes (attacked gpt-4o)
asr_by_it = collections.defaultdict(lambda: [0,0])
ut16 = []
local = {'logs':0,'asst_turns':0,'asst_no_calls':0,'callish_no_calls':0,'logs_callish':0,'logs_empty_final':0,'logs_zero_calls':0,
         'logs_payload_in_tool_output':0,'attacked_logs':0, 'tool_msgs':0}
local_callish_kinds = C()
gpt_reach = C()
july = []
names = C(); pkg = C(); bv = C(); errs = C(); dur = C(); inj_keys=C(); role_other=C()
tool_errors = 0
def text_of(c):
    if c is None: return ''
    if isinstance(c, str): return c
    return ''.join(x.get('content') or '' for x in c if isinstance(x, dict))
for label, row, o in load():
    f = row['facets']; pdir = f['pipeline_dir']; rdir = f['results_dir']; att = f['attack_dir']
    names[(pdir, o.get('pipeline_name') == pdir)] += 1
    pkg[o.get('agentdojo_package_version')] += 1; bv[o.get('benchmark_version')] += 1
    errs[(o.get('error') is None)] += 1
    dur[('duration_none' if o.get('duration') is None else 'duration_num', 'outcome' if 'utility' in o else 'no_outcome')] += 1
    ts = o.get('evaluation_timestamp') or ''
    if ts[:7] == '2025-07': july.append(label)
    msgs = o.get('messages') or []
    for m in msgs:
        if m['role'] not in ('system','user','assistant','tool'): role_other[m['role']] += 1
        if m['role'] == 'tool' and m.get('error'): tool_errors += 1
    inj = o.get('injections') or {}
    inj_keys[(att, bool(inj))] += 1
    payloads = [v for v in inj.values() if isinstance(v, str)]
    tool_text = '\n'.join(text_of(m.get('content')) for m in msgs if m['role']=='tool')
    reached = any(p and p.strip() and p.strip()[:80] in tool_text for p in payloads)
    if att == 'tool_knowledge':
        it = o.get('injection_task_id')
        n_calls = sorted({len(re.findall(r'use the tool `', p)) for p in payloads})
        it_calls[(pdir, it)][tuple(n_calls)] += 1
        if pdir == 'gpt-4o-2024-05-13':
            gpt_reach[reached] += 1
            if 'security' in o:
                a = asr_by_it[it]; a[1] += 1; a[0] += bool(o['security'])
    if pdir == 'gpt-4o-2024-05-13' and o.get('user_task_id') == 'user_task_16':
        called = any(tc.get('function') == 'get_unread_emails' for m in msgs if m['role']=='assistant' for tc in (m.get('tool_calls') or []))
        ut16.append((att, called, o.get('utility')))
    if pdir in ('local', 'Local model') and msgs:
        local['logs'] += 1
        zero = True; callish = False
        for m in msgs:
            if m['role'] != 'assistant': continue
            local['asst_turns'] += 1
            tcs = m.get('tool_calls') or []
            if tcs: zero = False
            else:
                local['asst_no_calls'] += 1
                t = text_of(m.get('content'))
                kinds = [k for k, pat in (('function_tag', '<function='), ('tool_call_tag', '<tool_call>'), ('fenced_json', '```json')) if pat in t]
                if kinds:
                    local['callish_no_calls'] += 1; callish = True
                    for k in kinds: local_callish_kinds[k] += 1
        local['tool_msgs'] += sum(1 for m in msgs if m['role']=='tool')
        last = [m for m in msgs if m['role']=='assistant']
        if last and not text_of(last[-1].get('content')).strip() and not (last[-1].get('tool_calls')): local['logs_empty_final'] += 1
        if zero: local['logs_zero_calls'] += 1
        if callish: local['logs_callish'] += 1
        if att == 'tool_knowledge':
            local['attacked_logs'] += 1
            local['logs_payload_in_tool_output'] += reached
out = {
 'pipeline_name_equals_dir': {f'{k[0]}|{k[1]}': v for k, v in names.items()},
 'package_version': dict(pkg), 'benchmark_version': dict(bv), 'error_is_null': {str(k): v for k, v in errs.items()},
 'duration': {'|'.join(k): v for k, v in dur.items()},
 'july_logs': july, 'non_standard_roles': dict(role_other), 'tool_errors': tool_errors,
 'injections_present_by_attack': {f'{k[0]}|{k[1]}': v for k, v in inj_keys.items()},
 'payload_call_count_by_pipeline_it': {f'{k[0]}|{k[1]}': {str(list(kk)): vv for kk, vv in v.items()} for k, v in sorted(it_calls.items())},
 'gpt4o_attacked_payload_reached_tool_output': {str(k): v for k, v in gpt_reach.items()},
 'gpt4o_asr_by_injection_task': {k: v for k, v in sorted(asr_by_it.items(), key=lambda x: int(x[0].split('_')[-1]))},
 'gpt4o_user_task_16': [list(x) for x in ut16],
 'local': local, 'local_callish_kinds': dict(local_callish_kinds),
}
print(json.dumps(out, indent=1))
