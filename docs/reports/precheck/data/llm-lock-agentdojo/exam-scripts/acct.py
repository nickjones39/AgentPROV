"""llm-lock-agentdojo L1-06 follow-up: the 10 logs flagged account_path_* and the 57 secret_like logs; counts, classes,
roles and truncated digests only (no names, no values). Usage: uv run python -I acct.py <l1-units> <bare> <commit> <out>"""
import hashlib, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pop_io import tree, Reader, text
from agentprov.ingest.loaders import strict_json_loads
UNITS, BARE, COMMIT, OUT = sys.argv[1:5]
PAT = {"users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"), "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/"),
       "windows-users": re.compile(r"(?i)[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+([^\\/\s\"'<>]{1,64})")}
CRED = re.compile(r"(?i)(api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?([A-Za-z0-9_\-/+=.]{16,})")
OP = os.path.basename(os.path.expanduser("~")).lower()
AUTH = {"wakeful-cloud", "wakefulcloud", "wakeful"}
t = tree(BARE, COMMIT); r = Reader(BARE)
names = defaultdict(Counter); cred = Counter(); credv = defaultdict(Counter)
for ln in open(UNITS, encoding="utf-8"):
    row = json.loads(ln)
    fl = set(row["flags"])
    if not fl & {"account_path_generic", "account_path_named", "secret_like"}: continue
    f = row["facets"]
    x = strict_json_loads(r.read(t[row["label"]])); ms = x["messages"]
    env_text = "\n".join(text(m.get("content")) for m in ms if m.get("role") in ("tool", "user", "system")).lower()
    for m in ms:
        blobs = [("content", text(m.get("content")))] + [("tool_call_args", json.dumps(tc.get("args"))) for tc in (m.get("tool_calls") or [])]
        if m.get("role") == "tool" and isinstance(m.get("tool_call"), dict): blobs.append(("tool_call_args", json.dumps(m["tool_call"].get("args"))))
        for where, s in blobs:
            for cls, rx in PAT.items():
                for mm in rx.finditer(s):
                    nm = mm.group(1).lower(); d = hashlib.sha256(nm.encode()).hexdigest()[:8]
                    n = names[f"{cls}|{d}"]; n["strings"] += 1; n[f"role={m.get('role')}|{where}"] += 1
                    n["operator"] = int(nm == OP); n["repo_author"] = int(nm in AUTH); n["len"] = len(nm)
                    n["in_env_text_of_log"] = max(n["in_env_text_of_log"], int(nm in env_text))
                    n["files"] += 0; n[f"suite={f['suite']}"] += 1
            for mm in CRED.finditer(s):
                k = mm.group(1).lower(); v = hashlib.sha256(mm.group(2).encode()).hexdigest()[:8]
                cred[f"key={k}|role={m.get('role')}|{where}|suite={f['suite']}"] += 1; credv[v]["strings"] += 1
                credv[v]["value_in_env_text"] = max(credv[v]["value_in_env_text"], int(mm.group(2).lower() in env_text))
r.close()
out = {"account_names": {k: dict(v) for k, v in names.items()}, "credential_assignments": dict(cred),
       "credential_values_distinct": len(credv), "credential_values": {k: dict(v) for k, v in sorted(credv.items(), key=lambda kv: -kv[1]["strings"])[:10]}}
json.dump(out, open(OUT, "w"), indent=1); print(json.dumps(out, indent=1))
