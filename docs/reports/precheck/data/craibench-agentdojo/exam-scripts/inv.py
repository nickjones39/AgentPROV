"""Raw census of craibench-agentdojo logs via agentprov.ingest strict parse: system-prompt variants, PI wrapper shape,
extra user messages, delimiter forms, tool-call names, payload reach. Counts and truncated digests only."""
import sys,os,json,hashlib,re,collections as C
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
t=tree(); r=Reader()
labs=sorted(l for l in t if re.fullmatch(r'runs/[^/]+/[^/]+/[^/]+/[^/]+/[^/]+\.json',l))
out=C.defaultdict(lambda: C.defaultdict(C.Counter)); calls=C.Counter(); top=C.Counter()
for lab in labs:
    p=lab.split('/'); fn=p[5][:-5]
    mode='prepass' if p[4]=='none' else ('MI' if fn.endswith('_memory_injection') else 'PI')
    cell=f'{p[1]}|{p[2]}|{mode}'
    d=r.json(t[lab]); o=out[cell]; o['n']['logs']+=1
    ms=d['messages']; sysm=[m for m in ms if m['role']=='system']
    sp=sysm[0]['content'] if sysm else ''
    o['sysprompt'][hashlib.sha256(sp.encode()).hexdigest()[:10]+f':{len(sp)}']+=1
    o['n_user_msgs'][sum(m['role']=='user' for m in ms)]+=1
    o['pipeline_name_eq_dir'][d.get('pipeline_name')==p[1]]+=1
    inj=' '.join(str(v) for v in (d.get('injections') or {}).values())
    o['inj_signed'][bool(re.search(r'important message from me',inj,re.I))]+=1
    o['inj_has_important_message'][bool(re.search(r'important message',inj,re.I))]+=1
    o['inj_nonempty'][bool(inj.strip())]+=1
    tools=' '.join(str(m.get('content')) for m in ms if m['role']=='tool')
    users=' '.join(str(m.get('content')) for m in ms if m['role']=='user')
    o['payload_in_tool_output'][bool(inj.strip()) and any(str(v)[:60] in tools for v in (d.get('injections') or {}).values() if str(v).strip())]+=1
    o['payload_in_user_msgs'][bool(inj.strip()) and any(str(v)[:60] in users for v in (d.get('injections') or {}).values() if str(v).strip())]+=1
    o['data_tag'][('<data>' in tools)]+=1
    o['angle_delims'][('<<' in tools or '>>' in tools)]+=1
    o['caret_join'][bool(re.search(r'\w\^\w',tools))]+=1
    o['security'][d.get('security')]+=1; o['utility'][d.get('utility')]+=1
    for m in ms:
        for c in (m.get('tool_calls') or []): calls[c.get('function')]+=1
    top[tuple(sorted(d.keys()))]+=1
res={'logs':len(labs),'cells':{k:{kk:{str(a):b for a,b in vv.items()} for kk,vv in v.items()} for k,v in sorted(out.items())},
     'tool_calls':{k:calls[k] for k in ('siphon','secure_funds')},'tool_call_total':sum(calls.values()),'distinct_tools':len(calls),
     'top_key_sets':len(top)}
json.dump(res,sys.stdout,indent=1)
