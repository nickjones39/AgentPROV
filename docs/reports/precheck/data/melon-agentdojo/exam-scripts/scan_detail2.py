import json, os, re, subprocess, sys
from collections import Counter
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.quote import quote_untrusted
BARE, COMMIT = sys.argv[1], sys.argv[2]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
SAN = "[已移除潜在注入内容]"
CJK = re.compile(r"[㐀-鿿　-〿＀-￯]+[^\n]{0,40}")
def git(*a): return subprocess.run(["git","-C",BARE,*a],capture_output=True,env=ENV,check=True).stdout
def text_of(c):
    if isinstance(c,str): return c
    if isinstance(c,list): return "\n".join((b.get("content") or b.get("text") or "") for b in c if isinstance(b,dict) and isinstance((b.get("content") or b.get("text") or ""),str))
    return ""
ents=[l.split("\t") for l in git("ls-tree","-r",COMMIT,"runs/").decode().splitlines()]
ents=[(p,m.split()[2]) for m,p in ents if "-melon_r" in p.split("/")[1] and p.endswith(".json")]
c=Counter(); frags=Counter()
for p,oid in ents:
    d=strict_json_loads(git("cat-file","blob",oid)); pd=p.split('/')[1]
    for i,m in enumerate(d.get("messages") or []):
        t=text_of(m.get("content"))
        if m.get("role")=="tool" and SAN in t:
            c[("eq" if t.strip()==SAN else "contains")+":"+pd]+=1
        if m.get("role")=="tool" and SAN not in t:
            for f in CJK.findall(t): frags[f[:50]]+=1
        if m.get("role")=="system" and i>0:
            tt=text_of(m.get("content"))
            if "a021" and len(tt) in (117,129): frags["SYS:"+tt[:40]]+=1
        if m.get("role")=="assistant" and re.search(r"[一-鿿]",t): frags["ASST:"+t[:40]]+=1
print(dict(c))
for f,n in frags.items(): print(n, quote_untrusted(f, "fragment", max_chars=60).replace("\n"," | "))
