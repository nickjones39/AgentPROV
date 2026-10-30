import os, subprocess, sys
from collections import Counter
from agentprov.ingest.loaders import strict_json_loads
BARE, COMMIT = sys.argv[1], sys.argv[2]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
def git(*a): return subprocess.run(["git","-C",BARE,*a],capture_output=True,env=ENV,check=True).stdout
ents=[l.split("\t") for l in git("ls-tree","-r",COMMIT,"runs/").decode().splitlines()]
ents=[(p,m.split()[2]) for m,p in ents if len(p.split("/"))==6 and "-melon" in p.split("/")[1] and p.endswith(".json")]
c=Counter()
for p,oid in ents:
    d=strict_json_loads(git("cat-file","blob",oid)); ms=d.get("messages") or []
    a=[m for m in ms if m.get("role")=="assistant"]
    if not a: c["no_assistant"]+=1; continue
    last=a[-1]; cont=last.get("content")
    texts=[b.get("content") for b in cont] if isinstance(cont,list) else [cont]
    empty=all((t is None or (isinstance(t,str) and not t.strip())) for t in texts)
    if empty and not last.get("tool_calls"): c["last_assistant_empty_no_calls"]+=1
    if ms and ms[-1].get("role")=="assistant" and empty and not last.get("tool_calls"): c["final_msg_empty_assistant"]+=1
print(dict(c), len(ents))
