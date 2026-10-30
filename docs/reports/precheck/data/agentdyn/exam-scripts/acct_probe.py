"""L1-06 follow-up: are the named account paths benchmark content? Counts and digests only, never a name."""
import json, sys, re, os, glob, hashlib, collections
from agentprov.ingest.loaders import strict_json_loads

ROOT = os.path.expanduser("~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn")
W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
PATS = {"users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"), "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/"),
        "windows-users": re.compile(r"(?i)[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+([^\\/\s\"'<>]{1,64})")}
GENERIC = {"ubuntu", "user", "root", "runner", "app", "node", "admin", "agent", "dev", "test", "shared"}

def walk(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield k; yield from walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from walk(x)

# benchmark-side text: every text file under src/ except the run logs (task, environment and tool definitions)
env_text = []
for p in glob.glob(f"{ROOT}/src/**/*", recursive=True):
    if os.path.isfile(p) and "/runs/" not in p and p.endswith((".yaml", ".yml", ".py", ".json", ".txt", ".md")) and os.path.getsize(p) < 8_000_000:
        with open(p, "rb") as fh:
            env_text.append(fh.read().decode("utf-8", "replace"))
env_blob = "\n".join(env_text)
env_names = {cls: set(m.group(1) for m in pat.finditer(env_blob)) for cls, pat in PATS.items()}

res = collections.Counter(); per_name = collections.defaultdict(lambda: {"files": 0, "dirs": set(), "in_env_path": False, "in_env_text": False, "parts": set()})
for part in "abc":
    for line in open(f"{W}/l1-units-{part}.jsonl"):
        r = json.loads(line)
        if "account_path_named" not in r["flags"]:
            continue
        with open(f"{ROOT}/{r['label']}", "rb") as fh:
            v = strict_json_loads(fh.read())
        seen = set()
        for s in walk(v):
            for cls, pat in PATS.items():
                for m in pat.finditer(s):
                    n = m.group(1)
                    if n.lower() in GENERIC:
                        continue
                    seen.add((cls, n))
        for cls, n in seen:
            e = per_name[(cls, n)]
            e["files"] += 1; e["dirs"].add(r["facets"]["pipeline_dir"]); e["parts"].add(part)
            e["in_env_path"] = n in env_names[cls]
            e["in_env_text"] = n in env_blob
        res[part] += 1
summary = []
for (cls, n), e in sorted(per_name.items(), key=lambda kv: -kv[1]["files"]):
    summary.append({"class": cls, "name_digest": hashlib.sha256(n.encode()).hexdigest()[:12], "files": e["files"], "dirs": len(e["dirs"]),
                    "parts": "".join(sorted(e["parts"])), "in_benchmark_path": e["in_env_path"], "in_benchmark_text": e["in_env_text"]})
out = {"files_flagged_named": dict(res), "distinct_named": len(summary),
       "not_in_benchmark_text": sum(1 for s in summary if not s["in_benchmark_text"]),
       "files_with_name_not_in_benchmark_text": sum(s["files"] for s in summary if not s["in_benchmark_text"]), "names": summary}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "names"}))
for s in summary:
    print(s)
