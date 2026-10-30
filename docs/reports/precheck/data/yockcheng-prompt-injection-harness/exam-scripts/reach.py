"""Population payload reach: for each attacked log, is any logged injection value (whitespace-collapsed) a substring of a
tool result (whitespace-collapsed)? Counts and labels only, payload text never printed. Usage: reach.py <repo> <out.json>"""
import sys, json, re
from collections import Counter
from pathlib import Path
REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
bare = Path.home() / ".agentprov/staging/10c/yockcheng/prompt-injection-harness.git"
src = s.GitSource(bare, "5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6")
rows = {json.loads(l)["label"]: json.loads(l) for l in open(Path.home() / ".agentprov/migration-work/precheck/yockcheng-prompt-injection-harness/l1-units-head.jsonl")}
rd = s.GitBlobReader(str(bare))
ws = lambda t: re.sub(r"\s+", " ", t).strip()
res = Counter(); per = {}; by_arm = Counter(); vec = Counter()
for e in src.entries():
    if e.label not in rows or rows[e.label]["facets"]["attack_dir"] != "important_instructions": continue
    o = strict_json_loads(rd.read(e.sha1), IngestLimits())
    tool = []
    for m in o.get("messages") or []:
        if m.get("role") == "tool":
            c = m.get("content")
            if isinstance(c, list): tool += [b.get("content") or b.get("text") or "" for b in c if isinstance(b, dict)]
            elif isinstance(c, str): tool.append(c)
    joined = " ".join(t for t in tool if isinstance(t, str))
    blob = ws(joined) + " || " + ws(joined.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'"))
    blob = blob + " || " + ws(re.sub(r"'\s*'", "", joined.replace("''", "'")))
    inj = o.get("injections") or {}
    hit = [k for k, v in inj.items() if isinstance(v, str) and ws(v) and ws(v) in blob]
    # partial: the first 60 collapsed chars
    part = [k for k, v in inj.items() if isinstance(v, str) and ws(v)[:60] in blob] if not hit else hit
    st = "present" if hit else ("partial" if part else "absent")
    arm = f"{rows[e.label]['facets']['pipeline_dir']}|{o.get('benchmark_version')}"
    by_arm[f"{arm}|{st}"] += 1; res[st] += 1
    for k in inj: vec[k] += 1
    per[e.label] = {"status": st, "n_injections": len(inj), "tool_msgs": len(tool), "security": o.get("security")}
out = {"status": dict(res), "by_arm": dict(sorted(by_arm.items())), "vectors": dict(vec), "per_label": per}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, sort_keys=True))
print(json.dumps({k: v for k, v in out.items() if k != "per_label"}, indent=1, sort_keys=True))
