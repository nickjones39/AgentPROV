"""Follow-up census of ceferisbarov-agentdojo (head) for the gaps exam.py flagged; counts and facets only.

H8 (literal {optim_str} in original-arm logs: where), H12 (cross-arm attacked fingerprint groups vs the literal),
H13 (escape residues in banking tool output), H15 (shape classes of secret-like matches, never values), H16 (logs
later than their adding commit), H9 (paper-grid subsets and the cells nearest the paper's counts).
Same raw-read guarantees as exam.py. Usage: uv run python -I extra.py <l1-units> <bare> <commit> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from agentprov.adapters.runner.importer import git_blob_sha1
from agentprov.ingest.loaders import strict_json_loads

UNITS, BARE, COMMIT, OUT = sys.argv[1], os.path.expanduser(sys.argv[2]), sys.argv[3], sys.argv[4]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {
    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]


def git(*a: str) -> bytes:
    return subprocess.run(["git", *H, "--git-dir", BARE, *a], capture_output=True, env=ENV, check=True).stdout


p = subprocess.Popen(["git", *H, "--git-dir", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=ENV)


def read(oid: str) -> bytes:
    p.stdin.write(oid.encode() + b"\n"); p.stdin.flush()
    h = p.stdout.readline().split()
    d = p.stdout.read(int(h[2])); p.stdout.read(1)
    assert git_blob_sha1(d) == oid
    return d


def wilson(k, n):
    if not n:
        return None
    z, q = 1.959963984540054, k / n
    d = 1 + z * z / n
    c = (q + z * z / (2 * n)) / d
    h = z * ((q * (1 - q) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(100 * q, 2), round(100 * max(0.0, c - h), 2), round(100 * min(1.0, c + h), 2)]


def text_of(c):
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    return "\n".join(str(b.get("content") or b.get("text") or "") for b in c if isinstance(b, dict))


tree = {}
for rec in git("ls-tree", "-r", "-z", COMMIT, "reruns/").split(b"\0"):
    if rec:
        meta, path = rec.split(b"\t", 1)
        tree[path.decode()] = meta.split()[2].decode()
added, cur = {}, None
for ln in git("log", "--no-renames", "--diff-filter=A", "--name-only", "--format=C %h %cI", COMMIT, "--",
              "reruns").decode().splitlines():
    if ln.startswith("C "):
        _, h, t = ln.split(" ", 2); cur = (h, t)
    elif ln.strip() and ln not in added:
        added[ln] = cur
SECRET = {"generic": re.compile(r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?"
                                r"([A-Za-z0-9_\-/+=.]{16,})"),
          "slack": re.compile(r"(?<![A-Za-z0-9])xox[abposr]-([A-Za-z0-9\-]{10,})")}
PLACEHOLDER = re.compile(r"(?i)x{4,}|your|example|placeholder|1234|abcd|dummy|redacted|\*{3,}")
rows = [json.loads(ln) for ln in open(UNITS, encoding="utf-8")]
lit_cells = Counter(); lit_by_label = {}
h13 = defaultdict(Counter); h15 = Counter(); h16 = Counter(); h16_excess = defaultdict(float)
for row in rows:
    lab, f = row["label"], row["facets"]
    _, armd, pdir, suite, task, att, fn = lab.split("/")
    raw = read(tree[lab])
    assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    x = strict_json_loads(raw)
    vals = [v for v in (x.get("injections") or {}).values() if isinstance(v, str)]
    lit = any("{optim_str}" in v for v in vals)
    lit_by_label[lab] = lit
    if armd == "original" and f["task_kind"] == "user":
        lit_cells[f"{pdir}|{suite}|literal={lit}|pkg={x.get('agentdojo_package_version')}|commit={added[lab][0]}"] += 1
    msgs = x.get("messages") or []
    if suite == "banking" and f["task_kind"] == "user":
        k = "fixed" if armd.endswith("_fixed") else "not_fixed"
        tt = "\n".join(text_of(m.get("content")) for m in msgs if m.get("role") == "tool")
        c = h13[k]
        c["logs"] += 1
        c["tool_output_has_backslash_quote"] += '\\"' in tt
        c["tool_output_has_double_backslash_special"] += any(s in tt for s in ("\\\\?", "\\\\<", "\\\\{", "\\\\}", "\\\\("))
        c["injection_has_bare_quote"] += any(re.search(r'(?<!\\)"', v) for v in vals)
        c["injection_has_backslash_special"] += any(re.search(r"\\[?<{}(]", v) for v in vals)
        heads = [v[:24] for v in vals if len(v) >= 24]
        c["injection_head24_in_tool_output"] += any(hd in tt for hd in heads)
    if "secret_like" in row["flags"]:
        for m in msgs:
            for nm, rx in SECRET.items():
                for mt in rx.finditer(text_of(m.get("content"))):
                    s = mt.group(1)
                    h15[f"{nm}|{pdir}|{suite}|arm_kind={'original' if armd == 'original' else 'optim'}"
                        f"|placeholder_shape={bool(PLACEHOLDER.search(s))}|len_bucket={min(len(s) // 16, 4) * 16}+"
                        f"|distinct_ratio_lt_0.3={len(set(s)) / len(s) < 0.3}"] += 1
    et = datetime.fromisoformat(x["evaluation_timestamp"])
    h, ct = added[lab]
    cdt = datetime.fromisoformat(ct).replace(tzinfo=None)
    if et > cdt + timedelta(days=1):
        h16[f"{armd}|{pdir}|{suite}|commit={h}"] += 1
        h16_excess[h] = max(h16_excess[h], round((et - cdt).total_seconds() / 86400, 2))
    elif et > cdt:
        h16["later_than_commit_within_1d"] += 1
p.stdin.close(); p.wait()

# H12: attacked cross-arm groups (L1 fingerprints) vs the literal
fp = defaultdict(list)
for row in rows:
    if row.get("fp") and row["facets"]["task_kind"] == "user":
        fp[row["fp"]].append(row)
h12 = Counter()
for g in fp.values():
    arms = {r["facets"]["arm"] for r in g}
    if len(g) > 1 and len(arms) > 1:
        kinds = "+".join(sorted(arms)) if arms <= {"original", "optim_str"} else "qwen_k/other"
        h12[f"{kinds}|pipeline={'/'.join(sorted({r['facets']['pipeline_dir'] for r in g}))}"] += 1
        if arms == {"original", "optim_str"}:
            h12["orig_members_with_literal"] += sum(lit_by_label[r["label"]] for r in g if r["facets"]["arm"] == "original")
            h12["orig_members"] += sum(1 for r in g if r["facets"]["arm"] == "original")
            h12["same_user_and_injection_task"] += len({(r["facets"]["task_dir"], r["facets"]["file"]) for r in g}) == 1

# H9: paper-grid subsets and nearest cells (raw outcomes = L1 rows, 0 differences in exam.py)
cell = defaultdict(lambda: defaultdict(Counter))
for row in rows:
    f, o = row["facets"], row["outcomes"]
    if f["task_kind"] != "user" or o["security"] is None:
        continue
    k = f"{f['arm']}|{f['pipeline_dir']}|{f['suite']}"
    c = cell[k][(f["task_dir"], f["file"])]
    c["n"] += 1; c["s"] += bool(o["security"])
sub = {}
for k, name, drop_ut, drop_it in (("optim_str|gpt-4o-2024-05-13|banking", "b_paper_grid_drop_ut15_it8", {"user_task_15"},
                                   {"injection_task_8"}),):
    t = Counter()
    for (ut, it), c in cell[k].items():
        if ut not in drop_ut and it not in drop_it:
            t.update(c)
    sub[name] = {"n": t["n"], "s": t["s"], "rate": wilson(t["s"], t["n"])}
for k in ("optim_str|gpt-4o-2024-05-13|slack", "original|gpt-4o-2024-05-13|slack"):
    by_ut = Counter()
    for (ut, it), c in cell[k].items():
        by_ut[ut] += c["s"]
    tot = sum(by_ut.values())
    sub[f"{k}|drop_one_ut_successes"] = sorted({tot - v for v in by_ut.values()})
near = []
for k, d in cell.items():
    n = sum(c["n"] for c in d.values()); s = sum(c["s"] for c in d.values())
    if k.endswith(("|banking", "|slack")) and n >= 100:
        near.append((k, n, s, wilson(s, n)))
near_b = sorted([z for z in near if z[0].endswith("|banking") and "gpt-4o-2024" in z[0]], key=lambda z: -z[3][0])[:5]
pairs = []
for m in ("gpt-4o-mini-2024-07-18", "meta-llama_Llama-3.1-70B-Instruct"):
    for a in ("original", "optim_str"):
        for s_ in ("slack", "banking"):
            k = f"{a}|{m}|{s_}"
            d = cell.get(k, {})
            pairs.append((k, sum(c["n"] for c in d.values()), sum(c["s"] for c in d.values())))
res = {"H8_original_arm_cells": dict(sorted(lit_cells.items())), "H12_cross_arm": dict(h12),
       "H13": {k: dict(v) for k, v in h13.items()}, "H15_shapes": dict(h15),
       "H16_later_than_commit": dict(h16), "H16_max_excess_days_by_commit": dict(h16_excess),
       "H9_subsets": sub, "H9_top_gpt4o_banking_cells": near_b, "H9c_cells": pairs}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=1, sort_keys=True)
print(json.dumps(res, sort_keys=True))
