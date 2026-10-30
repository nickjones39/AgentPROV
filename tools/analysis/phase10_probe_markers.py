"""Probe executions scored as attack successes in which SEM found no injection marker (read-only; no text printed).

For each selected execution (attacked, recorded ``security`` true, no ``injection_marker`` with status ``present``) it
reports: marker statuses by tool message; whether a whitespace-collapsed 40-character window of any payload occurs in a
tool result, an assistant message (text or tool-call args), or the task prompt; recomputed judgements; denials; the
attack and injection task. Only ids, counts and booleans are printed.

Usage: ``python tools/analysis/phase10_probe_markers.py --corpus DIR --features FEATURES.jsonl [--limit N]``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from message_roles import is_assistant  # noqa: E402  (assistant + DTap agent: one shared grouping)

from agentprov.aer.reader import load_aer
from agentprov.io.canonical import jcs_bytes
from agentprov.sem.reader import load_sem

_WS = re.compile(r"\s+")


def collapse(s: str) -> str:
    return _WS.sub(" ", s).strip()


_YAML_UNESCAPE = re.compile(r"\\([\\\"nt])")


def yaml_unescape(s: str) -> str:
    """Inverse of AutoDojo's ``_yaml_escape`` (backslash, double quote, newline, tab), as ported in hooks/autodojo.py."""
    return _YAML_UNESCAPE.sub(lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def windows(payload: str) -> list[str]:
    out: list[str] = []
    for form in dict.fromkeys((payload, yaml_unescape(payload))):
        c = collapse(form)
        if len(c) < 40:
            out.extend([c] if c else [])
            continue
        mid = len(c) // 2
        out.extend([c[:40], c[mid - 20: mid + 20], c[-40:]])
    return out


def probe(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    aer = load_aer(root / row["paths"]["aer"])
    ref, rel = next(iter(row["paths"]["sem"].items()))
    sem = load_sem(root / rel)
    payloads = [r["content"] for r in aer.records if r.get("k") == "fixture" and isinstance(r.get("content"), str)]
    wins = [w for p in payloads for w in windows(p)]
    where: Counter[str] = Counter()
    first_user = True
    for r in aer.records:
        if r.get("k") != "message":
            continue
        texts = [p.get("text") for p in r.get("parts") or () if isinstance(p.get("text"), str)]
        args = [jcs_bytes(p.get("args")).decode() for p in r.get("parts") or () if p.get("t") == "tool_call"]
        blob = collapse(" ".join(texts))
        hit = any(w and w in blob for w in wins)
        if r.get("role") == "tool" and hit:
            where["tool_result"] += 1
        elif is_assistant(r.get("role")):
            if hit:
                where["assistant_text"] += 1
            if any(any(w and w in collapse(a) for w in wins) for a in args):
                where["assistant_args"] += 1
        elif r.get("role") == "user" and first_user:
            first_user = False
            if hit:
                where["task_prompt"] += 1
    statuses = Counter(a["value"]["status"] for a in sem.records[1:] if a.get("type") == "injection_marker")
    rec = [(r.get("value"), r.get("origin")) for r in aer.records if r.get("k") == "judgement" and r.get("revises")]
    return {"ex": row["ex"], "markers": dict(statuses), "payload_window_found_in": dict(where), "recomputed": rec,
            "denials": sum(1 for r in aer.records if r.get("k") == "decision" and r.get("verdict") == "deny"),
            "n_tool_results": sum(1 for r in aer.records if r.get("k") == "message" and r.get("role") == "tool")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--features", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--all-attacked", action="store_true", help="probe every attacked execution (summary only)")
    args = ap.parse_args()
    root = args.corpus.expanduser()
    wanted = {}
    for line in args.features.read_text().splitlines():
        f = json.loads(line)
        sec = next((j["value"] for j in f.get("judgements") or () if j["name"] == "security" and not j["revises"]), None)
        if f.get("attack") and f.get("task_kind") != "dos" and f["unit"] == "agent_execution" and (args.all_attacked or (
                sec is True and f.get("sem_marker_present_msgs", 0) == 0)):
            wanted[f["ex"]] = (f.get("suite"), f.get("target"), f.get("attack"), f.get("model"), sec,
                               f.get("sem_marker_present_msgs", 0) > 0)
    rows = [json.loads(ln) for ln in (root / "executions.jsonl").read_text().splitlines() if ln]
    out = []
    agg: Counter[str] = Counter()
    for row in rows:
        if row["ex"] in wanted and (args.all_attacked or len(out) < args.limit):
            p = probe(root, row)
            p["cell"] = wanted[row["ex"]]
            out.append(p)
            loc = "tool_result" if "tool_result" in p["payload_window_found_in"] else "not_in_tool_result"
            cell = wanted[row["ex"]]
            agg[f"attack={cell[2]}|window={loc}|marker_present={cell[5]}|security={cell[4]}"] += 1
            agg["has_recomputed"] += bool(p["recomputed"])
            agg["recomputed_false"] += any(v is False for v, _o in p["recomputed"])
    if args.all_attacked:
        out = [r for r in out if "tool_result" in r["payload_window_found_in"] and not r["cell"][5]][:20]
    print(json.dumps({"selected": len(wanted), "probed": len(out), "summary": dict(sorted(agg.items())), "rows": out},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
