import sys, re
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, "tools/precheck")
import lx_lib
from l1_scan import SECRET_PATTERNS
GEN = SECRET_PATTERNS["generic-credential-assignment"]
E = lx_lib.entries(); R = lx_lib.Reader()
for lab, e in E.items():
    if not lab.endswith(".json") or lab.count("/") < 5: continue
    raw = R.raw(e).decode("utf-8", "replace")
    for m in GEN.finditer(raw):
        v = re.search(r"[A-Za-z0-9_\-/+=.]{16,}$", m.group(0)).group(0)
        print(lab.split("/")[0], lab.split("/")[1][-20:], "len", len(v), "alnum", sum(ch.isalnum() for ch in v), "distinct", len(set(v)), "kw_class", re.match(r"(?i)api[_-]?key|secret|token|passw", m.group(0)).group(0).lower()[:6])
