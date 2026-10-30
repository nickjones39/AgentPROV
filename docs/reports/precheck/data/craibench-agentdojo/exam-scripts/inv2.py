"""System-prompt variants vs system_messages.yaml keys at the pin; PI wrapper x outcome; payload reach. Counts/digests only."""
import sys,os,json,hashlib,re,collections as C
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
from agentprov.ingest.yamlsafe import safe_load
t=tree(); r=Reader()
ws=lambda s: re.sub(r'\s+',' ',s).strip()
y=safe_load(r.read(t['src/agentdojo/data/system_messages.yaml']))
keys={k:ws(v) for k,v in y.items() if isinstance(v,str)}
labs=sorted(l for l in t if re.fullmatch(r'runs/[^/]+/[^/]+/[^/]+/[^/]+/[^/]+\.json',l))
var={}; var_where=C.defaultdict(C.Counter); pi=C.Counter(); reach=C.Counter(); var_out=C.defaultdict(C.Counter)
for lab in labs:
    p=lab.split('/'); fn=p[5][:-5]; mode='prepass' if p[4]=='none' else ('MI' if fn.endswith('_memory_injection') else 'PI')
    d=r.json(t[lab]); ms=d['messages']; sp=ws(ms[0]['content']) if ms[0]['role']=='system' else ''
    h=hashlib.sha256(ms[0]['content'].encode()).hexdigest()[:10]
    var[h]=sp; var_where[h][f'{p[1]}|{p[2]}|{mode}']+=1
    if mode!='prepass': var_out[h+'|'+p[2]+'|'+mode][f"sec={d['security']}"]+=1
    tools=ws(' '.join(str(m.get('content')) for m in ms if m['role']=='tool'))
    vals=[ws(str(v)) for v in (d.get('injections') or {}).values() if str(v).strip()]
    if mode=='PI':
        inj=' '.join(vals)
        w='signed' if re.search(r'important message from me',inj,re.I) else ('unsigned' if re.search(r'important message',inj,re.I) else 'other')
        hit=any(v[len(v)//3:len(v)//3+30] in tools for v in vals if len(v)>=40)
        mi=int(p[3].split('_')[-1])
        pi[f'{p[2]}|{w}|reach={hit}|sec={d["security"]}']+=1
        if p[2]=='crypto_trading' and w=='other': pi[f'crypto other: inj_keys={len(vals)} task={p[3]}']+=1
    else:
        reach[f'{mode}|user_msgs={sum(m["role"]=="user" for m in ms)}']+=1
res={'yaml_keys':sorted(keys),'variants':{}}
for h,sp in var.items():
    res['variants'][h]={'len_norm':len(sp),'where':dict(var_where[h]),
      'yaml_key_substring':[k for k,v in keys.items() if v and v in sp],
      'yaml_key_prefix':[k for k,v in keys.items() if v and sp.startswith(v[:200])]}
res['variant_outcomes']={k:dict(v) for k,v in sorted(var_out.items())}
res['pi_wrapper_reach_security']=dict(sorted(pi.items()))
json.dump(res,sys.stdout,indent=1)
