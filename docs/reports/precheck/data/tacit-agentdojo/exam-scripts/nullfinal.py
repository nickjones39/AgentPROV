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
c = co.Counter(); out = []
for lab in labels:
    d = strict_json_loads(read(lab)); m = d["messages"]
    nn = [i for i, x in enumerate(m) if x["role"] == "assistant" and x.get("content") is None]
    if nn: c["logs_with_any_none_assistant"] += 1
    last = m[-1]
    if last["role"] == "assistant" and "content" in last and last["content"] is None:
        c["last_content_none"] += 1; out.append((lab, bool(last.get("tool_calls")), d.get("utility"), d.get("security")))
    c[f"last_content_type:{type(last.get('content')).__name__}"] += 1
print(dict(c)); [print(o) for o in out]
