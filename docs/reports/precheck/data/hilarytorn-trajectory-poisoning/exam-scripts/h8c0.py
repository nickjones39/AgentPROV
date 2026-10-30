"""H8 refinement and the C0 source: for slack injection_task_5 attacked logs with security true, does each of the three
membership functions have an executed (error-free) call? Plus: C0 code points inside the search candidates (counts only),
tool errors per arm, and the C0-bearing channel args per arm vs their tool errors. Counts and labels only.

usage: uv run python h8c0.py <bare> <commit> <out.json>
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402

bare, commit, out = sys.argv[1], sys.argv[2], sys.argv[3]
LOG = re.compile(r"^data/traces/(?:(e2e/[^/]+)/)?([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/]+)\.json$")
CF = re.compile(r"^data/results/(pair_search|tap_search)/([^/]+)/best_candidate\.json$")
limits = IngestLimits()
src = s.GitSource(Path(bare), commit)
ents = src.entries()
rd = s.GitBlobReader(bare)
SLACK5 = ("invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack")


def c0(t: str) -> int:
    return sum(1 for ch in t if (ord(ch) < 0x20 and ch not in "\n\t\r") or ch == "\x7f")


res = {"cand_c0": collections.Counter(), "h8": collections.Counter(), "h8_labels": [],
       "tool_err_by_arm": collections.Counter(), "c0_arg_calls_by_arm": collections.Counter(),
       "c0_arg_calls_error": collections.Counter(), "c0_logs_by_arm": collections.Counter(),
       "c0_in_tool_output_logs": collections.Counter()}
for e in ents:
    m = CF.match(e.label)
    if m and e.disposition != "absent_blob":
        v = s.parse_json(rd.read(e.sha1), limits).value
        if isinstance(v, dict) and isinstance(v.get("candidate"), str):
            g = re.sub(r"_\d{10}$", "_<ts>", re.sub(r"injection_task_\d", "IT", m.group(2)))
            res["cand_c0"][f"{g}|files"] += 1
            res["cand_c0"][f"{g}|files_with_c0"] += 1 if c0(v["candidate"]) else 0
for e in ents:
    m = LOG.match(e.label)
    if not m or e.disposition == "absent_blob":
        continue
    arm = m.group(1) or "<none>"
    attack_dir, file = m.group(5), m.group(6)
    v = s.parse_json(rd.read(e.sha1), limits).value
    msgs = v.get("messages") or []
    errs = {}
    for msg in msgs:
        if msg.get("role") == "tool":
            tc = msg.get("tool_call") or {}
            errs[tc.get("id")] = msg.get("error") is not None
            if msg.get("error") is not None:
                res["tool_err_by_arm"][arm] += 1
            cont = msg.get("content")
            texts = [cont] if isinstance(cont, str) else [b.get("content") for b in cont or [] if isinstance(b, dict)]
            if any(isinstance(t, str) and c0(t) for t in texts):
                res["c0_in_tool_output_logs"][arm] += 1
    has_c0 = False
    for msg in msgs:
        for tc in msg.get("tool_calls") or []:
            a = "".join(x for x in (tc.get("args") or {}).values() if isinstance(x, str))
            if c0(a):
                has_c0 = True
                res["c0_arg_calls_by_arm"][f"{arm}|{tc.get('function')}"] += 1
                res["c0_arg_calls_error"][f"{arm}|{errs.get(tc.get('id'))}"] += 1
    res["c0_logs_by_arm"][arm] += 1 if has_c0 else 0
    if attack_dir != "none" and file == "injection_task_5" and v.get("security") is True:
        res["h8"]["sec_true"] += 1
        ok = {f: False for f in SLACK5}
        att = {f: False for f in SLACK5}
        for msg in msgs:
            for tc in msg.get("tool_calls") or []:
                f = tc.get("function")
                if f in ok:
                    att[f] = True
                    if errs.get(tc.get("id")) is False:
                        ok[f] = True
        if all(att.values()) and not all(ok.values()):
            res["h8"]["sec_true_some_required_fn_only_errored"] += 1
            res["h8_labels"].append([e.label, sorted(f for f in SLACK5 if not ok[f])])
        if not all(att.values()):
            res["h8"]["sec_true_some_required_fn_never_called"] += 1
with open(out, "w") as fh:
    json.dump(res, fh, indent=1, sort_keys=True)
print(json.dumps(res, indent=0, sort_keys=True)[:6000])
