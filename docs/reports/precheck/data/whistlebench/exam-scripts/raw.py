# ruff: noqa  (precheck examiner script for whistlebench, read-only; counts, labels and truncated digests only)
"""Whole-population raw pass over the 184 .eval logs (through agentprov.ingest): params per log, revision origin shape,
account-name classes (digest only) by pointer root and scenario membership, storyline tallies. Usage: raw.py <out.json>"""
import io, sys, json, re, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, __file__.rsplit('/',1)[0])
from gitread import tree, read
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
PAT={"users-dir":re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"),"home-dir":re.compile(r"/home/([^/\s\"'<>\\]{1,64})/"),
     "windows-users":re.compile(r"(?i)[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+([^\\/\s\"'<>]{1,64})")}
GH=re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}")
GEN={"ubuntu","user","root","runner","app","node","admin","agent","dev","test","shared"}
dg=lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
def walk(o,ptr,out):
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(k,str): out.append((ptr,k))
            walk(v,ptr,out)
    elif isinstance(o,list):
        for v in o: walk(v,ptr,out)
    elif isinstance(o,str): out.append((ptr,o))
def strs(o):
    out=[]; walk(o,'',out); return [s for _,s in out]
res={"logs":[],"acct":defaultdict(lambda: {"kind":None,"logs":set(),"samples":0,"strings":Counter(),"in_input":0,"in_store_seed":0,"tb_suffix":Counter()}),
     "origin":Counter(),"token_digests":Counter(),"token_logs_by":Counter()}
t={k:v for k,v in tree().items() if k.endswith('.eval')}
for lab in sorted(t):
    exp=lab.split('/',1)[1].rsplit('/',1)[0]
    with open_zip(io.BytesIO(read(t[lab])),IngestLimits(),release=False) as z:
        ms={m.label:m for m in iter_zip_members(z)}
        h=strict_json_loads(z.read_member(ms['header.json'])); ev=h['eval']
        p=(ev.get('task_args') or {}).get('params') or {}
        org=(ev.get('revision') or {}).get('origin') or ''
        toks=GH.findall(org)
        shape=re.sub(r"gh[pousr]_[A-Za-z0-9]{30,}","<gh-token>",org); shape=re.sub(r"github\.com[:/][^/]+/","github.com/<owner>/",shape)
        res["origin"][shape]+=1
        for tk in toks: res["token_digests"][dg(tk)]+=1
        if toks: res["token_logs_by"][f"{exp}|{ev['model']}|{h.get('eval',{}).get('packages',{}).get('inspect_ai')}"]+=1
        row={"label":lab,"exp":exp,"model":ev['model'],"task":ev.get('task'),"params":{k:v for k,v in p.items() if not isinstance(v,(dict,list))},
             "token_in_origin":bool(toks),"commit":((ev.get('revision') or {}).get('commit') or '')[:8],"n":0,"storyline_samples":Counter(),"scores":Counter()}
        for name,m in ms.items():
            if not (name.startswith('samples/') and name.endswith('.json')): continue
            s=strict_json_loads(z.read_member(m)); row["n"]+=1
            for sk,sv in (s.get('scores') or {}).items():
                v=sv.get('value')
                if isinstance(v,dict):
                    for a,b in v.items(): row["scores"][f"{sk}.{a}={b}"]+=1
                else: row["scores"][f"{sk}={v}"]+=1
            inp=" ".join(strs(s.get('input')))
            seed=" ".join(strs((s.get('metadata') or {})))+" "+" ".join(strs(s.get('files') or {}))
            seen=set()
            for root,val in s.items():
                out=[]; walk(val,root,out)
                for ptr,txt in out:
                    if '/Users/' not in txt and '/home/' not in txt and 'sers' not in txt: continue
                    for kind,rx in PAT.items():
                        for mm in rx.finditer(txt):
                            a=mm.group(1)
                            if a.lower() in GEN: continue
                            key=f"{kind}:{dg(a)}"; r=res["acct"][key]; r["kind"]=kind; r["logs"].add(lab); r["strings"][ptr]+=1
                            if ptr=='error_retries':
                                tail=txt[mm.end():mm.end()+200]
                                r["tb_suffix"]["site-packages/venv" if ('site-packages' in tail or '.venv' in tail or '/lib/python' in tail) else ("repo-code" if 'highagency' in tail or 'whistlebench' in tail else "other")]+=1
                            if key not in seen:
                                seen.add(key); r["samples"]+=1
                                if f"/Users/{a}/" in inp or f"/home/{a}/" in inp or a in inp: r["in_input"]+=1
            for e in (s.get('events') or [])[:1]: pass
        res["logs"].append(row)
out={"logs":[{**r,"storyline_samples":None,"scores":dict(r["scores"])} for r in res["logs"]],
     "acct":{k:{**v,"logs":len(v["logs"]),"strings":dict(v["strings"]),"tb_suffix":dict(v["tb_suffix"])} for k,v in res["acct"].items()},
     "origin_shapes":dict(res["origin"]),"token_digests":dict(res["token_digests"]),"token_logs_by":dict(res["token_logs_by"])}
json.dump(out,open(sys.argv[1],'w'),indent=1,sort_keys=True)
print(len(out["logs"]), sum(r["n"] for r in out["logs"]))
