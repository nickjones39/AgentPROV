"""credleak-p15b: redaction-marker strings in the 643 cells by field, and co-occurrence with the frequent named home-dir
account digest in the same run. Counts only. Usage: python -I redmark.py <exam-scripts dir>"""
import sys, re, json, hashlib, collections
sys.path.insert(0, sys.argv[1]); from rawlib import cells
RED = re.compile(r"(?i)redacted"); ACC = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
c = collections.Counter()
for label, d in cells():
    for r in d.get("runs", []):
        hasred = hasacc = False
        for t in r.get("turns", []):
            for fld, s in [("assistant", t.get("assistantResponse") or ""), ("user", t.get("userMessage") or "")] + \
                    [("tool_output", x.get("output") or "") for x in t.get("toolCalls") or []] + \
                    [("tool_input", json.dumps(x.get("input"))) for x in t.get("toolCalls") or []]:
                n = len(RED.findall(s)); c[f"marker:{fld}"] += n; hasred |= bool(n)
                hasacc |= any(hashlib.sha256(m.group(1).encode("utf-8","surrogatepass")).hexdigest()[:12] == "<account-F>" for m in ACC.finditer(s))
        c["runs_with_marker"] += hasred; c["runs_with_9386"] += hasacc; c["runs_with_both"] += hasred and hasacc
print(json.dumps(dict(c), sort_keys=True))
