import json, os, subprocess
from agentprov.ingest.loaders import strict_json_loads
BARE = os.path.expanduser("~/.agentprov/staging/10c/tacit/Tacit.git"); C = "995692d3cd42c32e08cf0db8a5fae55fec272f1a"
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
W = os.path.expanduser("~/.agentprov/migration-work/precheck/tacit-agentdojo")
labels = [json.loads(l)["label"] for l in open(f"{W}/l1-units-head.jsonl") if "qwen3" in l]
p = subprocess.Popen(["git", "-C", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=ENV)
def read(label):
    p.stdin.write(f"{C}:{label}\n".encode()); p.stdin.flush()
    n = int(p.stdout.readline().split()[2]); d = p.stdout.read(n); p.stdout.read(1); return d
for lab in labels:
    d = strict_json_loads(read(lab)); m = d["messages"]
    for i, x in enumerate(m):
        if x["role"] == "assistant" and not x.get("tool_calls"):
            t = "".join(b.get("content") or "" for b in (x.get("content") or []) if isinstance(b, dict))
            if "<tool_call>" in t: print(lab.split("/", 2)[2], "turn", i, "of", len(m), "final" if i == len(m) - 1 else "mid", "u", d["utility"], "s", d["security"], "tags", t.count("<tool_call>"))
