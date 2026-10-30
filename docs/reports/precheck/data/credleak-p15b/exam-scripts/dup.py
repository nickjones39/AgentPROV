"""credleak-p15b: identical run trajectories (L1 per-run fingerprints, tool names+inputs+outputs+texts) by scope:
within one cell, across cells of one (model, scenario), across models; cell pairs sharing runs; and a name-blind test of
the frequent named home-dir account against common container/service user names (digests compared, names never printed).
Usage: python -I dup.py <exam-scripts dir> <out.json>
"""
import sys, json, os, collections, hashlib, re
sys.path.insert(0, sys.argv[1]); from rawlib import cells
C = collections.Counter
fp = collections.defaultdict(list); meta = {}
for line in open(os.path.expanduser("~/.agentprov/migration-work/precheck/_fp/credleak-p15b.head.jsonl")):
    x = json.loads(line); fp[x["fp"]].append((x["label"], x["unit"]))
calls = {}; facet = {}
ACC = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/([^/\s\"'<>\\]{1,64})?")
TARGET = "<account-F>"
nxt = C(); owner_col = 0; candidates = ["model", "codex", "owner", "human", "devin", "cline", "goose", "aider", "bench", "agent0",
    "tester", "victim", "worker", "nobody", "appuser", "daemon", "build", "linux", "debian", "kali", "vagrant", "claude",
    "openai", "gemini", "coding", "hacker", "target", "attacker", "project", "repo", "code", "dev1", "app", "pwuser", "ubuntu",
    "playground", "space", "home", "local", "host", "server", "admin1", "operator", "service", "bot", "tool", "work1", "ctf"]
cand_hit = [c for c in candidates if hashlib.sha256(c.encode()).hexdigest()[:12] == TARGET]
for label, d in cells():
    for i, r in enumerate(d.get("runs", [])):
        u = (label, f"/runs/{i}")
        calls[u] = sum(len(t.get("toolCalls") or []) for t in r.get("turns", []))
        facet[u] = (d.get("model"), d.get("scenario"), label.rsplit("/", 1)[1].split("__")[0])
        for t in r.get("turns", []):
            for c in t.get("toolCalls") or []:
                for m in ACC.finditer(c.get("output") or ""):
                    if hashlib.sha256(m.group(1).encode("utf-8", "surrogatepass")).hexdigest()[:12] == TARGET:
                        nxt[hashlib.sha256((m.group(2) or "").encode("utf-8", "surrogatepass")).hexdigest()[:8]] += 1
res = C(); pairs = C(); cross_examples = C()
for g in fp.values():
    if len(g) < 2: continue
    cellset = {l for l, _ in g}; models = {facet[u][0] for u in g}; scen = {facet[u][1] for u in g}; batch = {facet[u][2] for u in g}
    wc = any(calls[u] for u in g)
    scope = "within_cell" if len(cellset) == 1 else ("cross_model" if len(models) > 1 else ("cross_scenario" if len(scen) > 1 else "cross_cell_same_model_scenario"))
    res[f"{scope}:groups"] += 1; res[f"{scope}:runs"] += len(g); res[f"{scope}:groups_with_calls"] += wc
    res[f"{scope}:runs_with_calls"] += sum(1 for u in g if calls[u])
    if len(cellset) > 1:
        cross_examples[f"{scope}|batches={'+'.join(sorted(batch))}"] += 1
        cl = sorted(cellset)
        for a in range(len(cl)):
            for b in range(a + 1, len(cl)): pairs[(cl[a], cl[b])] += 1
top = sorted(pairs.items(), key=lambda kv: -kv[1])[:8]
out = dict(format="credleak-p15b-exam-dup/1", scopes=dict(sorted(res.items())), cross_cell_by_batches=dict(sorted(cross_examples.items())),
           cell_pairs_sharing=len(pairs), top_cell_pairs=[dict(a=a, b=b, shared_groups=n) for (a, b), n in top],
           account_9386=dict(candidate_generic_match=cand_hit, next_segment_digests=dict(nxt.most_common(6)),
                             next_segment_distinct=len(nxt)))
json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True); print(json.dumps(out, indent=0, sort_keys=True))
