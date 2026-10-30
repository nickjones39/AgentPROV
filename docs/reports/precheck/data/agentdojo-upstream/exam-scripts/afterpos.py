import json, re, sys
from pathlib import Path
from collections import Counter
H=Path.home()/'.agentprov'; part=sys.argv[1]
NEW=H/f'migration-work/precheck/agentdojo-upstream/l2-{part}-j2.partial'; OLD=H/f'corpora/agentdojo-upstream-{part}-p10.partial'
new={json.loads(l)['ex']:json.loads(l) for l in open(NEW/'executions.jsonl')}
old={}
for l in open(OLD/'executions.jsonl'):
    r=json.loads(l)
    if r['ex'] in new: old[r['ex']]=r
def core(p):
    d=json.load(open(p)); return [v for k,v in d['bundle'].items() if '.core.' in k][0], d
def aer(p):
    return {(json.loads(x)['k'],json.loads(x).get('id')):json.loads(x) for x in open(p)}
shown=0; c=Counter()
for ex in sorted(new):
    co,_=core(OLD/old[ex]['paths']['prov']['agentprov-prov/0.1']['json']); cn,dn=core(NEW/new[ex]['paths']['prov']['agentprov-prov/0.1']['json'])
    for k,st in co.get('activity',{}).items():
        if 'apv:afterPos' in st and 'apv:afterPos' not in cn.get('activity',{}).get(k,{}):
            ra=aer(OLD/old[ex]['paths']['aer']); rb=aer(NEW/new[ex]['paths']['aer'])
            rid=k.split(':',1)[1]
            ka=[x for x in ra if x[1]==rid]; kb=[x for x in rb if x[1]==rid]
            a=ra[ka[0]]; b=rb[kb[0]]
            sig=(a['k'], json.dumps(a.get('after')), json.dumps(b.get('after')), json.dumps(a.get('evf',{}).get('/after')), json.dumps(b.get('evf',{}).get('/after')), str([r for r in a.get('rule',[]) if 'after' in r]), str([r for r in b.get('rule',[]) if 'after' in r]))
            c[sig]+=1
            if shown<2:
                shown+=1
                print(ex, rid, 'old st keys', sorted(st), '\n new st keys', sorted(cn['activity'].get(k,{})))
                # where did afterPos go
                for bn,bd in dn['bundle'].items():
                    for sec,items in bd.items():
                        for kk,s2 in items.items():
                            if json.dumps(s2).find('"'+k+'"')>=0 and ('after' in json.dumps(s2).lower()): print('   in', re.sub(r'\.[a-z2-7]{16,}$','',bn), sec, kk[:50], sorted(s2)[:12])
for s,n in c.items(): print(n, s)
