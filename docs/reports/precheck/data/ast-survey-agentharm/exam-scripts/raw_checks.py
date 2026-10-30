# ruff: noqa  (precheck examiner script for ast-survey-agentharm, committed as run; read-only analysis)
"""Raw checks of the six AgentHarm .eval containers for the prereg hypotheses (read-only, through agentprov.ingest).

Output: counts, labels, metric values and truncated digests only. No source text, no account names (digest only).
Usage: python raw_checks.py <corpus dir with raw/> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

CORPUS = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2])
README = {  # survey agentharm/README.md @ 89c4db2c l. 342-349 (prereg section 3)
    "gptoss_harmful": {"avg_score": 0.131, "avg_full_score": 0.108, "avg_refusals": 0.915, "avg_score_non_refusals": 0.769},
    "gptoss_benign": {"avg_score": 0.640, "avg_full_score": 0.432, "avg_refusals": 0.528, "avg_score_non_refusals": 0.717},
    "coder_harmful": {"avg_score": 0.394, "avg_full_score": 0.205, "avg_refusals": 0.619, "avg_score_non_refusals": 0.727},
    "coder_benign": {"avg_score": 0.791, "avg_full_score": 0.540, "avg_refusals": 0.199, "avg_score_non_refusals": 0.808},
    "qwen14_harmful": {"avg_score": 0.495, "avg_full_score": 0.199, "avg_refusals": 0.290, "avg_score_non_refusals": 0.586},
    "qwen14_benign": {"avg_score": 0.607, "avg_full_score": 0.284, "avg_refusals": 0.063, "avg_score_non_refusals": 0.608},
}
README_MIN = {"gptoss_harmful": 108, "gptoss_benign": 165, "coder_harmful": 62, "coder_benign": 89,
              "qwen14_harmful": 247, "qwen14_benign": 289}
ACCT = re.compile(r"^/(?:Users|home)/([^/]+)/")
ANYACCT = re.compile(r"/(?:Users|home)/([A-Za-z0-9._-]+)/")
ERRPAT = re.compile(r"error|exception|traceback|failed to", re.I)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def text_of(content, att):
    """(text, has_reasoning) of a message content (str or parts), attachments resolved."""
    def res(x):
        if isinstance(x, str) and x.startswith("attachment://"):
            return att.get(x[len("attachment://"):], "")
        return x if isinstance(x, str) else ""
    if isinstance(content, str):
        return res(content), False
    text, reasoning = [], False
    for p in content or []:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            text.append(res(p.get("text")))
        elif p.get("type") == "reasoning":
            if res(p.get("reasoning")) or p.get("signature") or p.get("redacted"):
                reasoning = True
    return "".join(text), reasoning


def walk_strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from walk_strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from walk_strings(x)


def main():
    containers = {}
    for line in (CORPUS / "raw/origins.jsonl").read_text().splitlines():
        r = json.loads(line)
        o = r.get("origin", {})
        if o.get("kind") == "git":
            containers[r["sha256"].split(":", 1)[1]] = None
    members_rows = defaultdict(set)
    for line in (CORPUS / "raw/members.jsonl").read_text().splitlines():
        r = json.loads(line)
        members_rows[r["container"].split(":", 1)[1]].add(r["label"])
    out = {"logs": {}, "members": {}, "sample_ids": {}}
    account_segments = Counter()
    windows = {}
    for sha in sorted(containers):
        path = next((CORPUS / "raw/objects" / sha[:2]).glob(sha + "*"))
        with path.open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
            ms = list(iter_zip_members(z))
            labels = {m.label for m in ms if m.label}
            disp = Counter(str(m.disposition) for m in ms)
            hdr = strict_json_loads(z.read_member(next(m for m in ms if m.label == "header.json")))
            ev = hdr["eval"]
            rd = None
            for k in README:
                pass
            loc = ev.get("dataset", {}).get("location") or ""
            mm = ACCT.match(loc)
            seg = mm.group(1) if mm else None
            if seg:
                account_segments[seg] += 1
            model = ev["model"]
            split = "benign" if ev["task"].endswith("benign") else "harmful"
            short = {"ollama/gpt-oss:120b": "gptoss", "ollama/qwen3-coder:30b": "coder", "ollama/qwen3:14b": "qwen14"}[model]
            rdir = f"{short}_{split}"
            metrics = {}
            for sc in hdr.get("results", {}).get("scores", []):
                for mk, mv in (sc.get("metrics") or {}).items():
                    metrics[mk] = mv.get("value") if isinstance(mv, dict) else mv
            log = {"container": sha[:12], "members_zip": len(ms), "members_rows": len(members_rows[sha]),
                   "members_equal": labels == members_rows[sha], "zip_disposition": dict(disp),
                   "status": hdr.get("status"), "task": ev["task"], "model": model, "task_version": ev.get("task_version"),
                   "full_task_version": (ev.get("metadata") or {}).get("full_task_version"),
                   "revision_commit_len": len((ev.get("revision") or {}).get("commit") or ""),
                   "packages": ev.get("packages"), "dataset_samples": ev.get("dataset", {}).get("samples"),
                   "dataset_location_account_path": bool(seg),
                   "dataset_location_segment_sha8": hashlib.sha256(seg.encode()).hexdigest()[:8] if seg else None,
                   "epochs": (ev.get("config") or {}).get("epochs"), "message_limit": (ev.get("config") or {}).get("message_limit"),
                   "plan_config": hdr.get("plan", {}).get("config"),
                   "judges": {k: v for k, v in (ev.get("task_args") or {}).items() if k.endswith("_judge")},
                   "results_total": hdr.get("results", {}).get("total_samples"),
                   "results_completed": hdr.get("results", {}).get("completed_samples"),
                   "header_metrics": metrics}
            c = Counter()
            scores, refusals, int_scores = [], [], 0
            ids = []
            grading = Counter()
            setup_meeting_full = 0
            limit_msgs = []
            judge_cfg, agent_cfg = Counter(), Counter()
            total_time = 0.0
            smin, smax = None, None
            evmin, evmax = None, None
            tool_err = Counter()
            for m in ms:
                if not (m.label or "").startswith("samples/"):
                    continue
                s = strict_json_loads(z.read_member(m))
                c["samples"] += 1
                ids.append(s["id"])
                c[f"epoch={s.get('epoch')}"] += 1
                if s.get("error"):
                    c["sample_error"] += 1
                att = s.get("attachments") or {}
                v = s["scores"]["combined_scorer"]["value"]
                sc, rf = v.get("score"), v.get("refusal")
                if isinstance(sc, int) and not isinstance(sc, bool):
                    int_scores += 1
                c[f"score_type={type(sc).__name__}"] += 1
                c[f"refusal_type={type(rf).__name__}"] += 1
                scores.append(float(sc))
                refusals.append(float(rf))
                gf = (s.get("metadata") or {}).get("grading_function")
                grading[gf] += 1
                if gf == "grade_setup_meeting_location" and float(sc) == 1.0:
                    setup_meeting_full += 1
                if s.get("limit"):
                    lim = s["limit"]
                    c[f"limit={lim.get('type')}:{lim.get('limit')}"] += 1
                    limit_msgs.append(len(s.get("messages") or []))
                for rex in (s.get("metadata") or {}).get("refusal_explanations") or []:
                    c["refusal_explanations"] += 1
                    if ERRPAT.search(rex.get("explanation") or ""):
                        c["refusal_explanation_error_pattern"] += 1
                for msg in s.get("messages") or []:
                    if msg.get("role") != "assistant":
                        continue
                    c["assistant_msgs"] += 1
                    text, reasoning = text_of(msg.get("content"), att)
                    if not text.strip():
                        c["assistant_empty_text"] += 1
                        if reasoning:
                            c["assistant_empty_text_with_reasoning"] += 1
                    if reasoning:
                        c["assistant_with_reasoning"] += 1
                    if "<function=" in text:
                        c["assistant_text_encoded_call"] += 1
                spans = {}
                for e in s.get("events") or []:
                    if e.get("event") == "span_begin":
                        spans[e.get("id")] = (e.get("parent_id"), e.get("type"), e.get("name"))
                n_te = 0
                for e in s.get("events") or []:
                    t = e.get("timestamp")
                    if t:
                        tt = ts(t)
                        evmin = tt if evmin is None or tt < evmin else evmin
                        evmax = tt if evmax is None or tt > evmax else evmax
                    if e.get("event") == "model":
                        sid, judge = e.get("span_id"), False
                        for _ in range(50):
                            if sid not in spans:
                                break
                            parent, typ, _name = spans[sid]
                            if typ in ("scorer", "scorers"):
                                judge = True
                                break
                            sid = parent
                        who = "judge" if judge else "agent"
                        c[f"model_events_{who}"] += 1
                        cfg = e.get("config") or {}
                        tgt = judge_cfg if judge else agent_cfg
                        for key in ("temperature", "seed", "max_tokens"):
                            tgt[f"{key}={cfg.get(key)}"] += 1
                        for ch in (e.get("output") or {}).get("choices") or []:
                            if ch.get("stop_reason") == "max_tokens":
                                c[f"max_tokens_stop_{who}"] += 1
                    elif e.get("event") == "tool":
                        n_te += 1
                        fn = e.get("function")
                        res = e.get("result")
                        res = att.get(res[len("attachment://"):], "") if isinstance(res, str) and res.startswith("attachment://") else res
                        if fn in ("read_file", "edit_txt") and (e.get("error") or (isinstance(res, str) and re.search(r"not found|error", res, re.I))):
                            tool_err[f"{fn}:error_or_not_found"] += 1
                        if fn == "convert_pdf_to_text" and isinstance(res, str) and re.search(r"not found", res, re.I):
                            tool_err["convert_pdf_to_text:not_found"] += 1
                        if e.get("error"):
                            tool_err["any_tool_event_error"] += 1
                c["tool_events"] += n_te
                st, ct = ts(s["started_at"]), ts(s["completed_at"])
                smin = st if smin is None or st < smin else smin
                smax = ct if smax is None or ct > smax else smax
                total_time += float(s.get("total_time") or 0)
                for string in walk_strings({k: s.get(k) for k in ("messages", "attachments", "output", "events")}):
                    for mm2 in ANYACCT.finditer(string):
                        c["account_like_strings_in_content"] += 1
                        if seg and mm2.group(1) == seg:
                            c["dataset_location_segment_in_sample_content"] += 1
            n = len(scores)
            nonref = [x for x, r in zip(scores, refusals) if r == 0]
            float_only_full = None
            recount = {"n": n, "refusals": int(sum(refusals)), "avg_score": sum(scores) / n,
                       "avg_refusals": sum(refusals) / n, "avg_full_score_all": sum(1 for x in scores if x == 1.0) / n,
                       "avg_score_non_refusals": sum(nonref) / len(nonref) if nonref else None, "int_score_tokens": int_scores}
            log.update({"counts": dict(c), "recount": recount, "grading_functions": len(grading),
                        "setup_meeting_location_n": grading.get("grade_setup_meeting_location", 0),
                        "setup_meeting_location_full": setup_meeting_full,
                        "limit_samples_messages_min": min(limit_msgs) if limit_msgs else None,
                        "agent_cfg": dict(agent_cfg), "judge_cfg": dict(judge_cfg), "tool_err": dict(tool_err),
                        "sum_total_time_min": round(total_time / 60, 1), "readme_min": README_MIN[rdir],
                        "total_time_gap_pct": round(100 * (total_time / 60 - README_MIN[rdir]) / README_MIN[rdir], 1),
                        "window": [smin.isoformat(), smax.isoformat()], "event_ts": [evmin.isoformat(), evmax.isoformat()],
                        "ids_sha8": hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()[:8]})
            ref = README[rdir]
            log["readme_cmp_header"] = {k: [metrics.get(k), ref[k], abs((metrics.get(k) or 0) - ref[k]) <= 0.0005 + 1e-12]
                                        for k in ref}
            log["readme_cmp_recount"] = {k: [round(recount[k if k != "avg_full_score" else "avg_full_score_all"], 4), ref[k],
                                             abs(recount[k if k != "avg_full_score" else "avg_full_score_all"] - ref[k]) <= 0.0005 + 1e-12]
                                         for k in ref}
            out["logs"][rdir] = log
            windows[rdir] = (smin, smax)
    # overlap across models
    by_model = defaultdict(list)
    for rdir, (a, b) in windows.items():
        by_model[rdir.split("_")[0]].append((a, b))
    mw = {m: (min(a for a, _ in v), max(b for _, b in v)) for m, v in by_model.items()}
    overlaps = []
    ms_ = sorted(mw.items(), key=lambda kv: kv[1][0])
    for i in range(len(ms_)):
        for j in range(i + 1, len(ms_)):
            (m1, (a1, b1)), (m2, (a2, b2)) = ms_[i], ms_[j]
            if a2 < b1 and a1 < b2:
                overlaps.append([m1, m2])
    out["model_windows"] = {m: [a.isoformat(), b.isoformat()] for m, (a, b) in mw.items()}
    out["model_window_overlaps"] = overlaps
    log_windows = sorted(windows.items(), key=lambda kv: kv[1][0])
    out["log_window_overlaps"] = [[a[0], b[0]] for i, a in enumerate(log_windows) for b in log_windows[i + 1:]
                                  if b[1][0] < a[1][1] and a[1][0] < b[1][1]]
    out["distinct_dataset_location_segments"] = len(account_segments)
    ids_h = {v["ids_sha8"] for k, v in out["logs"].items() if k.endswith("harmful")}
    ids_b = {v["ids_sha8"] for k, v in out["logs"].items() if k.endswith("benign")}
    out["sample_id_sets"] = {"harmful_distinct_sets": len(ids_h), "benign_distinct_sets": len(ids_b)}
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    # search for the dataset-location account segment (in-process only; counts only)
    roots = [Path(x).expanduser() for x in sys.argv[3:]]
    found = {}
    for seg in account_segments:
        needles = {"slash": f"/{seg}/".encode(), "bare": seg.encode()}
        for root in roots:
            for sub in ("aer", "sem", "prov", "validation", "executions.jsonl", "register.jsonl", "corpus.json",
                        "derivation.json", "reports", "data", "precheck", "views"):
                base = root / sub
                if not base.exists():
                    continue
                files = [base] if base.is_file() else [f for f in base.rglob("*") if f.is_file()]
                for f in files:
                    b = f.read_bytes()
                    for nk, nd in needles.items():
                        k = b.count(nd)
                        if k:
                            key = f"{root.name}/{sub}:{nk}"
                            found[key] = found.get(key, 0) + k
    out["dataset_location_segment_hits"] = found
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
