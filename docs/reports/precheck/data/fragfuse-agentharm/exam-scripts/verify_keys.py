# ruff: noqa  (precheck verifier script, fragfuse-agentharm PC-03: key shapes in raw logs via agentprov.ingest; digests, lengths, counts only)
import io,json,re,subprocess,sys,os
from collections import Counter
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
REPO=sys.argv[1]; REV=sys.argv[2]; IDS=sys.argv[3:]
env={"PATH":os.environ["PATH"],"HOME":os.environ["HOME"],"GIT_NO_LAZY_FETCH":"1","GIT_ALLOW_PROTOCOL":"file"}
tree=subprocess.run(["git","-C",REPO,"ls-tree","-r",REV],capture_output=True,env=env,check=True).stdout.decode()
P={"anthropic":re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),"openai":re.compile(r"(?<![A-Za-z0-9])sk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")}
lim=IngestLimits()
import hashlib,math
F=Counter()
def feat(n,k,o,mt):
    body=k.split("-",2)[-1]; ent=-sum(body.count(ch)/len(body)*math.log2(body.count(ch)/len(body)) for ch in set(body))
    ctx=o[max(0,mt.start()-40):mt.start()].lower()
    F[(n,hashlib.sha256(k.encode()).hexdigest()[:8],len(k),round(ent,2),any(w in k.lower() for w in ("xxxx","example","test","fake","dummy","1234","abcd")),"api_key" in ctx or "key" in ctx)]+=1
for want in IDS:
    line=[l for l in tree.splitlines() if want in l][0]; oid=line.split()[2]
    data=subprocess.run(["git","-C",REPO,"cat-file","blob",oid],capture_output=True,env=env,check=True).stdout
    ar=open_zip(io.BytesIO(data),lim,release=False); c=Counter()
    for m in iter_zip_members(ar):
        if m.disposition!="selected" or not (m.label or "").endswith(".json"): continue
        v=strict_json_loads(ar.read_member(m),lim)
        st=[(v,"")]
        while st:
            o,p=st.pop()
            if isinstance(o,dict): st+=[(x,p+"/"+(k if re.fullmatch(r"[a-z_]{1,30}",str(k)) else "<k>")) for k,x in o.items()]
            elif isinstance(o,list): st+=[(x,p+"/*") for x in o]
            elif isinstance(o,str):
                for n,rx in P.items():
                    for mt in rx.finditer(o):
                        whole = mt.group(0)==o.strip()
                        a=o[mt.end():mt.end()+1]; b=o[mt.start()-1:mt.start()] if mt.start() else ""
                        tok = (not a or not a.isalnum() and a not in "+/=") and (not b or not b.isalnum())
                        feat(n,mt.group(0),o,mt);c[(n,"whole_string" if whole else ("delimited_token" if tok else "inside_longer"),len(mt.group(0))>=80,re.sub(r"^.*?/","",(m.label or "").split("/")[0])+":"+p)]+=1
    print(want[:4], sorted(F.items())); F.clear()
