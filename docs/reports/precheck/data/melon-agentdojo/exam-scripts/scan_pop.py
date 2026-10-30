"""Population scan of the 1,911 melon logs (raw, read through agentprov.ingest; counts only, no text printed).

Usage: uv run python -I scan_pop.py <bare repo> <commit> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

from agentprov.ingest.loaders import strict_json_loads

BARE, COMMIT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {
    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_TERMINAL_PROMPT": "0"}

STOP_EN = "The tool outputs contain potential prompt injection, stopping execution."
SENTINEL = "<Data omitted because a prompt injection was detected>"
SANITIZE = "[已移除潜在注入内容]"
CJK = re.compile(r"[㐀-鿿　-〿＀-￯]")
SECWARN = "SECURITY WARNING"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", BARE, *args], capture_output=True, env=ENV, check=True).stdout


def text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                for k in ("content", "text"):
                    v = b.get(k)
                    if isinstance(v, str):
                        out.append(v)
            elif isinstance(b, str):
                out.append(b)
    return "\n".join(out)


lines = git("ls-tree", "-r", COMMIT, "runs/").decode().splitlines()
entries = []
for ln in lines:
    meta, path = ln.split("\t", 1)
    _, typ, oid = meta.split()
    parts = path.split("/")
    if typ == "blob" and len(parts) == 6 and "-melon" in parts[1] and path.endswith(".json"):
        entries.append((path, oid))

proc = subprocess.Popen(["git", "-C", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, env=ENV)


def read(oid: str) -> bytes:
    proc.stdin.write(oid.encode() + b"\n"); proc.stdin.flush()
    hdr = proc.stdout.readline().split()
    assert hdr[0].decode() == oid and hdr[1] == b"blob", hdr
    n = int(hdr[2]); data = proc.stdout.read(n); proc.stdout.read(1)
    return data


rows = []
agg = defaultdict(Counter)
for path, oid in entries:
    d = strict_json_loads(read(oid))
    _, pdir, suite, task, attack, fname = path.split("/")
    model = "gpt-4o-mini-2024-07-18" if pdir.startswith("gpt-4o-mini") else "gpt-4o-2024-05-13"
    defence = pdir.split("-")[-1]
    msgs = d.get("messages") or []
    r = {"label": path, "pdir": pdir, "model": model, "defence": defence, "suite": suite, "task": task,
         "attack": attack, "inj": fname[:-5], "utility": d.get("utility"), "security": d.get("security"),
         "has_utility_key": "utility" in d, "has_duration": "duration" in d,
         "date": (d.get("evaluation_timestamp") or "")[:10], "n_msgs": len(msgs)}
    c = Counter()
    sys_digests = []
    for i, m in enumerate(msgs):
        role = m.get("role")
        t = text_of(m.get("content"))
        tc = m.get("tool_calls")
        if role == "system":
            c["system"] += 1
            sys_digests.append((i, hashlib.sha256(t.encode()).hexdigest()[:8], len(t), SECWARN in t, bool(CJK.search(t))))
        if role == "assistant":
            if t.strip() == STOP_EN:
                c["stop_en"] += 1
                c["stop_en_toolcalls_null" if not tc else "stop_en_with_toolcalls"] += 1
                if i == len(msgs) - 1:
                    c["stop_en_last"] += 1
            if CJK.search(t):
                c["asst_cjk"] += 1
                c["asst_cjk_toolcalls_null" if not tc else "asst_cjk_with_toolcalls"] += 1
                c["asst_cjk_end_" + ("ascii_dot" if t.rstrip().endswith(".") else "cjk_dot" if t.rstrip().endswith("。") else "other")] += 1
        if role == "tool":
            if SENTINEL in t:
                c["sentinel_tool_msgs"] += 1
            if SANITIZE in t:
                c["sanitize_tool_msgs"] += 1
            if CJK.search(t) and SANITIZE not in t:
                c["tool_cjk_other"] += 1
        if role == "user" and CJK.search(t):
            c["user_cjk"] += 1
        if SENTINEL in t and role != "tool":
            c["sentinel_non_tool"] += 1
    r["counts"] = dict(c)
    r["system"] = sys_digests
    r["last_role"] = msgs[-1].get("role") if msgs else None
    rows.append(r)

proc.stdin.close(); proc.wait()

# detection_stats.json (supporting artefact; numbers only)
ds_oid = git("rev-parse", f"{COMMIT}:runs/detection_stats.json").decode().strip()
ds = strict_json_loads(read_ds := subprocess.run(["git", "-C", BARE, "cat-file", "blob", ds_oid], capture_output=True,
                                                 env=ENV, check=True).stdout)


def numeric_shape(x, pre=""):
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out.update(numeric_shape(v, f"{pre}/{k}"))
    elif isinstance(x, list):
        out[pre] = f"list[{len(x)}]"
    elif isinstance(x, (int, float, bool)) or x is None:
        out[pre] = x
    else:
        out[pre] = f"str[{len(x)}]"
    return out


json.dump({"n": len(rows), "rows": rows, "detection_stats": numeric_shape(ds)}, open(OUT, "w"), ensure_ascii=True)
print("rows", len(rows))
