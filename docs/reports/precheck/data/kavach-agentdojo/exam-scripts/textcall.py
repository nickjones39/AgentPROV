"""Shape of the final assistant text in 3-message (no tool call) workspace gemma logs: pattern counts and length buckets only.
usage: uv run python -I textcall.py <out.json>"""
import sys, os, json, collections, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader, PINS
W=os.path.expanduser('~/.agentprov/migration-work/precheck/kavach-agentdojo'); C=collections.Counter
PAT={'json_name_key':re.compile(r'"name"\s*:'),'tool_code':re.compile(r'tool_code|<tool_call>|<\|tool_call'),'fence':re.compile(r'```'),'call_paren':re.compile(r'\b[a-z_]+\([^)]*\)'),'KAVACH':re.compile(r'KAVACH|kavach',re.I)}
def txt(c):
    if c is None: return ''
    if isinstance(c,str): return c
    return ''.join((b.get('content') or '') for b in c if isinstance(b,dict))
r=Reader(); out=collections.defaultdict(C); done=set()
for part in ('nav-fixer2','rearch-forcedformat-fix'):
    t=tree(PINS[part])
    for l in open(f'{W}/l1-units-{part}.jsonl'):
        x=json.loads(l); md=x['facets']['model_dir']
        if x['sha256'] in done or not ('workspace_forced/' in md or 'not_forced2/' in md): continue
        done.add(x['sha256']); d=r.json(t[x['label']]); msgs=d['messages']
        if len(msgs)!=3: continue
        k=md.split('/')[1]+'|'+md.split('/')[-1]; a=out[k]; s=txt(msgs[-1].get('content')); a['n_3msg']+=1
        for n,p in PAT.items(): a[n]+= bool(p.search(s))
        a['len<200' if len(s)<200 else ('len<1000' if len(s)<1000 else 'len>=1000')]+=1
        a['utility_true']+= bool(d.get('utility'))
json.dump({k:dict(v) for k,v in out.items()},open(sys.argv[1],'w'),indent=1,sort_keys=True)
for k,v in sorted(out.items()): print(k,dict(v))
