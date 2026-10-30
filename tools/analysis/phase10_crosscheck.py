"""End-to-end fidelity cross-check of AER against the raw TraceLogger log it was mapped from (read-only).

For each execution: parse the raw primary object with the strict ingest loader and the AER with the strict reader, then
check that the AER states what the log shows and nothing more (invariant 2):

* every source message is mapped exactly once (``src`` pointers ``/messages/<i>``) and no AER message lacks a source;
* message roles, text contents, tool-call names/args/ids equal the source (JCS comparison);
* one ``tool_execution`` or one deny ``decision`` per tool message; execution ``status`` agrees with the tool ``error``;
* the injections map equals the fixtures; outcome values equal the source keys; run duration and timestamp verbatim;
* no record other than the run scope carries a time.

Prints a JSON summary of mismatch codes with example ex ids; never prints source text.

Usage: ``python tools/analysis/phase10_crosscheck.py --corpus DIR [--sample N] [--jobs 4]`` (``--sample 0``: all).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from agentprov.aer.reader import load_aer
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes

_ROOT: Path | None = None


def _init(root: str) -> None:
    global _ROOT
    _ROOT = Path(root)


def _texts_of(content: Any) -> list[Any]:
    if content is None:
        return [None]
    if isinstance(content, str):
        return [content]
    out = []
    for b in content if isinstance(content, list) else ():
        if isinstance(b, dict) and b.get("type") in ("text", "thinking"):
            out.append(b.get("content"))
        elif isinstance(b, dict) and b.get("type") == "redacted_thinking":
            out.append(None)
        else:
            out.append(("other", jcs_bytes(b)))
    return out


def check(line: bytes) -> tuple[str, list[str]]:
    assert _ROOT is not None
    row = strict_json_loads(line, record=True)
    ex = row["ex"]
    bad: list[str] = []
    h = row["raw"][0]["sha256"].removeprefix("sha256:")
    cands = list((_ROOT / "raw" / "objects" / h[:2]).glob(h + ".*"))
    if not cands:
        return ex, ["raw.missing"]
    src = strict_json_loads(cands[0].read_bytes())
    aer = load_aer(_ROOT / row["paths"]["aer"], verify=True)
    msgs = src.get("messages") or []
    amsgs = [r for r in aer.records if r.get("k") == "message"]
    seen: Counter[int] = Counter()
    for m in amsgs:
        ptrs = [s.get("p") for s in m.get("src") or () if isinstance(s.get("p"), str) and s["p"].startswith("/messages/")]
        idx = [int(p.split("/")[2]) for p in ptrs if p.count("/") == 2]
        if len(idx) != 1:
            bad.append("message.src_pointer_count")
            continue
        i = idx[0]
        seen[i] += 1
        if i >= len(msgs):
            bad.append("message.src_out_of_range")
            continue
        sm = msgs[i]
        if m.get("id") != f"m{i}":
            bad.append("message.id_not_positional")
        if m.get("role") != sm.get("role") and isinstance(sm.get("role"), str):
            bad.append("message.role_differs")
        parts = m.get("parts") or []
        if sm.get("role") == "tool":
            p0 = parts[0] if parts else {}
            content = sm.get("content")
            got = p0.get("text") if "text" in p0 else ("value", jcs_bytes(p0.get("value")))
            if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict) and content[0].get("type") == "text":
                want = content[0].get("content")
            elif isinstance(content, list):
                want = ("value", jcs_bytes(content))
            else:
                want = content
            if got != want:
                bad.append("tool_result.content_differs")
            if p0.get("error") != sm.get("error"):
                bad.append("tool_result.error_differs")
        elif sm.get("role") in ("system", "user", "assistant"):
            content_parts = [p for p in parts if p.get("t") in ("text", "reasoning", "other")]
            got = []
            for p in content_parts:
                if p.get("t") == "other":
                    got.append(("other", jcs_bytes(p.get("value"))))
                else:
                    got.append(p.get("text"))
            want = _texts_of(sm.get("content"))
            if sm.get("content") == []:
                want = []
            if got != want:
                bad.append(f"{sm.get('role')}.content_differs")
            calls = [p for p in parts if p.get("t") == "tool_call"]
            scalls = sm.get("tool_calls") or []
            if len(calls) != len(scalls):
                bad.append("assistant.call_count_differs")
            for p, c in zip(calls, scalls, strict=False):
                if p.get("name") != c.get("function"):
                    bad.append("tool_call.name_differs")
                if jcs_bytes(p.get("args")) != jcs_bytes(c.get("args")):
                    bad.append("tool_call.args_differs")
                if ("id" in c) != ("provider_call_id" in p) or (("id" in c) and c.get("id") != p.get("provider_call_id")):
                    bad.append("tool_call.id_differs")
    for i in range(len(msgs)):
        if seen[i] != 1:
            bad.append("source_message.not_mapped_once")
    # tool messages -> exactly one execution or deny decision
    n_tool = sum(1 for m in msgs if isinstance(m, dict) and m.get("role") == "tool")
    tes = [r for r in aer.records if r.get("k") == "tool_execution"]
    denies = [r for r in aer.records if r.get("k") == "decision" and r.get("verdict") == "deny" and any(
        str(s.get("p", "")).startswith("/messages/") and msgs[int(str(s["p"]).split("/")[2])].get("role") == "tool"
        for s in r.get("src") or () if str(s.get("p", "")).count("/") >= 2)]
    if len(tes) + len(denies) != n_tool:
        bad.append("tool_messages_vs_executions_plus_denials")
    for te in tes:
        ptr = next((s["p"] for s in te.get("src") or () if str(s.get("p", "")).endswith("/error")), None)
        if ptr is None:
            bad.append("tool_execution.no_src")
            continue
        sm = msgs[int(ptr.split("/")[2])]
        err = sm.get("error")
        st = te.get("status")
        if err is None and st != "ok":
            bad.append("tool_execution.status_ok_expected")
        if err is not None and st == "ok":
            bad.append("tool_execution.status_not_ok_expected")
        if te.get("name") != (sm.get("tool_call") or {}).get("function"):
            bad.append("tool_execution.name_differs")
        if jcs_bytes(te.get("args")) != jcs_bytes((sm.get("tool_call") or {}).get("args")):
            bad.append("tool_execution.args_differs")
    # fixtures vs injections
    fx = [r for r in aer.records if r.get("k") == "fixture"]
    inj = src.get("injections") or {}
    if [(f.get("vector"), f.get("content")) for f in fx] != list(inj.items()):
        bad.append("fixtures_differ_from_injections")
    # judgements
    js = {r.get("name"): r for r in aer.records if r.get("k") == "judgement" and r.get("revises") is None}
    for name in ("utility", "security"):
        if name in src:
            if name not in js:
                bad.append(f"judgement.{name}_missing")
            elif js[name].get("value") != src[name]:
                bad.append(f"judgement.{name}_differs")
        elif name in js:
            bad.append(f"judgement.{name}_invented")
    run = aer.get("run") or {}
    t = run.get("t") or {}
    if "duration" in src and src["duration"] is not None and t.get("dur_s") != src["duration"]:
        bad.append("run.duration_differs")
    if "evaluation_timestamp" in src and (t.get("raw") or {}).get("start") != src["evaluation_timestamp"]:
        bad.append("run.timestamp_differs")
    for r in aer.records:
        if r.get("id") != "run" and isinstance(r.get("t"), dict) and r["t"]:
            bad.append(f"time_on_{r.get('k')}")
    task = aer.header.get("task") or {}
    if task.get("suite") != src.get("suite_name") or task.get("task_id") != src.get("user_task_id"):
        bad.append("task.fields_differ")
    if task.get("attack_id") != src.get("attack_type") or task.get("attack_target_id") != src.get("injection_task_id"):
        bad.append("task.attack_fields_differ")
    return ex, sorted(set(bad))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261011)
    args = ap.parse_args()
    root = args.corpus.expanduser()
    lines = [ln for ln in (root / "executions.jsonl").read_bytes().split(b"\n") if ln]
    if args.sample:
        lines = random.Random(args.seed).sample(lines, min(args.sample, len(lines)))
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    with Pool(args.jobs, initializer=_init, initargs=(str(root),)) as pool:
        for ex, bad in pool.imap_unordered(check, lines, chunksize=16):
            for b in bad:
                counts[b] += 1
                if len(examples[b]) < 3:
                    examples[b].append(ex)
    print(json.dumps({"corpus": root.name, "checked": len(lines), "mismatches": dict(counts),
                      "examples": {k: sorted(v) for k, v in examples.items()}}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
