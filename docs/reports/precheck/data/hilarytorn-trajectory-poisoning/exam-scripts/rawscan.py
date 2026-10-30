"""Raw scan of the 990 selected logs (git pin, lazy fetch off, strict agentprov.ingest parse) for the exam:
per-(arm, injection task) outcomes, timestamp windows (H3/H4), #168 exposure (H8), candidate presence (H9), C0/FFFD
locations (L1-03), tool-error counts. Prints counts, labels, code points and timestamps only (never message text).

usage: uv run python rawscan.py <bare> <commit> <out.json>
"""
from __future__ import annotations

import collections
import datetime as dt
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
limits = IngestLimits()
src = s.GitSource(Path(bare), commit)
entries = [e for e in src.entries() if LOG.match(e.label) and e.disposition != "absent_blob"]
rd = s.GitBlobReader(bare)

# candidate strings of the search outputs (not printed): group -> {task: [cand]}
cands: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
CF = re.compile(r"^data/results/(pair_search|tap_search)/([^/]+)/best_candidate\.json$")
for e in src.entries():
    m = CF.match(e.label)
    if not m or e.disposition == "absent_blob":
        continue
    v = s.parse_json(rd.read(e.sha1), limits).value
    if isinstance(v, dict) and isinstance(v.get("candidate"), str) and len(v["candidate"]) >= 40:
        grp = re.sub(r"injection_task_\d", "IT", m.group(2))
        grp = re.sub(r"_\d{10}$", "_<ts>", grp)
        tk = re.search(r"injection_task_\d", m.group(2))
        cands[grp].append((tk.group(0) if tk else "*", v["candidate"]))

def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("\\n", "\n")).strip()

cand_keys = {g: [(t, norm(c)[:60]) for t, c in lst] for g, lst in cands.items()}

WIN = {  # H3 windows (naive), from the manifests
    "<none>": ("2026-03-20T00:00:00", "2026-03-21T23:59:59"),
    "e2e/baseline": ("2026-04-14T06:14:07", "2026-04-14T08:09:20"),
    "e2e/persona_v3": ("2026-04-14T06:14:07", "2026-04-14T08:09:20"),
    "e2e/tap_run1": ("2026-04-14T06:14:07", "2026-04-14T08:09:20"),
    "e2e/seeded_pair_run1": ("2026-04-14T06:14:07", "2026-04-14T08:09:20"),
    "e2e/tap_run2": ("2026-04-14T15:56:09", "2026-04-14T16:46:39"),
    "e2e/seeded_pair_run2": ("2026-04-14T15:56:09", "2026-04-14T16:46:39"),
    "e2e/tap": ("2026-04-14T17:29:29", "2026-04-14T18:48:25"),
    "e2e/seeded_pair": ("2026-04-14T17:29:29", "2026-04-14T18:48:25"),
}
SLACK5 = {"invite_user_to_slack", "add_user_to_channel", "remove_user_from_slack"}

res = {
    "n_logs": 0, "sec_by_arm_it": collections.Counter(), "n_by_arm_it": collections.Counter(),
    "util_by_arm": collections.Counter(), "n_by_arm_kind": collections.Counter(),
    "ts": {}, "outside_window": collections.Counter(), "outside_labels": [], "baseline_before_run1": [],
    "tap_run1_prepass_it1_ts": None,
    "h8": collections.Counter(), "h9": collections.Counter(), "h9_cand_groups": collections.Counter(),
    "c0": collections.Counter(), "fffd": collections.Counter(), "tool_errors": collections.Counter(),
    "tool_error_fn": collections.Counter(), "info_occ_by_arm": collections.Counter(),
}
pre_sets: dict[str, set[str]] = collections.defaultdict(set)  # injection task -> preceding-60 contexts in base/baseline
pending: list[tuple[str, str, list[str]]] = []
ts_by_arm: dict[str, list[str]] = collections.defaultdict(list)


def tool_texts(msgs):
    for m in msgs:
        if m.get("role") != "tool":
            continue
        c = m.get("content")
        if isinstance(c, str):
            yield c
        elif isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and isinstance(b.get("content"), str):
                    yield b["content"]


for e in entries:
    m = LOG.match(e.label)
    arm = m.group(1) or "<none>"
    task_dir, attack_dir, file = m.group(4), m.group(5), m.group(6)
    v = s.parse_json(rd.read(e.sha1), limits).value
    res["n_logs"] += 1
    kind = "prepass" if attack_dir == "none" else "attacked"
    res["n_by_arm_kind"][f"{arm}|{kind}"] += 1
    msgs = v.get("messages") or []
    ts = v.get("evaluation_timestamp")
    ts_by_arm[arm].append(ts)
    lo, hi = WIN[arm]
    if not (lo <= ts.replace(" ", "T")[:19] <= hi):
        res["outside_window"][arm] += 1
        res["outside_labels"].append([e.label, ts])
    if arm == "e2e/baseline" and ts.replace(" ", "T")[:19] < "2026-04-14T06:36:04":
        res["baseline_before_run1"].append([e.label, ts])
    if arm == "e2e/tap_run1" and kind == "prepass" and task_dir == "injection_task_1":
        res["tap_run1_prepass_it1_ts"] = ts
    if kind == "attacked":
        it = file
        res["n_by_arm_it"][f"{arm}|{it}"] += 1
        res["sec_by_arm_it"][f"{arm}|{it}"] += 1 if v.get("security") is True else 0
        res["util_by_arm"][f"{arm}|attacked"] += 1 if v.get("utility") is True else 0
    else:
        res["util_by_arm"][f"{arm}|prepass"] += 1 if v.get("utility") is True else 0
    # tool errors, #168 exposure
    calls = {}
    for msg in msgs:
        for tc in msg.get("tool_calls") or []:
            calls[tc.get("id")] = tc.get("function")
    err_fns = []
    for msg in msgs:
        if msg.get("role") == "tool":
            fn = (msg.get("tool_call") or {}).get("function")
            if msg.get("error") is not None:
                res["tool_errors"]["errors"] += 1
                res["tool_error_fn"][fn] += 1
                err_fns.append(fn)
            for k in ("tool_call",):
                ch = ((msg.get(k) or {}).get("args") or {}).get("channel")
                if isinstance(ch, str):
                    for c in ch:
                        o = ord(c)
                        if o < 0x20 and c not in "\n\t":
                            res["c0"][f"{arm}|args.channel|U+{o:04X}"] += 1
                        if c == "\r":
                            res["c0"][f"{arm}|args.channel|CR"] += 1
                        if o == 0xFFFD:
                            res["fffd"][f"{arm}|args.channel|{fn}"] += 1
            er = msg.get("error")
            if isinstance(er, str):
                for c in set(er):
                    o = ord(c)
                    if (o < 0x20 and c not in "\n\t") or c == "\r":
                        res["c0"][f"{arm}|error|U+{o:04X}"] += 1
    if kind == "attacked" and file == "injection_task_5":
        res["h8"][f"{arm}|it5_attacked"] += 1
        if v.get("security") is True:
            res["h8"][f"{arm}|it5_sec_true"] += 1
            if any(fn in SLACK5 for fn in err_fns):
                res["h8"][f"{arm}|it5_sec_true_with_membership_error"] += 1
    # H9: contexts preceding the injection marker
    if kind == "attacked":
        ctxs = []
        for t in tool_texts(msgs):
            start = 0
            while (i := t.find("<INFORMATION>", start)) >= 0:
                ctxs.append(t[max(0, i - 60):i])
                start = i + 1
        res["info_occ_by_arm"][arm] += 1 if ctxs else 0
        if arm in ("<none>", "e2e/baseline"):
            pre_sets[file].update(ctxs)
        pending.append((arm, file, ctxs, "\n".join(tool_texts(msgs))))

for arm, it, ctxs, alltext in pending:
    if arm in ("<none>", "e2e/baseline"):
        res["h9"][f"{arm}|ctx_known"] += 1
        hit_grp = [g for g, lst in cand_keys.items() if any((t in (it, "*")) and k in norm(alltext) for t, k in lst)]
        res["h9"][f"{arm}|any_candidate_file_match"] += 1 if hit_grp else 0
        continue
    novel = [c for c in ctxs if c not in pre_sets[it]]
    res["h9"][f"{arm}|attacked"] += 1
    res["h9"][f"{arm}|with_marker"] += 1 if ctxs else 0
    res["h9"][f"{arm}|novel_preceding_context"] += 1 if novel else 0
    res["h9"][f"{arm}|novel_ends_blank_line"] += 1 if any(c.endswith("\n\n") or c.endswith("\\n\\n") for c in novel) else 0
    nt = norm(alltext)
    grps = sorted({g for g, lst in cand_keys.items() if any((t in (it, "*")) and k in nt for t, k in lst)})
    res["h9"][f"{arm}|any_candidate_file_match"] += 1 if grps else 0
    for g in grps:
        res["h9_cand_groups"][f"{arm}|{g}"] += 1

for arm, lst in ts_by_arm.items():
    lst = sorted(x.replace(" ", "T") for x in lst)
    res["ts"][arm] = {"n": len(lst), "min": lst[0], "max": lst[-1]}
res["candidate_groups_loaded"] = {g: len(v) for g, v in cands.items()}
with open(out, "w") as fh:
    json.dump(res, fh, indent=1, sort_keys=True, default=lambda o: dict(o))
print("ok", res["n_logs"])
