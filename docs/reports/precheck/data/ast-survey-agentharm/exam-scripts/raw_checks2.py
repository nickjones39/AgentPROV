# ruff: noqa  (precheck examiner script for ast-survey-agentharm, committed as run; read-only analysis)
"""Second raw pass: event order, limit samples, text-encoded calls, empty text forms, account-path segment classes.

Counts and sha8 digests only. Usage: python raw_checks2.py <corpus dir with raw/> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

CORPUS = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2])
ACC = re.compile(r"/(Users|home)/([A-Za-z0-9._-]+)/")
SHORT = {"ollama/gpt-oss:120b": "gptoss", "ollama/qwen3-coder:30b": "coder", "ollama/qwen3:14b": "qwen14"}


def res(x, att):
    if isinstance(x, str) and x.startswith("attachment://"):
        return att.get(x[len("attachment://"):], "")
    return x


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def main():
    out = {}
    seg_roles = defaultdict(Counter)
    hdr_seg = set()
    for line in (CORPUS / "raw/origins.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("origin", {}).get("kind") != "git":
            continue
        sha = r["sha256"].split(":", 1)[1]
        path = next((CORPUS / "raw/objects" / sha[:2]).glob(sha + "*"))
        with path.open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
            ms = list(iter_zip_members(z))
            hdr = strict_json_loads(z.read_member(next(m for m in ms if m.label == "header.json")))
            ev = hdr["eval"]
            loc = ev.get("dataset", {}).get("location") or ""
            mm = re.match(r"^/(?:Users|home)/([^/]+)/", loc)
            if mm:
                hdr_seg.add(mm.group(1))
            rdir = SHORT[ev["model"]] + ("_benign" if ev["task"].endswith("benign") else "_harmful")
            c = Counter()
            limit_msgs = Counter()
            for m in ms:
                if not (m.label or "").startswith("samples/"):
                    continue
                s = strict_json_loads(z.read_member(m))
                att = s.get("attachments") or {}
                events = s.get("events") or []
                tool_ev = [e for e in events if e.get("event") == "tool"]
                c["samples"] += 1
                if tool_ev:
                    c["samples_with_tool_events"] += 1
                tss = [e.get("timestamp") for e in events if e.get("timestamp")]
                if any(b < a for a, b in zip(tss, tss[1:])):
                    c["samples_ts_non_monotone"] += 1
                ws = [e.get("working_start") for e in events if isinstance(e.get("working_start"), (int, float))]
                if any(b < a for a, b in zip(ws, ws[1:])):
                    c["samples_working_start_non_monotone"] += 1
                # tool event listed before its own tool span begin
                pos_span = {e.get("id"): i for i, e in enumerate(events) if e.get("event") == "span_begin" and e.get("type") == "tool"}
                tidx = [i for i, e in enumerate(events) if e.get("event") == "tool"]
                before = 1 if tidx and pos_span and min(tidx) < min(pos_span.values()) else 0
                if before:
                    c["samples_tool_event_before_a_tool_span"] += 1
                if s.get("limit"):
                    n_msgs = len(s.get("messages") or [])
                    limit_msgs[str(n_msgs)] += 1
                    pending = 0
                    for msg in s.get("messages") or []:
                        pass
                    tc_ids = {tc.get("id") for msg in s.get("messages") or [] if msg.get("role") == "assistant"
                              for tc in msg.get("tool_calls") or []}
                    res_ids = {msg.get("tool_call_id") for msg in s.get("messages") or [] if msg.get("role") == "tool"}
                    if tc_ids - res_ids:
                        c["limit_samples_with_unanswered_tool_calls"] += 1
                        c["unanswered_tool_calls_at_limit"] += len(tc_ids - res_ids)
                        if n_msgs < 20:
                            c["limit_samples_lt20_with_unanswered"] += 1
                    if n_msgs < 20:
                        c["limit_samples_lt20"] += 1
                # text-encoded calls
                hit_msgs = 0
                for msg in s.get("messages") or []:
                    if msg.get("role") != "assistant":
                        continue
                    content = msg.get("content")
                    parts = [content] if isinstance(content, str) else [p.get("text") for p in content or [] if isinstance(p, dict) and p.get("type") == "text"]
                    text = "".join(res(p, att) or "" for p in parts)
                    if "<function=" in text:
                        hit_msgs += 1
                    if text == "":
                        c["assistant_text_exact_empty"] += 1
                    elif not text.strip():
                        c["assistant_text_whitespace_only"] += 1
                if hit_msgs:
                    c["samples_with_text_encoded_call"] += 1
                    c["messages_with_text_encoded_call"] += hit_msgs
                for e in events:
                    if e.get("event") == "model":
                        for ch in (e.get("output") or {}).get("choices") or []:
                            msg = ch.get("message") or {}
                            content = msg.get("content")
                            parts = [content] if isinstance(content, str) else [p.get("text") for p in content or [] if isinstance(p, dict) and p.get("type") == "text"]
                            if "<function=" in "".join(res(p, att) or "" for p in parts):
                                c["model_events_with_text_encoded_call"] += 1
                # account-like segments by role class
                for msg in s.get("messages") or []:
                    role = msg.get("role")
                    cls = {"system": "bench_system", "user": "bench_input", "tool": "env_tool_result", "assistant": "model"}.get(role, role)
                    for st in strings(res(msg.get("content"), att) if isinstance(msg.get("content"), str) else msg.get("content")):
                        for g in ACC.finditer(res(st, att) or ""):
                            seg_roles[g.group(2)][cls] += 1
                    for tc in msg.get("tool_calls") or []:
                        for st in strings(tc.get("arguments")):
                            for g in ACC.finditer(st):
                                seg_roles[g.group(2)]["model_tool_args"] += 1
            c.update({f"limit_msgs={k}": v for k, v in limit_msgs.items()})
            out[rdir] = dict(sorted(c.items()))
    segs = {}
    for seg, roles in seg_roles.items():
        segs[hashlib.sha256(seg.encode()).hexdigest()[:8]] = {"roles": dict(roles), "is_header_segment": seg in hdr_seg,
                                                              "in_bench_text": bool(roles.get("bench_input") or roles.get("bench_system") or roles.get("env_tool_result"))}
    out["account_like_segments"] = {"distinct": len(segs), "in_bench_or_env_text": sum(v["in_bench_text"] for v in segs.values()),
                                    "model_only": sum(not v["in_bench_text"] for v in segs.values()),
                                    "header_segment_present": sum(v["is_header_segment"] for v in segs.values()), "by_sha8": segs}
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
