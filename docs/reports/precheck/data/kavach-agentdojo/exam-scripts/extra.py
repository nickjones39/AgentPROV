"""kavach-agentdojo extra counts: H7 token definitions, kavach-arm message shape, incomplete labels (counts only).
usage: uv run python -I extra.py <out.json>"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader, PINS
W=os.path.expanduser('~/.agentprov/migration-work/precheck/kavach-agentdojo'); C=collections.Counter
def txt(c):
    if c is None: return None
    if isinstance(c,str): return c
    return ''.join((b.get('content') or '') for b in c if isinstance(b,dict))
TOK='<|tool_response>'
r=Reader(); out=collections.defaultdict(C); done=set(); incomplete=[]
for part,commit in PINS.items():
    t=tree(commit)
    for l in open(f'{W}/l1-units-{part}.jsonl'):
        x=json.loads(l)
        if x['sha256'] in done: continue
        done.add(x['sha256']); f=x['facets']; md=f['model_dir']
        if 'incomplete' in x['flags']: incomplete.append('/'.join(x['label'].split('/')[-3:]) + ' @ ' + md.split('/')[1])
        if not (('slack' in md) or ('workspace' in md and 'gemma' not in md) or md.startswith('results_v2/logs')): continue
        d=r.json(t[x['label']]); msgs=d['messages']; key=f"{md}|{f['attack_dir']}"
        a=out[key]; a['n']+=1
        asst=[m for m in msgs if m.get('role')=='assistant']
        last=txt(asst[-1].get('content')) if asst else ''
        a['tok_last_asst']+= TOK in (last or '')
        a['tok_any_asst']+= any(TOK in (txt(m.get('content')) or '') for m in asst)
        a['tok_anywhere']+= TOK in json.dumps(d)
        a[f'n_msgs={len(msgs)}' if len(msgs)<=3 else 'n_msgs>3']+=1
        if 'kavach' in md:
            a['last_asst_text_empty']+= (last or '').strip()==''
            a['asst_with_tool_calls']+= sum(1 for m in asst if m.get('tool_calls'))
out['incomplete_labels']=dict(C(incomplete))
json.dump({k:dict(v) for k,v in out.items()},open(sys.argv[1],'w'),indent=1,sort_keys=True)
for k,v in sorted(out.items()): print(k.replace('results_v2/',''),dict(v))
