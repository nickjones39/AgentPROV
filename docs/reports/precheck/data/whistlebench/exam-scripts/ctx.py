# ruff: noqa  (precheck examiner script for whistlebench; counts and truncated digests only)
"""Screen the 39 non-.eval context files under final_runs/ for token-shaped strings and account names (digest only).
Bytes decoded as UTF-8 with replacement (no parse). Usage: ctx.py <out.json>"""
import sys, re, json, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, __file__.rsplit('/',1)[0])
from gitread import tree, read
GH=re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"); ACC=re.compile(r"/(?:Users|home)/([^/\s\"'<>\\]{1,64})/")
dg=lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
out={"files":0,"by_kind":Counter(),"gh_token":defaultdict(Counter),"acct":defaultdict(Counter)}
for lab,oid in sorted(tree().items()):
    if lab.endswith('.eval'): continue
    kind=lab.rsplit('/',1)[1] if '.' not in lab.rsplit('/',1)[1][1:] else lab.rsplit('.',1)[1]
    txt=read(oid).decode('utf-8','replace'); out["files"]+=1; out["by_kind"][kind]+=1
    for t in GH.findall(txt): out["gh_token"][dg(t)][kind]+=1
    for m in ACC.finditer(txt): out["acct"][dg(m.group(1))][kind]+=1
json.dump(out,open(sys.argv[1],'w'),indent=1,sort_keys=True); print(json.dumps(out)[:1500])
