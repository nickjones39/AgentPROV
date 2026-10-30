# ruff: noqa  (precheck examiner script for kexin-xu-01-agentharm; read-only; counts, labels, metric values, sha8 digests only)
"""Raw checks of the 68 pinned .eval logs for prereg H-01..H-04, H-07..H-15, H-17 (through agentprov.ingest; blobs from the
fetch cache via tools/precheck/l1_scan GitSource/GitBlobReader, lazy fetch off). No source text and no account names leave
this script (account segments are recorded as sha256[:8] only; local-path model ids as 'local:<sha8>').
Usage: uv run python -I raw_checks.py <repo-root> <bare> <commit> <out.json>"""
import hashlib, io, json, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path.insert(0, str(ROOT / "tools/precheck"))
from l1_scan import GitSource, GitBlobReader, ACCOUNT_PATTERNS, GENERIC_ACCOUNTS  # noqa: E402
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
BARE, COMMIT, OUT = sys.argv[2], sys.argv[3], Path(sys.argv[4])
PIN_TIME = datetime(2026, 9, 26, 22, 39, 28, tzinfo=timezone.utc)
sha8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
FN_TS = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})")
def strings(v, ptr=""):
    if isinstance(v, str): yield ptr, v
    elif isinstance(v, dict):
        for k, x in v.items(): yield from strings(x, ptr + "/" + ("<att>" if ptr.endswith("attachments") else ("*" if str(k).isdigit() else str(k))))
    elif isinstance(v, list):
        for x in v: yield from strings(x, ptr + "/*")
def accounts(s):
    for kind, rx in ACCOUNT_PATTERNS.items():
        for m in rx.finditer(s):
            a = m.group(1)
            yield kind, ("generic" if a.lower() in GENERIC_ACCOUNTS else "named"), a
def model_class(m):
    if not m: return None
    return "local:" + sha8(m) if (m.startswith("/") or "\\" in m or any(True for _ in accounts(m))) else m
src = GitSource(Path(BARE), COMMIT, ["logs"]); rd = GitBlobReader(BARE)
out = {"logs": [], "acct": {}}
loc_named = Counter(); content_named = defaultdict(lambda: {"logs": set(), "ptr": Counter(), "kind": None})
for e in src.entries():
    if not e.label.endswith(".eval"): continue
    data = rd.read(e.sha1)
    jv = e.label.split("/")[1] if e.label.count("/") > 1 else "base"
    fnm = FN_TS.search(e.label); fstart = datetime.fromisoformat(f"{fnm.group(1)}T{fnm.group(2)}:{fnm.group(3)}:{fnm.group(4)}+00:00")
    L = {"label_tail": e.label.rsplit("_", 1)[-1][:8], "judge_variant": jv, "file_start": fstart.isoformat()}
    with open_zip(io.BytesIO(data), IngestLimits(), release=False) as z:
        ms = list(iter_zip_members(z)); by = {m.label: m for m in ms if m.label}
        hdr = strict_json_loads(z.read_member(by["header.json"])) if "header.json" in by else None
        if hdr is None and "_journal/start.json" in by:
            st = strict_json_loads(z.read_member(by["_journal/start.json"])); ev = st.get("eval", {}); L["header"] = False
        else:
            ev = (hdr or {}).get("eval", {}); L["header"] = hdr is not None
        L["status"] = (hdr or {}).get("status")
        L["model"] = model_class(ev.get("model")); L["task"] = ev.get("task"); L["task_version"] = ev.get("task_version")
        L["packages"] = ev.get("packages"); L["dataset_samples"] = (ev.get("dataset") or {}).get("samples")
        rv = ev.get("revision") or {}
        L["revision"] = {"origin": ("kexin" if "Kexin" in (rv.get("origin") or "") else "upstream" if "inspect_evals" in (rv.get("origin") or "") else rv.get("origin")),
                         "commit7": (rv.get("commit") or "")[:7] or None}
        L["judges"] = {k: v for k, v in (ev.get("task_args") or {}).items() if "judge" in k}
        L["scorers"] = sorted({s.get("name") for s in ((ev.get("scorers") or []) + [x for x in ((hdr or {}).get("results") or {}).get("scores", [])]) if isinstance(s, dict) and s.get("name")})
        loc = (ev.get("dataset") or {}).get("location") or ""
        L["dataset_location_accounts"] = sorted({f"{k}:{c}:{sha8(a)}" for k, c, a in accounts(loc)})
        for k, c, a in accounts(loc):
            if c == "named": loc_named[sha8(a)] += 1
        L["header_error"] = None
        if hdr and hdr.get("error"):
            msg = (hdr["error"].get("message") or "")
            L["header_error"] = {"has_401": "401" in msg, "auth": bool(re.search(r"(?i)authenticat|api.key|expired", msg))}
        S = Counter(); ids = defaultdict(set); cat = Counter(); cat_ref = Counter(); errs = Counter(); cf = []
        tool_err = Counter(); ts_bad = Counter(); logger = 0; rj_err = 0; ts_min = ts_max = None
        for m in ms:
            if not (m.label or "").startswith("samples/"): continue
            s = strict_json_loads(z.read_member(m)); S["samples"] += 1
            md = s.get("metadata") or {}; c = md.get("category"); cat[c] += 1
            sid = str(s.get("id")); ids[L["task"]].add(sid.split("-")[0])
            sc = ((s.get("scores") or {}).get("combined_scorer") or {}).get("value") or {}
            if isinstance(sc, dict) and "score" in sc:
                S["scored"] += 1
                if sc.get("refusal") == 1: S["refused"] += 1; cat_ref[c] += 1
            if s.get("error"):
                S["error"] += 1; msg = s["error"].get("message") or ""
                errs["401" if "401" in msg else ("auth" if re.search(r"(?i)authenticat", msg) else "other")] += 1
            for x in md.get("refusal_explanations") or []:
                if "Error in RefusalJudgeLLM" in json.dumps(x): rj_err += 1
            hit_cf = False
            for evn in s.get("events") or []:
                t = evn.get("timestamp")
                if t:
                    tt = datetime.fromisoformat(t)
                    if tt.tzinfo is None: ts_bad["naive"] += 1
                    else:
                        ts_min = tt if ts_min is None or tt < ts_min else ts_min; ts_max = tt if ts_max is None or tt > ts_max else ts_max
                        if tt < fstart.replace(microsecond=0) and (fstart - tt).total_seconds() > 1: ts_bad["before_file_start"] += 1
                        if tt > PIN_TIME: ts_bad["after_pin"] += 1
                if evn.get("event") == "logger": logger += 1
                if evn.get("event") == "model":
                    o = evn.get("output") or {}
                    if o.get("stop_reason") == "content_filter" or any((ch or {}).get("stop_reason") == "content_filter" for ch in o.get("choices") or []):
                        hit_cf = True
                if evn.get("event") == "tool" and evn.get("error"):
                    split = "B" if (L["task"] or "").endswith("benign") else "H"
                    tool_err[f"{split}:{evn.get('function')}:{(evn['error'] or {}).get('type')}"] += 1
            if hit_cf: cf.append({"id": sid, "refusal": sc.get("refusal") if isinstance(sc, dict) else None})
            for p, v in strings(s):
                for k, cl, a in accounts(v):
                    if cl == "named":
                        d = content_named[sha8(a)]; d["logs"].add(L["label_tail"]); d["ptr"][p.split("/")[1] if "/" in p else p] += 1; d["kind"] = k
        L.update({"samples": S["samples"], "scored": S["scored"], "refused": S["refused"], "sample_errors": S["error"],
                  "error_classes": dict(errs), "category": dict(cat), "category_refused": dict(cat_ref),
                  "behaviour_ids": sorted({i for v in ids.values() for i in v}, key=lambda x: (len(x), x)),
                  "content_filter": cf, "tool_errors": dict(tool_err), "ts_violations": dict(ts_bad), "logger_events": logger,
                  "refusal_judge_errors": rj_err, "ts_min": ts_min.isoformat() if ts_min else None, "ts_max": ts_max.isoformat() if ts_max else None})
    out["logs"].append(L)
out["acct"] = {"dataset_location_named": dict(loc_named),
               "content_named": {k: {"logs": len(v["logs"]), "kind": v["kind"], "top": dict(v["ptr"].most_common(3)),
                                     "equals_location_account": k in loc_named} for k, v in content_named.items()}}
OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print("logs", len(out["logs"]))
