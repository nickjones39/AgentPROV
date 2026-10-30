"""Masked context of each named account path (name -> <NAME>, any other /Users|/home segment -> <ACCT>, secret shapes
-> <SECRET>), for classification by the examiner only; prints task, model, event kind and a 70-char window per match.
usage: python -I acctctx.py <l1-units.jsonl> [digest ...]"""
import sys, os, json, re, hashlib, pathlib
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[6] / 'tools' / 'precheck'))
from rawread import tree, Reader
from agentprov.ingest.loaders import strict_json_loads
import l1_scan
want=set(sys.argv[2:]); dig=lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]
PAT={k:v for k,v in l1_scan.ACCOUNT_PATTERNS.items() if k!='windows-users'}
t=tree(); r=Reader(); seen={}
def mask(s,n):
    s=s.replace(n,'<NAME>')
    s=re.sub(r'(/Users/|/home/)[^/\s"\'<>\\]+',lambda m:m.group(1)+('<ACCT>' if '<NAME>' not in m.group(0) else '<NAME>'),s)
    for rx in l1_scan.SECRET_PATTERNS.values(): s=rx.sub('<SECRET>',s)
    return re.sub(r'[^\x20-\x7e]','.',s)
for l in open(sys.argv[1]):
    x=json.loads(l)
    if not {'account_path_named'} & set(x['flags']): continue
    ev=strict_json_loads(r.read(t[x['label']]))
    for i,e in enumerate(ev):
        def w(o,p):
            if isinstance(o,str):
                for k,rx in PAT.items():
                    for m in rx.finditer(o):
                        d=dig(m.group(1))
                        if d in want and seen.get(d,0)<2:
                            seen[d]=seen.get(d,0)+1
                            a,b=max(0,m.start()-70),m.end()+70
                            print(d,x['facets']['task'],x['facets']['model'],e.get('source'),e.get('action') or e.get('observation'),p,'|',mask(o[a:b],m.group(1)))
            elif isinstance(o,dict):
                for k,v in o.items(): w(v,p+'/'+k)
            elif isinstance(o,list):
                for v in o: w(v,p)
        w(e,'')
