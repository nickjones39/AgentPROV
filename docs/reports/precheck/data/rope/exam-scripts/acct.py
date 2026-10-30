import re, os, json, hashlib, getpass, sys
from agentprov.ingest.loaders import strict_json_loads
ROOT=os.path.expanduser('~/Desktop/PhD/Labs/AgentPROV-upstream/rope')
labels=sys.argv[1:]
rx=re.compile(r"/(?:home|Users)/([^/\s\"'<>\\]{1,64})/")
me=getpass.getuser()
def walk(v,p):
    if isinstance(v,str): yield p,v
    elif isinstance(v,dict):
        for k,x in v.items(): yield from walk(x,p+[k])
    elif isinstance(v,list):
        for i,x in enumerate(v): yield from walk(x,p+[i])
for lab in labels:
    data=open(os.path.join(ROOT,lab),'rb').read()
    obj=strict_json_loads(data)
    names={}
    for p,s in walk(obj,[]):
        for m in rx.finditer(s):
            n=m.group(1); role=None
            if p and p[0]=='messages': role=obj['messages'][p[1]].get('role')
            names.setdefault(n,[]).append((role,'/'.join(str(x) if not isinstance(x,int) else '*' for x in p)))
    for n,occ in names.items():
        print(lab, 'acct#'+hashlib.sha256(n.encode()).hexdigest()[:8], 'is_operator', n==me, 'roles', sorted(set(o[0] or '-' for o in occ)), 'first_role', occ[0][0], 'n', len(occ))
