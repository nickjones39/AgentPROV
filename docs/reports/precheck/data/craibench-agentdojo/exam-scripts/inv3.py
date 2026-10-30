"""Where the Default-type crypto prompt (5d66eb347e) and the PI wrapper forms occur (task ids only); mini MI single security by task."""
import sys,os,json,hashlib,re,collections as C
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
t=tree(); r=Reader()
labs=sorted(l for l in t if re.fullmatch(r'runs/[^/]+/crypto_trading/[^/]+/[^/]+/[^/]+\.json',l))
v=C.defaultdict(set); w=C.defaultdict(lambda: C.defaultdict(set)); mini=C.Counter(); dur=C.defaultdict(list)
for lab in labs:
    p=lab.split('/'); fn=p[5][:-5]; d=r.json(t[lab]); ms=d['messages']
    h=hashlib.sha256(ms[0]['content'].encode()).hexdigest()[:10]
    if h=='5d66eb347e': v[p[1]].add(p[3]+'/'+fn)
    if p[4]!='none' and not fn.endswith('_memory_injection') and 'mini' not in p[1]:
        inj=' '.join(str(x) for x in (d.get('injections') or {}).values())
        f='signed' if re.search(r'important message from me',inj,re.I) else ('unsigned' if re.search(r'important message',inj,re.I) else 'other')
        w[f]['inj'].add(re.match(r'injection_task_(\d+)',fn).group(1)); w[f]['n'].add(lab)
    if 'mini' in p[1] and p[4]!='none':
        ut=int(p[3].split('_')[-1]); mini[f"{'single' if ut>=80 else 'multi'}|{fn.split('_')[2]}|sec={d['security']}"]+=1
print(json.dumps({'default_prompt_logs':{k:sorted(s) for k,s in v.items()},
 'pi_wrapper':{f:{'n':len(x['n']),'injection_ids':sorted(x['inj'],key=int)} for f,x in w.items()},
 'mini_by_inj':dict(sorted(mini.items()))},indent=1))
