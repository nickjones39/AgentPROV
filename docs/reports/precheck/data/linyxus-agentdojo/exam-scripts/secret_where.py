"""L1-06 hit: where the one generic-credential-assignment value occurs (labels' facet classes and JSON pointer classes only;
never the value). Usage (repo root): uv run python -I docs/reports/precheck/data/linyxus-agentdojo/exam-scripts/secret_where.py"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lx_lib  # noqa: E402
from l1_scan import SECRET_PATTERNS  # noqa: E402
E = lx_lib.entries(); R = lx_lib.Reader()
rows = [json.loads(l) for l in open(lx_lib.W / "l1-units-head.jsonl")]
GEN = SECRET_PATTERNS["generic-credential-assignment"]
val = None
for u in rows:
    so = R.load(E[u["label"]]).get("tacit_secure_output")
    if isinstance(so, str) and GEN.search(so):
        val = re.split(r"[:=]", GEN.search(so).group(0), maxsplit=1)[1].strip(" \"'"); break
def walk(o, p):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, p + "/" + (k if k not in ("content",) or True else k))
    elif isinstance(o, list):
        for v in o: yield from walk(v, p + "/*")
    elif isinstance(o, str) and val in o:
        yield p
out = []
for u in rows:
    x = R.load(E[u["label"]])
    ps = sorted(set(walk(x, "")))
    if ps:
        f = u["facets"]
        roles = sorted({m.get("role") for m in x.get("messages") or [] if val in json.dumps(m)})
        out.append({"run_set": f["run_set"], "pipeline_dir": f["pipeline_dir"], "suite": f["suite"], "task_kind": f["task_kind"],
                    "task_dir": f["task_dir"], "file": f["file"], "pointers": ps, "message_roles": roles,
                    "charclass": "".join(sorted({("A" if c.isupper() else "a" if c.islower() else "9" if c.isdigit() else "s") for c in val}))})
print(json.dumps(out, indent=0))
