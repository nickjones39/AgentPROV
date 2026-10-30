# verifier: independent recount (counts, prefixes, digests only)
import io, sys, json, re, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[1])
from gitread import tree, read
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
dg=lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
UI=re.compile(r"^[a-z+]+://([^@/]+)@")  # any URL userinfo
ACC=re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/")
r={"origin_userinfo":Counter(),"by_exp":Counter(),"er_logs":set(),"er_samples":0,"acct7_ptrs":Counter(),"acct7_samples":0,"acct7_logs":set(),"er_samples_by_exp":Counter(),"samples":0,"er_status":Counter()}
t={k:v for k,v in tree().items() if k.endswith('.eval')}
for lab in sorted(t):
    exp=lab.split('/',1)[1].rsplit('/',1)[0]
    with open_zip(io.BytesIO(read(t[lab])),IngestLimits(),release=False) as z:
        ms={m.label:m for m in iter_zip_members(z)}
        h=strict_json_loads(z.read_member(ms['header.json']))
        org=((h['eval'].get('revision') or {}).get('origin')) or ''
        m=UI.match(org)
        if m:
            u=m.group(1); user,_,pw=u.partition(':')
            def shp(x): return (re.match(r"[a-z_]+?_|",x).group(0) or 'noprefix')+f"/len{len(x)}"
            r["origin_userinfo"][f"user={shp(user)}|pw={shp(pw) if pw else '-'}|d={dg(u)}"]+=1; r["by_exp"][exp]+=1
        for name,mm in ms.items():
            if not (name.startswith('samples/') and name.endswith('.json')): continue
            s=strict_json_loads(z.read_member(mm)); r["samples"]+=1
            hit=False
            for k,v in s.items():
                txt=json.dumps(v)
                if '/Users/' not in txt: continue
                for a in ACC.findall(txt):
                    if dg(a)=='<account-F>': r["acct7_ptrs"][k]+=1; hit=True
            if hit: r["acct7_samples"]+=1; r["acct7_logs"].add(lab)
            if s.get('error_retries'):
                r["er_samples"]+=1; r["er_logs"].add(lab); r["er_samples_by_exp"][exp]+=1
                r["er_status"][str(bool(s.get('error')))]+=1
out={k:(len(v) if isinstance(v,set) else v) for k,v in r.items()}
json.dump(out,open(sys.argv[2],'w'),indent=1,default=dict); print(json.dumps(out,default=dict))
