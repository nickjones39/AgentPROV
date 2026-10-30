"""Raw census of the 280 selected logs (counts and labels only, no text values). Reads via the L1 scanner's git source
(GitSource + GitBlobReader, lazy fetch disabled) and agentprov.ingest strict_json_loads.
Usage: uv run python census.py <repo> <out.json>"""
import sys, json, re
from collections import Counter, defaultdict
from pathlib import Path
REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
bare = Path.home() / ".agentprov/staging/10c/yockcheng/prompt-injection-harness.git"
src = s.GitSource(bare, "5f9137ff352c5e843a94cbe20a7f31aa6e2c8fc6")
rows = [json.loads(l) for l in open(Path.home() / ".agentprov/migration-work/precheck/yockcheng-prompt-injection-harness/l1-units-head.jsonl")]
labels = {r["label"]: r for r in rows}
ents = {e.label: e for e in src.entries() if e.label in labels}
assert len(ents) == 280
rd = s.GitBlobReader(str(bare))
NEEDLES = {"stock_sender_fb": "security-facebook-com@", "stock_sender_hiking": "hiking-travels-unlimited@",
           "patched_sender_mc": "michael.chen@", "patched_sender_sm": "sarah.mitchell@"}
out = {"per_label": {}, "agg": {}}
agg = defaultdict(Counter)
def texts(m):
    c = m.get("content")
    if isinstance(c, str): yield c
    elif isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and isinstance(b.get("content"), str): yield b["content"]
            elif isinstance(b, dict) and isinstance(b.get("text"), str): yield b["text"]
for lab in sorted(ents):
    r = labels[lab]; f = r["facets"]
    o = strict_json_loads(rd.read(ents[lab].sha1), IngestLimits())
    msgs = o.get("messages") or []
    roles = Counter(m.get("role") for m in msgs)
    calls = 0; ph_null = 0; ph_nonnull = 0; ph_absent = 0; tool_err = 0
    for m in msgs:
        for tc in (m.get("tool_calls") or []):
            calls += 1
            if "placeholder_args" not in tc: ph_absent += 1
            elif tc["placeholder_args"] is None: ph_null += 1
            else: ph_nonnull += 1
        if m.get("role") == "tool" and m.get("error") is not None: tool_err += 1
    hits = Counter()
    for m in msgs:
        for t in texts(m):
            for k, n in NEEDLES.items():
                if n in t: hits[(m.get("role"), k)] += 1
    # injections dict: sender needles also in injected payloads?
    ts = o.get("evaluation_timestamp")
    rec = {"tree": f["tree"], "model": f["pipeline_dir"], "attack": f["attack_dir"], "kind": f["task_kind"],
           "task": f["task_dir"], "file": f["file"], "variant": f["variant"],
           "pipeline_name_eq_dir": o.get("pipeline_name") == f["pipeline_dir"],
           "suite_name": o.get("suite_name"), "user_task_id": o.get("user_task_id"),
           "injection_task_id": o.get("injection_task_id"), "attack_type": o.get("attack_type"),
           "benchmark_version": o.get("benchmark_version"), "pkg": o.get("agentdojo_package_version"),
           "ts_month": ts[:7] if isinstance(ts, str) else None, "ts_date": ts[:10] if isinstance(ts, str) else None,
           "error_null": o.get("error") is None, "utility": o.get("utility"), "security": o.get("security"),
           "roles": dict(roles), "n_msgs": len(msgs), "calls": calls, "ph_null": ph_null, "ph_nonnull": ph_nonnull,
           "ph_absent": ph_absent, "tool_err": tool_err, "n_injections": len(o.get("injections") or {}),
           "needles": {f"{a}:{b}": n for (a, b), n in sorted(hits.items())},
           "sys_len": len(next(texts(msgs[0]), "")) if msgs and msgs[0].get("role") == "system" else None}
    out["per_label"][lab] = rec
    for k in ("benchmark_version", "pkg", "ts_month", "attack_type", "suite_name", "variant"):
        agg[k][str(rec[k])] += 1
    for k, v in roles.items(): agg["roles"][k] += v
    agg["calls"]["total"] += calls; agg["calls"]["ph_null"] += ph_null; agg["calls"]["ph_nonnull"] += ph_nonnull
    agg["calls"]["ph_absent"] += ph_absent; agg["calls"]["tool_err"] += tool_err
    agg["pipeline_name_eq_dir"][str(rec["pipeline_name_eq_dir"])] += 1
    agg["error_null"][str(rec["error_null"])] += 1
    agg["sys_len"][str(rec["sys_len"])] += 1
out["agg"] = {k: dict(v) for k, v in agg.items()}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, sort_keys=True))
print(json.dumps(out["agg"], indent=1, sort_keys=True))
