"""Section 8: which AER fields differ from the 10J-T baseline, per record kind (paths only, no values). Usage: basediff.py CORPUS BASELINE"""
import sys, os, glob, json, collections
from agentprov.ingest.loaders import strict_json_loads
A=os.path.expanduser(sys.argv[1]); B=os.path.expanduser(sys.argv[2]); c=collections.Counter()
def flat(x,p=''):
    if isinstance(x,dict):
        for k,v in x.items(): yield from flat(v,f'{p}/{k}')
    else: yield p,x
for f in glob.glob(f'{A}/aer/*/*.aer.jsonl'):
    ex=os.path.basename(f); bf=glob.glob(f'{B}/aer/*/{ex}')[0]
    ra=[strict_json_loads(l) for l in open(f,'rb')]; rb=[strict_json_loads(l) for l in open(bf,'rb')]
    for x,y in zip(ra,rb):
        fx=dict(flat(x)); fy=dict(flat(y))
        for k in set(fx)|set(fy):
            if fx.get(k)!=fy.get(k):
                import re; c[f"{x['k']}:{re.sub(r'/\d+','/*',k)}"]+=1
print(json.dumps(dict(c.most_common(40))))
