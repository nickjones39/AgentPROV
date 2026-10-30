"""L1-08 trailing_calls rows of sentry-agentdojo: label, last message role, whether its text content is empty, trailing
call count (counts only, no text). Usage (repo root): uv run python -I .../exam-scripts/trail.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader
W = os.path.expanduser("~/.agentprov/migration-work/precheck/sentry-agentdojo")
t = tree(); r = Reader()
for u in (json.loads(l) for l in open(f"{W}/l1-units-head.jsonl")):
    if "trailing_calls" not in u["flags"]: continue
    ms = r.json(t[u["label"]])["messages"]; m = ms[-1]
    txt = "".join(b.get("content") or "" for b in (m.get("content") or []) if isinstance(b, dict)) if isinstance(m.get("content"), list) else (m.get("content") or "")
    print(u["label"].split("/", 3)[3], m.get("role"), "text_empty=%s" % (not txt.strip()), "calls=%d" % len(m.get("tool_calls") or []), u["outcomes"])
