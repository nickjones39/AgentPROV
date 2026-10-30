"""Verifier PC-01: for target account digests, domain/split/framework distribution, bare-name presence in the task tree,
second path component (whitelisted labels only), first pointer class per file. Digests and counts only.
Usage: python -I v_acc.py <runs_root> <tasks_root> <lfs_dir> <l1-units> <out.json> <digest,digest,...>"""
import collections, hashlib, json, os, re, sys
runs, tasks, lfs, units, out = sys.argv[1:6]
TARGET = set(sys.argv[6].split(","))
from agentprov.ingest.limits import MIB, IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../../tools/precheck"))
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS
LIM = IngestLimits().replace(max_json_bytes=512 * MIB)
LFS = b"version https://git-lfs.github.com/spec/v1\n"
def load(label):
    with open_evidence(runs, label, LIM) as h: data = h.read()
    if data.startswith(LFS):
        oid = re.search(rb"\noid sha256:([0-9a-f]{64})\n", data).group(1).decode()
        with open_evidence(lfs, oid, LIM) as h: data = h.read()
    return strict_json_loads(data)
def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, f"{p}/{k}")
    elif isinstance(o, list):
        for v in o: yield from walk(v, p + "/*")
    elif isinstance(o, str): yield (p, o)
WL = {"Desktop","Documents","Downloads",".openclaw",".claude","workspace","projects","project","code","work","repos","src","tmp",".config",".local",".cache","data","dt-agent","DecodingTrust-Agent","Pictures","Music","Videos","AppData","Library",".ssh",".bashrc"}
rows = [json.loads(l) for l in open(units)]
named = [r for r in rows if "account_path_named" in r["flags"]]
R = collections.defaultdict(lambda: {"domain": collections.Counter(), "split": collections.Counter(), "fw": collections.Counter(),
     "second": collections.Counter(), "first_class": collections.Counter(), "in_task_info_same_file": 0, "in_instruction_bare": 0})
names = {}
for r in named:
    d = load(r["label"]); f = r["facets"]; seenfile = {}
    strs = list(walk(d))
    ti = " ".join(v for p, v in strs if p.startswith("/task_info"))
    for p, v in strs:
        for nm, rx in ACCOUNT_PATTERNS.items():
            for m in rx.finditer(v):
                a = m.group(1)
                if a.lower() in GENERIC_ACCOUNTS or (nm == "users-dir" and a.lower() == "shared"): continue
                dg = nm + ":" + hashlib.sha256(a.encode("utf-8", "surrogatepass")).hexdigest()[:16]
                if dg not in TARGET: continue
                names[dg] = a; e = R[dg]
                rest = v[m.end():].lstrip("/\\").split("/")[0].split("\\")[0]
                e["second"][rest if rest in WL else ("<empty>" if not rest else "other")] += 1
                if dg not in seenfile:
                    seenfile[dg] = 1
                    e["domain"][f.get("domain")] += 1; e["split"][f.get("split_label")] += 1; e["fw"][f"{f.get('framework')}|{f.get('model')}"] += 1
                    c = "task_info" if p.startswith("/task_info") else ("agent" if re.search(r"/(action|metadata/message|agent_final_response|tool_params)", p) else "tool_or_other")
                    e["first_class"][c] += 1
                    if re.search(r"(?i)\b" + re.escape(a) + r"\b", ti): e["in_instruction_bare"] += 1
# bare name in task tree (any text file)
tt = collections.Counter(); ttfiles = collections.Counter()
pats = {dg: re.compile(r"(?i)\b" + re.escape(a) + r"\b") for dg, a in names.items()}
for dp, dns, fs in os.walk(tasks):
    dns[:] = [x for x in dns if x != ".git"]
    for fn in fs:
        rel = os.path.relpath(os.path.join(dp, fn), tasks)
        try:
            with open_evidence(tasks, rel, LIM) as h: t = h.read(8 * MIB).decode("utf-8", "replace")
        except Exception: continue
        for dg, rx in pats.items():
            if rx.search(t): ttfiles[dg] += 1
res = {dg: {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in e.items()} | {"bare_name_task_tree_files": ttfiles[dg], "name_len": len(names[dg]), "name_has_digit": any(c.isdigit() for c in names[dg])} for dg, e in R.items()}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res, indent=0))
