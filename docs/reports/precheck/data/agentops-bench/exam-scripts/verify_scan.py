# ruff: noqa  (precheck verifier script for agentops-bench; read-only; usage: uv run python -I <this> <traces.tar.gz>)
import fnmatch, json, re, sys, hashlib, os, math
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
GLOBS = ("pilot_v1_seeded/*/*/adversarial/*_run*.json", "pilot_v1_seeded/*/*/clean/safety_*_run*.json", "pilot_v1_seeded/*/*/noisy/safety_*_run*.json")
ACCT = re.compile(r"(/Users/|/home/)([^/\s\"'\\]+)")
OP = hashlib.sha256(os.environ.get("USER","").encode()).hexdigest()[:8]
def strings(v, p=""):
    if isinstance(v, str): yield p, v
    elif isinstance(v, dict):
        for k, x in v.items(): yield from strings(x, p+"/"+k)
    elif isinstance(v, list):
        for x in v: yield from strings(x, p+"/*")
def shape(v):
    if isinstance(v, dict): return {k: shape(x) for k, x in v.items()}
    if isinstance(v, list): return [shape(v[0])] if v else []
    if isinstance(v, str): return "str" if v.strip() else "emptystr"
    return type(v).__name__
acc = Counter(); names = defaultdict(set); runs = defaultdict(set); allf = defaultdict(set)
empty = Counter(); eshape = Counter(); etok = Counter(); n=0
with open(Path(sys.argv[1]).expanduser(), "rb") as fp, open_archive(fp, IngestLimits(), release=False) as t:
    for m in t.iter_members(lambda l: "/._" not in l and l.endswith(".json"), IngestLimits()):
        if m.disposition != "selected": continue
        try: r = strict_json_loads(t.read_member(m))
        except Exception: continue
        insc = any(fnmatch.fnmatchcase(m.label, g) for g in GLOBS)
        for p, v in strings(r):
            for mm in ACCT.finditer(v):
                nm = mm.group(2); d = hashlib.sha256(nm.encode()).hexdigest()[:8]
                allf[mm.group(1)+d].add(m.label)
                if not insc: continue
                k = mm.group(1)+"|"+re.sub(r"/[0-9]+","/*",p)
                acc[k+"|"+d] += 1; names[mm.group(1)].add(d); runs[mm.group(1)+d].add(m.label)
        if not insc or not isinstance(r, dict): continue
        n += 1
        tr = r.get("trace") or {}; st = tr.get("steps") or []
        if st and not any((s.get("reasoning") or "").strip() or s.get("tool_calls") for s in st):
            pm = m.label.split("/")[2]
            empty[pm] += 1
            eshape[json.dumps(shape({k: v for k, v in tr.items() if k != "steps"}), sort_keys=True)[:600]] += 1
            eshape["steps:"+json.dumps(shape(st), sort_keys=True)[:400]] += 1
            eshape["nsteps:%d"%len(st)] += 1
            sc = r.get("scores") or {}
            cost = sc.get("cost") if isinstance(sc.get("cost"), dict) else {}
            etok[f"{pm}|out_tokens>0={bool(cost.get('output_tokens') or cost.get('completion_tokens'))}|in>0={bool(cost.get('input_tokens') or cost.get('prompt_tokens'))}|costkeys={sorted(cost)}"] += 1
            etok[f"{pm}|completed={tr.get('completed')}|error={bool(tr.get('error'))}"] += 1
print(json.dumps({"op_digest_match":[k for k in names if OP in names[k]], "in_scope": n,
  "acct": dict(acc), "names": {k: sorted(v) for k, v in names.items()}, "runs": {k: len(v) for k, v in runs.items()},
  "all_files_runs": {k: len(v) for k, v in allf.items()}, "empty": dict(empty), "etok": dict(etok), "eshape": dict(eshape)}, indent=1))
