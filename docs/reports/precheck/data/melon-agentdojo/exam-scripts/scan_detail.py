import json, os, re, subprocess, sys
from collections import Counter
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.quote import quote_untrusted
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BARE, COMMIT = sys.argv[1], sys.argv[2]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
SAN = "[已移除潜在注入内容]"
CJK = re.compile(r"[㐀-鿿　-〿＀-￯]")
def git(*a, data=None): return subprocess.run(["git","-C",BARE,*a],capture_output=True,env=ENV,check=True,input=data).stdout
def text_of(c):
    if isinstance(c,str): return c
    if isinstance(c,list): return "\n".join(b.get("content") or b.get("text") or "" for b in c if isinstance(b,dict) and isinstance(b.get("content") or b.get("text") or "",str))
    return ""
ents=[l.split("\t") for l in git("ls-tree","-r",COMMIT,"runs/").decode().splitlines()]
ents=[(p,m.split()[2]) for m,p in ents if "-melon_r" in p.split("/")[1] and p.endswith(".json")]
c=Counter(); shown=0; samples={}
for p,oid in ents:
    d=strict_json_loads(git("cat-file","blob",oid))
    for i,m in enumerate(d.get("messages") or []):
        t=text_of(m.get("content"))
        if m.get("role")=="tool" and SAN in t:
            c["san_eq" if t.strip()==SAN else "san_contains"]+=1
            c["san_occurrences"]+=t.count(SAN)
        if m.get("role")=="tool" and CJK.search(t) and SAN not in t:
            k=t[:60]
            c["cjk_other:"+p.split('/')[1]]+=1
            if shown<4: print(quote_untrusted(t[:120], f"{p.split('/')[1]}/{p.split('/')[2]}/msg{i}", max_chars=120)); shown+=1
        if m.get("role")=="system" and i>0 and "a021" not in "":
            pass
print(dict(c))
