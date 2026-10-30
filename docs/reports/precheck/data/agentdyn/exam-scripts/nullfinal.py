import json, glob, os, collections
from agentprov.ingest.loaders import strict_json_loads
ROOT = os.path.expanduser("~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn")
W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
l1 = {json.loads(l)["label"]: json.loads(l) for l in open(f"{W}/l1-units-a.jsonl")}
c = collections.Counter()
for p in glob.glob(f"{W}/l2-a-j2.partial/aer/*/*.aer.jsonl"):
    label = None; hit = False
    for line in open(p):
        r = json.loads(line)
        if r["k"] == "execution": label = r["artifacts"][0]["origin"]["path"]
        rl = r.get("rule") or []
        rl = rl if isinstance(rl, list) else [rl]
        if any("last_assistant_content_none" in x for x in rl): hit = True
    v = strict_json_loads(open(f"{ROOT}/{label}", "rb").read())
    msgs = v.get("messages") or []
    last = msgs[-1] if msgs else None
    la = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "assistant"), None)
    def shape(m):
        if m is None: return "none"
        ct = m.get("content")
        if ct is None: cs = "null"
        elif isinstance(ct, str): cs = "str_empty" if ct == "" else "str"
        elif isinstance(ct, list): cs = "list_empty" if not ct else ("blocks_all_empty" if all(isinstance(b, dict) and not (b.get("content") or b.get("text")) for b in ct) else "blocks")
        else: cs = type(ct).__name__
        return f"{m.get('role')}:{cs}:calls={'y' if m.get('tool_calls') else 'n'}"
    c[(hit, "l1_null_final" in l1[label]["flags"] or "null_final" in l1[label]["flags"], shape(last), shape(la))] += 1
for k, n in sorted(c.items(), key=str): print(n, k)
