import json,sys,collections
from pathlib import Path
OLD=Path(sys.argv[1]).expanduser(); NEW=Path(sys.argv[2]).expanduser()
oi={r['ex']:r for r in map(json.loads,(OLD/'executions.jsonl').read_text().splitlines())}
ni=[json.loads(l) for l in (NEW/'executions.jsonl').read_text().splitlines() if l]
def shape(v):
    if isinstance(v,dict): return {k:shape(x) for k,x in sorted(v.items())}
    if isinstance(v,list): return [shape(x) for x in v[:1]]
    return type(v).__name__
kd=collections.Counter(); enum=collections.Counter(); sh=collections.Counter()
for row in ni:
    o=oi[row['ex']]
    def get(C,r):
        out=[]
        for l in (C/list(r['paths']['sem'].values())[0]).read_text().splitlines():
            a=json.loads(l)
            if a.get('type')=='injection_marker': out.append(a)
        return out
    A=get(OLD,o); B=get(NEW,row)
    for x,y in zip(A,B):
        va,vb=x['value'],y['value']
        sh[(json.dumps(shape(va)),json.dumps(shape(vb)))]+=1
        if isinstance(va,dict) and isinstance(vb,dict):
            for k in set(va)|set(vb):
                if va.get(k)!=vb.get(k):
                    kd[k]+=1
                    a_,b_=va.get(k),vb.get(k)
                    if isinstance(a_,(bool,int)) or isinstance(b_,(bool,int)) or (isinstance(a_,str) and len(a_)<25 and isinstance(b_,str) and len(b_)<25):
                        enum[(k,str(a_),str(b_))]+=1
print('shapes'); [print(' ',v,k) for k,v in sh.items()]
print('keys differing',dict(kd)); [print(' ',k,v) for k,v in enum.most_common(20)]
