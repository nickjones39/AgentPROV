# ruff: noqa  (precheck verifier script for agentops-bench; read-only; usage: uv run python -I <this> <traces.tar.gz>)
import fnmatch, json, re, sys, hashlib
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
GLOBS = ("pilot_v1_seeded/*/*/adversarial/*_run*.json", "pilot_v1_seeded/*/*/clean/safety_*_run*.json", "pilot_v1_seeded/*/*/noisy/safety_*_run*.json")
RUN = re.compile(r"_\d{3}_run\d+\.json$")
ACCT = re.compile(r"(/Users/|/home/)([^/\s\"'\\]+)(.?)")
def strings(v, p=""):
    if isinstance(v, str): yield p, v
    elif isinstance(v, dict):
        for k, x in v.items(): yield from strings(x, p+"/"+k)
    elif isinstance(v, list):
        for x in v: yield from strings(x, p+"/*")
c = Counter(); fl = defaultdict(set); ea = Counter()
with open(Path(sys.argv[1]).expanduser(), "rb") as fp, open_archive(fp, IngestLimits(), release=False) as t:
    for m in t.iter_members(lambda l: "/._" not in l and l.endswith(".json"), IngestLimits()):
        if m.disposition != "selected": continue
        try: r = strict_json_loads(t.read_member(m))
        except Exception: continue
        insc = any(fnmatch.fnmatchcase(m.label, g) for g in GLOBS); kind = "insc" if insc else ("run_oos" if RUN.search(m.label) else "side")
        for p, v in strings(r):
            for mm in ACCT.finditer(v):
                nm = mm.group(2); d = hashlib.sha256(nm.encode()).hexdigest()[:8]
                nxt = mm.group(3); nc = "slash" if nxt == "/" else ("end" if nxt == "" else "alpha" if nxt.isalnum() else "punct")
                shp = ("lower" if nm.islower() else "mixed") + f"len{len(nm)}"
                c[f"{kind}|{mm.group(1)}{d}|{nc}|{shp}"] += 1; fl[f"{kind}|{mm.group(1)}{d}"].add(m.label)
        if insc and m.label.split("/")[2].startswith("openrouter_meta-llama"):
            tr = r.get("trace") or {}; st = tr.get("steps") or []
            if st and not any((s.get("reasoning") or "").strip() or s.get("tool_calls") for s in st):
                ea[f"cond={m.label.split('/')[3]}|llm_out={st[0].get('llm_output_tokens')}|tot_out={tr.get('total_output_tokens')}|n_steps={len(st)}"] += 1
                ea[f"domain={m.label.split('/')[4].split('_')[0]}"] += 1
print(json.dumps({"c": dict(c), "files": {k: len(v) for k, v in fl.items()}, "ea": dict(ea)}, indent=1))
