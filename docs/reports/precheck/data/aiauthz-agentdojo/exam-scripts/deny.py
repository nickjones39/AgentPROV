"""Denial detail per log (tool, kind) and L1-10 hit shape classes (booleans only, never the value). usage: uv run python -I deny.py"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
t = tree(); r = Reader()
rows = []
for lab in sorted(p for p in t if p.startswith("experiments/agentdojo/runs/")):
    parts = lab.split("/"); d = r.json(t[lab])
    for m in d["messages"]:
        if m.get("role") == "tool" and isinstance(m.get("error"), str) and m["error"].startswith("Blocked by aiAuthZ policy: "):
            rows.append(dict(model=parts[3], cond=parts[4], task=parts[7], inj=parts[9][:-5], tool=m["tool_call"]["function"],
                             reason_class=m["error"][len("Blocked by aiAuthZ policy: "):].split(":")[0][:40]))
print(json.dumps(rows, indent=0))
SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?([A-Za-z0-9_\-/+=.]{16,})")
for p in ("experiments/agentdojo/RESULTS.md",):
    txt = r.read(t[p]).decode("utf-8", "replace")
    for m in SECRET.finditer(txt):
        v = m.group(1)
        print(p, dict(rhs_len=len(v), upper_snake=bool(re.fullmatch(r"[A-Z0-9_]+", v)), lower_snake=bool(re.fullmatch(r"[a-z0-9_.\-]+", v)),
                      has_digit=any(c.isdigit() for c in v), placeholder=bool(re.search(r"(?i)your|xxx|example|\.\.\.", v)),
                      known_key_prefix=bool(re.match(r"sk-|sk_|AIza|gh[pousr]_|hf_", v))))
