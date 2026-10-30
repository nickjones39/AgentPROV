import sys, re, json, hashlib
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, "tools/precheck")
import lx_lib
from l1_scan import SECRET_PATTERNS
GEN = SECRET_PATTERNS["generic-credential-assignment"]
E = lx_lib.entries(); R = lx_lib.Reader()
hits = []
for lab, e in E.items():
    if not lab.endswith(".json") or lab.count("/") < 5: continue
    raw = R.raw(e).decode("utf-8", "replace")
    for m in GEN.finditer(raw):
        hits.append((lab, m.start(), m.group(0)))
lab, pos, s = hits[0]
v = re.search(r"[A-Za-z0-9_\-/+=.]{16,}$", s).group(0)
dg = hashlib.sha256(v.encode()).hexdigest()[:12]
p = lab.split("/"); print("root", p[0], "suite", p[2], "task", p[3], "attack", p[4], "file", p[5][:-5], "digest", dg)
raw = R.raw(E[lab]).decode()
x = json.loads(raw)
def walk(n, ptr):
    if isinstance(n, dict):
        for k, w in n.items():
            if isinstance(w, str) and v in w: print("ptr", ptr + "/" + k, "key_is_kw", bool(re.search("(?i)passw", k)))
            walk(w, ptr + "/" + (k if not k.isdigit() else "*"))
    elif isinstance(n, list):
        for w in n: walk(w, ptr + "/*")
walk(x, "")
# recurrence of the value across logs and in tool results / user prompts
n = sum(1 for l, e in E.items() if l.endswith(".json") and v.encode() in R.raw(e))
print("logs containing value", n)
ctx = re.sub(r"[A-Za-z0-9]", "x", raw[max(0,pos-60):pos])
print("left-context shape", ctx[-60:])
