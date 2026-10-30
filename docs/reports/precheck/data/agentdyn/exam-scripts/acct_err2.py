import json, re, os, collections
from agentprov.ingest.loaders import strict_json_loads
ROOT = os.path.expanduser("~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn")
W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
PAT = re.compile(r"(/Users/|/home/|[A-Za-z]:\\+Users\\+)([^/\\\s\"'<>]{1,64})([/\\][^\s\"'<>]*)?")
TOK = ["site-packages", "/agentdojo/", "AgentDyn", ".venv", "conda", "lib/python", "Traceback", "File \""]
c = collections.Counter()
for part in "abc":
    for line in open(f"{W}/l1-units-{part}.jsonl"):
        r = json.loads(line)
        if not ({"account_path_named", "account_path_generic"} & set(r["flags"])):
            continue
        v = strict_json_loads(open(f"{ROOT}/{r['label']}", "rb").read())
        for m in v.get("messages") or ():
            if not isinstance(m, dict): continue
            for field in ("error", "content"):
                x = m.get(field)
                xs = [x] if isinstance(x, str) else [b.get("content") or b.get("text") for b in x if isinstance(b, dict)] if isinstance(x, list) else []
                for s in xs:
                    if not isinstance(s, str): continue
                    for mm in PAT.finditer(s):
                        tail = mm.group(3) or ""
                        hits = tuple(t for t in TOK if t in tail)
                        c[(part, m.get("role"), field, hits)] += 1
for k, n in sorted(c.items(), key=str): print(k, n)
