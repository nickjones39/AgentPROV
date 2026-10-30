import json, collections
from pathlib import Path
O = Path('~/.agentprov/corpora/rope-p10.partial').expanduser()
C = collections.Counter
r_ = C()
dates = collections.defaultdict(C)
for l in (O / 'executions.jsonl').read_bytes().splitlines():
    r = json.loads(l)
    lines = (O / r['paths']['aer']).read_bytes().splitlines()
    e = json.loads(lines[0]); path = e['artifacts'][0]['origin']['path']; seg = path.split('/')
    md = '/'.join(seg[1:3]) if seg[1] in ('ablation', 'router') else seg[1]; suite, att = seg[-4], seg[-2]
    pipe = (e.get('ext') or {}).get('agentdojo', {}).get('pipeline_name')
    date = None; variants = C(); denied_post = False; util_present = False
    for x in lines:
        if b'"scope"' in x or b'"decision"' in x or b'"judgement"' in x or b'post_webpage' in x:
            a = json.loads(x)
            if a.get('k') == 'scope' and a.get('id') == 'run':
                date = ((a.get('t') or {}).get('raw') or {}).get('start', '')[:10]
            elif a.get('k') == 'decision':
                variants[((a.get('ext') or {}).get('rope') or {}).get('query_echo')] += 1
            elif a.get('k') == 'judgement' and a.get('name') == 'utility' and not a.get('revises'):
                util_present = True
            elif a.get('k') == 'tool_execution' and a.get('name') == 'post_webpage' and (a.get('status') not in (None, 'ok')):
                denied_post = True
    for v, n in variants.items():
        r_[f'denial:{v}'] += n
        dates[f'denial:{v}'][date] += n
        if md == 'gpt-4o' and att == 'important_instructions': r_[f'gpt-4o-II-denial:{v}'] += n
    dates[f'pipe:{pipe if pipe and ("iter2" in pipe or "final-opus" in pipe) else "other"}'][date] += 1
    if md == 'qwen3-235b' and att == 'autodojo': dates['qwen-autodojo'][date] += 1
    if suite == 'slack' and denied_post: r_[f'slack_denied_post_webpage|utility_present={util_present}'] += 1
    dates['all'][date[:7] if date else None] += 1
print(dict(r_))
for k, v in dates.items(): print(k, dict(sorted(v.items(), key=lambda kv: str(kv[0])))) if len(v) < 15 else print(k, len(v), min(map(str, v)), max(map(str, v)))
