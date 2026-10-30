"""L1-06 follow-up: classify the named account paths of openagentsafety without writing any name (sha256[:12] only).
For each distinct (kind, name): trajectories, models, pointer roles, whether the same path prefix occurs in the task
definitions (workspaces/tasks/**, non-PNG, at the pin), in L1-10's non-JSON aux files, and operator identity.
usage: python -I acct.py <l1-units.jsonl> <out.json>"""
import sys, os, json, re, hashlib, collections, pathlib
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[6] / 'tools' / 'precheck'))
from rawread import tree, Reader
from agentprov.ingest.loaders import strict_json_loads
import l1_scan
PAT={k:v for k,v in l1_scan.ACCOUNT_PATTERNS.items() if k!='windows-users'}
PFX={'users-dir':'/Users/{}/','home-dir':'/home/{}/','tilde-user':'~{}/'}
OP=os.path.basename(os.path.expanduser('~'))
dig=lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]
t=tree(); r=Reader()
flag=[json.loads(l) for l in open(sys.argv[1])]
flag=[x for x in flag if {'account_path_named','account_path_generic'} & set(x['flags'])]
names=collections.defaultdict(lambda:{'traj':set(),'models':set(),'roles':collections.Counter(),'strings':0})
def walk(o,p,ev):
    if isinstance(o,str):
        for k,rx in PAT.items():
            for n in rx.findall(o):
                if k=='users-dir' and n.lower()=='shared': continue
                kind='generic' if n.lower() in l1_scan.GENERIC_ACCOUNTS else 'named'
                key=(k,n,kind); d=names[key]; d['strings']+=1; d['traj'].add(lab); d['models'].add(model)
                d['roles'][('first_event' if ev==0 else 'later')+':'+p.split('/')[-1]]+=1
    elif isinstance(o,dict):
        for k,v in o.items(): walk(v,p+'/'+k,ev)
    elif isinstance(o,list):
        for v in o: walk(v,p,ev)
for x in flag:
    lab=x['label']; model=x['facets']['model']
    ev=strict_json_loads(r.read(t[lab]))
    for i,e in enumerate(ev if isinstance(ev,list) else []): walk(e,'',i)
# task-definition text at the pin
taskdefs=[v for k,v in t.items() if k.startswith('workspaces/') and not k.lower().endswith('.png')]
blob=b'\n'.join((r.read(v) or b'') for v in taskdefs).decode('utf-8','replace')
evaltxt=[v for k,v in t.items() if k.startswith('evaluation/') and not k.lower().endswith(('.png','.json'))]
out={'trajectories_flagged':len(flag),'taskdef_files_screened':len(taskdefs),'operator_matches':0,'accounts':[]}
for (k,n,kind),d in sorted(names.items(),key=lambda kv:(-len(kv[1]['traj']),kv[0][0])):
    if n==OP: out['operator_matches']+=1
    pre=PFX[k].format(n)
    out['accounts'].append({'kind':k,'class':kind,'digest':dig(n),'trajectories':len(d['traj']),'models':sorted(d['models']),
        'strings':d['strings'],'roles':dict(d['roles']),'prefix_in_taskdefs':pre in blob,'name_in_taskdefs':bool(re.search(r'(?<![A-Za-z0-9])'+re.escape(n)+r'(?![A-Za-z0-9])',blob))})
a=out['accounts']; out['summary']={'distinct':len(a),'named':sum(x['class']=='named' for x in a),
  'named_prefix_in_taskdefs':sum(x['class']=='named' and x['prefix_in_taskdefs'] for x in a),
  'named_name_in_taskdefs_only':sum(x['class']=='named' and not x['prefix_in_taskdefs'] and x['name_in_taskdefs'] for x in a),
  'named_not_in_taskdefs':sum(x['class']=='named' and not x['name_in_taskdefs'] for x in a)}
json.dump(out,open(sys.argv[2],'w'),indent=1)
