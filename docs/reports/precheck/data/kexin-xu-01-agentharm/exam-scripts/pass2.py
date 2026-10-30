# ruff: noqa  (precheck examiner script for kexin-xu-01-agentharm; read-only; counts and sha8 only)
"""(a) account segments and secret-shaped tokens in the benchmark source at the pin (src/inspect_evals/agentharm, git blobs,
lazy fetch off) as sha8 sets; (b) over the j2 scratch corpus: L2 mapping check per container vs the L1 rows, per-category
refusals, tool_execution errors by split/tool (sample level, mean score with/without), AER secret-shaped tokens vs (a),
AER named account segments vs (a).
Usage: uv run python -I pass2.py <repo-root> <bare> <commit> <scratch corpus> <l1-units.jsonl> <raw.json> <out.json>"""
import hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path.insert(0, str(ROOT / "tools/precheck"))
from l1_scan import GitSource, GitBlobReader, ACCOUNT_PATTERNS, GENERIC_ACCOUNTS, SECRET_PATTERNS  # noqa: E402
BARE, COMMIT, C, UNITS, RAW, OUT = sys.argv[2], sys.argv[3], Path(sys.argv[4]).expanduser(), sys.argv[5], sys.argv[6], Path(sys.argv[7])
sha8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
SEC = {k: SECRET_PATTERNS[k] for k in ("anthropic-api-key", "openai-api-key")}
def acc(t):
    return {sha8(m.group(1)) for rx in ACCOUNT_PATTERNS.values() for m in rx.finditer(t) if m.group(1).lower() not in GENERIC_ACCOUNTS}
def sec(t):
    return {f"{k}:{sha8(m.group(0))}" for k, rx in SEC.items() for m in rx.finditer(t)}
bench_acc, bench_sec = set(), set(); src = GitSource(Path(BARE), COMMIT, ["src/inspect_evals/agentharm"]); rd = GitBlobReader(BARE); nb = 0
for e in src.entries():
    t = rd.read(e.sha1).decode("utf-8", "replace"); nb += 1; bench_acc |= acc(t); bench_sec |= sec(t)
l1 = {}
for line in open(UNITS):
    r = json.loads(line); o = r["outcomes"]; sc = o.get("score.combined_scorer.score", {}); n = sum(sc.values())
    l1[r["sha256"][:12]] = {"n": n, "refused": int(o.get("score.combined_scorer.refusal", {}).get("1.0", 0)),
                            "mean": round(sum(float(v) * c for v, c in sc.items()) / n, 4) if n else None, "facets": r["facets"]}
m2c = {}
for line in (C / "raw/origins.jsonl").read_text().splitlines():
    o = json.loads(line)
    if o["origin"].get("kind") == "member": m2c[o["sha256"].split(":", 1)[1]] = o["origin"]["container"]
per = defaultdict(lambda: {"scored": 0, "refused": 0, "sum": 0.0}); cat = Counter(); te = Counter(); te_samples = Counter()
aff = defaultdict(lambda: [0, 0.0]); aer_acc = Counter(); aer_sec = Counter()
for line in (C / "executions.jsonl").read_text().splitlines():
    r = json.loads(line); mk = r["source_key"].split("#")[0].split(":", 1)[1]; key = m2c.get(mk, mk)[:12]
    txt = (C / r["paths"]["aer"]).read_text("utf-8"); recs = [json.loads(x) for x in txt.splitlines() if x]
    h = recs[0]; md = ((h.get("ext") or {}).get("inspect") or {}).get("sample_metadata") or {}
    split = "B" if h["task"]["suite"].endswith("benign") else "H"
    js = {x.get("name"): x.get("value") for x in recs if x.get("k") == "judgement"}
    p = per[key]
    if "combined_scorer.score" in js:
        p["scored"] += 1; p["sum"] += float(js["combined_scorer.score"]); ref = int(js.get("combined_scorer.refusal") == 1); p["refused"] += ref
        f = l1[key]["facets"]; cat[f"{f['judge_variant']}|{f['model']}|{split}|{md.get('category')}|n"] += 1; cat[f"{f['judge_variant']}|{f['model']}|{split}|{md.get('category')}|refused"] += ref
    bad = [x for x in recs if x.get("k") == "tool_execution" and x.get("status") in ("error", "invalid")]
    for x in bad: te[f"{split}:{x.get('name')}:{x.get('status')}"] += 1
    rf = any(x.get("name") == "read_file" and x.get("status") == "error" for x in bad)
    if rf: te_samples[f"{split}:read_file_error"] += 1
    if "combined_scorer.score" in js:
        a = aff[f"{split}:{'affected' if rf else 'unaffected'}"]; a[0] += 1; a[1] += float(js["combined_scorer.score"])
    for d in acc(txt): aer_acc[d] += 1
    for d in sec(txt): aer_sec[d] += 1
mapcheck = {"containers": len(per), "equal": 0, "diff": []}
for k, p in per.items():
    m = round(p["sum"] / p["scored"], 4) if p["scored"] else None
    if (p["scored"], p["refused"], m) == (l1[k]["n"], l1[k]["refused"], l1[k]["mean"]): mapcheck["equal"] += 1
    else: mapcheck["diff"].append({"c": k, "aer": [p["scored"], p["refused"], m], "l1": [l1[k]["n"], l1[k]["refused"], l1[k]["mean"]]})
raw = json.load(open(RAW)); loc = set(raw["acct"]["dataset_location_named"])
out = {"bench_blobs": nb, "bench_named_accounts": len(bench_acc), "bench_secret_tokens": len(bench_sec), "mapping_check": mapcheck,
       "category": dict(sorted(cat.items())), "tool_exec_bad": dict(te), "samples_with_read_file_error": dict(te_samples),
       "score_by_read_file_error": {k: {"n": v[0], "mean": round(v[1] / v[0], 4) if v[0] else None} for k, v in aff.items()},
       "aer_named_accounts": {d: {"executions": n, "in_benchmark_source": d in bench_acc, "is_dataset_location_account": d in loc} for d, n in aer_acc.items()},
       "aer_secret_tokens": {d: {"executions": n, "in_benchmark_source": d in bench_sec} for d, n in aer_sec.items()}}
OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in out.items() if k != "category"}, indent=0)[:4000])
