# ruff: noqa  (precheck examiner script for atia-benchmark, committed as run; read-only analysis)
"""Raw pass over the 123 sample members + 5 headers held in the L2 scratch raw store (strict agentprov.ingest loader).

Counts only; never prints a value of a secret-shaped match. Tests H-01..H-11, H-16..H-18 and the L1-06 secret hits.
Usage: python -I raw.py <scratch-corpus>/raw <out.json>
"""
from __future__ import annotations

import json, re, sys, hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from agentprov.ingest.loaders import strict_json_loads

R = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2]).expanduser()
SEC = {  # the l1_scan shapes (tools/precheck/l1_scan.py) and l2_common shapes
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "openai-api-key": re.compile(r"(?<![A-Za-z0-9])sk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"),
    "hf-token": re.compile(r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{34,}"),
    "slack-token": re.compile(r"xox[abpors]-[A-Za-z0-9-]{10,200}"),
}
ACCT = re.compile(r"(?i)(?:[A-Z]:\\\\?Users\\\\?[^\\\\/\s\"]+|/Users/[^/\s\"]+|/home/[^/\s\"]+)")
B64RUN = re.compile(r"[A-Za-z0-9+/_\-]{200,}={0,2}")
LO, HI = datetime(2025, 7, 17, 5, 47, tzinfo=timezone.utc), datetime(2025, 7, 17, 9, 0, tzinfo=timezone.utc)
c = Counter(); per_log = defaultdict(Counter); ids = defaultdict(set); err = []; sec = Counter(); acct = Counter()
types = Counter(); score = Counter(); hdr = {}; recount = defaultdict(Counter); mver = Counter(); safety = Counter()
member_sha = Counter(); tsforms = Counter(); hdr_keys = Counter(); ncalls = Counter(); nmodel = Counter()


def obj(sha):
    h = sha.split(":")[1]
    return strict_json_loads((R / "objects" / h[:2] / (h + ".json")).read_bytes())


def walk(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from walk(v, p + "/" + ("<key>" if p.endswith("/attachments") else k))
    elif isinstance(x, list):
        for v in x:
            yield from walk(v, p + "/*")
    elif isinstance(x, str):
        yield p, x


def secret_ctx(s, m):
    """Where a secret-shaped match sits: inside a base64 payload run, a data: URI, or free text."""
    for r in B64RUN.finditer(s):
        if r.start() <= m.start() and m.end() <= r.end():
            return "inside-base64-run(data-uri)" if s.startswith("data:") else "inside-base64-run"
    return "free-text"


for line in open(R / "origins.jsonl"):
    o = json.loads(line); org = o["origin"]; lab = org.get("label", ""); log = org.get("container", "")[:8]
    if lab == "header.json":
        h = obj(o["sha256"]); ev = h["eval"]
        res = {s["name"]: s["metrics"].get("accuracy", {}).get("value") for s in (h.get("results") or {}).get("scores", [])}
        hdr[log] = {"status": h["status"], "model": ev["model"], "inspect_ai": ev["packages"].get("inspect_ai"),
                    "samples": ev["dataset"]["samples"], "revision_commit": (ev.get("revision") or {}).get("commit", "")[:8],
                    "model_roles": "model_roles" in ev, "accuracy": res, "has_error": "error" in h,
                    "location_is_windows_path": bool(re.match(r"^[A-Za-z]:\\", ev["dataset"].get("location") or ""))}
        for p, s in walk(h):
            for n, rx in SEC.items():
                if rx.search(s): sec[f"header:{n}:{p}"] += 1
            if ACCT.search(s): acct[f"header:{p}"] += 1
        continue
    if not lab.startswith("samples/"):
        continue
    s = obj(o["sha256"]); member_sha[o["sha256"]] += 1
    sid = s["id"]; ids[log].add(sid); per_log[log]["samples"] += 1; c["samples"] += 1; c[f"epoch={s['epoch']}"] += 1
    at = s["metadata"].get("attack_type"); types[at] += 1
    first_user = next((m for m in s["messages"] if m["role"] == "user"), None)
    kinds = sorted({p.get("type") for p in (first_user["content"] if isinstance(first_user["content"], list) else [])} - {"text"}) if first_user else []
    c[f"media:{at}:{'+'.join(kinds) or 'text'}"] += 1
    if s.get("error"):
        err.append({"log": log, "id": sid, "attack_type": at}); per_log[log]["errored"] += 1
    v = (s.get("scores") or {}).get("harmful_tool_invoked", {}).get("value")
    score[v] += 1; recount[log][v] += 1; recount[f"type:{at}"][v] += 1
    calls = [tc for m in s["messages"] if m["role"] == "assistant" for tc in (m.get("tool_calls") or [])]
    ncalls[len(calls)] += 1
    harm = set(s["metadata"].get("harmful_tools") or [])
    pred = "C" if any(tc["function"] in harm for tc in calls) else "I"
    if v is not None: c["score_agree" if pred == v else "score_disagree"] += 1
    c["tool_call_id_eq_function"] += sum(tc.get("id") == tc["function"] for tc in calls); c["tool_calls"] += len(calls)
    evs = s.get("events", [])
    c["tool_events"] += sum(e.get("event") == "tool" for e in evs)
    c["tool_events_with_message_id"] += sum(e.get("event") == "tool" and bool(e.get("message_id")) for e in evs)
    models = [e for e in evs if e.get("event") == "model"]; nmodel[(len(calls), len(models))] += 1
    c["error_events"] += sum(e.get("event") == "error" for e in evs)
    for e in evs:
        for k in ("timestamp", "completed"):
            t = e.get(k)
            if t:
                f = "-04:00" if t.endswith("-04:00") else "Z" if t.endswith("Z") or t.endswith("+00:00") else "other"
                tsforms[f] += 1
                try:
                    d = datetime.fromisoformat(t); tsforms["in_range" if LO <= d <= HI else "out_of_range"] += 1
                except ValueError:
                    tsforms["parse_fail"] += 1
    for e in models:
        call = e.get("call") or {}; req = call.get("request") or {}; resp = call.get("response") or {}
        mver[resp.get("modelVersion")] += 1
        for st in req.get("safety_settings") or []: safety[f"{st.get('category')}={st.get('threshold')}"] += 1
        safety[f"n_settings={len(req.get('safety_settings') or [])}"] += 1
        for hk in ((req.get("generation_config") or {}).get("httpOptions") or {}).get("headers") or {}: hdr_keys[hk] += 1
        for p, x in walk(req.get("contents") or []):
            if "BASE_64_DATA_REMOVED" in x: c["request_b64_removed_marker"] += 1
        for cont in req.get("contents") or []:
            for part in cont.get("parts") or []:
                if "inlineData" in part: c[f"req_inlineData:{at}:{(part['inlineData'].get('mimeType') or '').split('/')[0]}"] += 1
                if "fileData" in part: c[f"req_fileData:{at}:{(part['fileData'].get('mimeType') or '').split('/')[0]}"] += 1
    big_parts = 0
    for p, x in walk(s):
        if len(x.encode()) > 1 << 20:
            c["strings_gt_1MiB_with_attachments"] += 1
        for n, rx in SEC.items():
            for m in rx.finditer(x):
                sec[f"sample:{n}:{p}:{secret_ctx(x, m)}"] += 1
        if ACCT.search(x): acct[f"sample:{p}"] += 1
    # attachment-resolved string sizes (raw-resolved, as the census counted)
    att = s.get("attachments") or {}
    for p, x in walk({k: v for k, v in s.items() if k != "attachments"}):
        if x.startswith("attachment://"):
            v2 = att.get(x[len("attachment://"):], "")
            if len(v2.encode()) > 1 << 20:
                where = "request" if "/call/request" in p else "message_part" if p.startswith("/messages") else "other"
                c[f"resolved_gt_1MiB:{where}:{p.split('/')[1]}"] += 1

fp = {k: sorted(v) for k, v in ids.items()}
sizes = {k: len(v) for k, v in fp.items()}
all_ids = set().union(*ids.values())
twentyfive = [k for k, n in sizes.items() if n == 25]
nineteen = [k for k, n in sizes.items() if n == 19]
out = {
    "samples": c["samples"], "per_log": {k: dict(v) for k, v in per_log.items()}, "header": hdr,
    "distinct_ids": len(all_ids), "ids_per_log": sizes,
    "h02": {"25_logs_same_ids": len(twentyfive) == 2 and ids[twentyfive[0]] == ids[twentyfive[1]],
            "19_logs_subset_of_25": all(ids[k] <= ids[twentyfive[0]] for k in nineteen) if twentyfive else None,
            "35_log_ids_superset_of_all": max(sizes.values()) == len(all_ids)},
    "errored": err, "attack_type": dict(types), "score": {str(k): n for k, n in score.items()},
    "recount": {k: {str(a): b for a, b in v.items()} for k, v in recount.items()},
    "counts": dict(c), "tool_calls_per_sample": dict(ncalls),
    "calls_vs_model_events": {f"calls={a},model_events={b}": n for (a, b), n in nmodel.items()},
    "model_version": {str(k): n for k, n in mver.items()}, "safety": dict(safety), "http_header_names": dict(hdr_keys),
    "timestamps": dict(tsforms), "secret_shaped": dict(sec), "account_paths": dict(acct),
    "byte_identical_members": sum(n > 1 for n in member_sha.values()),
}
OUT.write_text(json.dumps(out, indent=1, sort_keys=True))
print(json.dumps(out, sort_keys=True)[:6000])
