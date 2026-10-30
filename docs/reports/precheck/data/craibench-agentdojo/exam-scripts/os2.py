"""L2 sample: raw L1 booleans of the 53 sampled labels per (model|defence|attack) arm, compared with l2-head.json mapped outcomes."""
import json,os,sys,collections as C
B=os.path.dirname(os.path.abspath(__file__))+'/..'
S=set(json.load(open(B+'/l2-sample-head.json'))['labels'])
U=os.path.expanduser('~/.agentprov/migration-work/precheck/craibench-agentdojo/l1-units-head.jsonl')
L2=json.load(open(B+'/l2-head.json'))['outcomes']['arms']
raw=C.defaultdict(lambda: C.Counter())
for l in open(U):
    r=json.loads(l)
    if r['label'] not in S: continue
    pd=r['label'].split('/')[1]; att=r['label'].split('/')[4]
    model,defn=pd.split('-spotlighting_')
    arm=f'{model}|spotlighting_{defn}|{att}'
    raw[arm]['n']+=1; raw[arm]['utility']+=r['outcomes']['utility']; raw[arm]['security']+=r['outcomes']['security']
out={}
for arm,c in sorted(raw.items()):
    m=L2.get(arm,{})
    mu=m.get('utility',{}); ms=m.get('attack_success') or {}
    out[arm]={'raw':dict(c),'mapped_utility':[mu.get('k'),mu.get('n')],'mapped_attack_success':[ms.get('k'),ms.get('n')] if ms else None,
              'utility_equal': mu.get('k')==c['utility'] and mu.get('n')==c['n'],
              'security_equal': (ms.get('k')==c['security']) if ms else 'n/a (prepass: benign constant)'}
json.dump(out,sys.stdout,indent=1)
