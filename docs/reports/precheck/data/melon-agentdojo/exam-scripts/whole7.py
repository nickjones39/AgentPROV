import os, subprocess, sys
from agentprov.ingest.loaders import strict_json_loads
BARE, COMMIT = sys.argv[1], sys.argv[2]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
SAN = "[已移除潜在注入内容]"
def git(*a): return subprocess.run(["git","-C",BARE,*a],capture_output=True,env=ENV,check=True).stdout
for l in git("ls-tree","-r",COMMIT,"runs/").decode().splitlines():
    m,p=l.split("\t")
    if "-melon_r" not in p.split("/")[1] or not p.endswith(".json"): continue
    d=strict_json_loads(git("cat-file","blob",m.split()[2]))
    n=0
    for x in d.get("messages") or []:
        c=x.get("content"); t="\n".join(b.get("content") or "" for b in c if isinstance(b,dict) and isinstance(b.get("content"),str)) if isinstance(c,list) else (c or "")
        if x.get("role")=="tool" and t.strip()==SAN: n+=1
    if n: print(p.split("/")[1], p.split("/")[2], "incomplete" if "utility" not in d else "complete", "whole", n)
