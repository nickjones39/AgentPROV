import collections as co, json, os, subprocess
from agentprov.ingest.loaders import strict_json_loads
BARE = os.path.expanduser("~/.agentprov/staging/10c/tacit/Tacit.git"); C = "995692d3cd42c32e08cf0db8a5fae55fec272f1a"
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
W = os.path.expanduser("~/.agentprov/migration-work/precheck/tacit-agentdojo")
labels = [json.loads(l)["label"] for l in open(f"{W}/l1-units-head.jsonl")]
p = subprocess.Popen(["git", "-C", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=ENV)
def read(label):
    p.stdin.write(f"{C}:{label}\n".encode()); p.stdin.flush()
    n = int(p.stdout.readline().split()[2]); d = p.stdout.read(n); p.stdout.read(1); return d
c = co.Counter()
for lab in labels:
    m = strict_json_loads(read(lab))["messages"]
    la = next((x for x in reversed(m) if x["role"] == "assistant"), None)
    if la is None: c["no_assistant"] += 1; continue
    cont = la.get("content"); calls = bool(la.get("tool_calls"))
    if cont is None: c[f"last_assistant_none:calls={calls}"] += 1
    elif isinstance(cont, list) and all(isinstance(b, dict) and b.get("type") == "text" and b.get("content") in (None, "") for b in cont):
        c[f"last_assistant_exact_empty_blocks:calls={calls}:n_blocks={len(cont)}"] += 1
print(dict(c))
