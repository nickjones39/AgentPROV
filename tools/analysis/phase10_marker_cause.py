"""Why does the SEM injection marker miss a payload that is visible in a tool result? (read-only; booleans only)

For each given execution and each fixture, reports whether the whole whitespace-collapsed payload occurs in any tool
result's text in four forms: the payload as logged, the payload with AutoDojo's ``_yaml_escape`` undone, and each of those
against the tool text with the SEM YAML normaliser's fast forms (``markers.content_forms``). Also reports whether the
payload contains characters ``_yaml_escape`` rewrites (backslash, double quote, newline, tab). Prints booleans only.

Usage: ``python tools/analysis/phase10_marker_cause.py --corpus DIR EX [EX ...]`` or ``--from-probe PROBE.json``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from agentprov.adapters.agentdojo.semantics import markers
from agentprov.aer.reader import load_aer

_WS = re.compile(r"\s+")
_UNESC = re.compile(r"\\([\\\"nt])")


def collapse(s: str) -> str:
    return _WS.sub(" ", s).strip()


def unescape(s: str) -> str:
    return _UNESC.sub(lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--from-probe", type=Path)
    ap.add_argument("ex", nargs="*")
    args = ap.parse_args()
    root = args.corpus.expanduser()
    wanted = set(args.ex)
    if args.from_probe:
        wanted |= {r["ex"] for r in json.loads(args.from_probe.read_text())["rows"]}
    agg: Counter[str] = Counter()
    for line in (root / "executions.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["ex"] not in wanted:
            continue
        aer = load_aer(root / row["paths"]["aer"])
        tools = [p["text"] for r in aer.records if r.get("k") == "message" and r.get("role") == "tool"
                 for p in r.get("parts") or () if isinstance(p.get("text"), str)]
        forms = [f for t in tools for f in markers.content_forms(t)]
        raw_tools = [collapse(t) for t in tools]
        for fx in (r for r in aer.records if r.get("k") == "fixture"):
            pay = fx.get("content")
            if not isinstance(pay, str) or not pay.strip():
                continue
            res = {
                "has_escapable": bool(re.search(r"[\\\"\n\t]", unescape(pay))) and pay != unescape(pay),
                "logged_in_raw": any(collapse(pay) in t for t in raw_tools),
                "unescaped_in_raw": any(collapse(unescape(pay)) in t for t in raw_tools),
                "logged_in_forms": any(markers.norm_payload(pay) in f for f in forms),
                "unescaped_in_forms": any(markers.norm_payload(unescape(pay)) in f for f in forms),
            }
            agg["|".join(f"{k}={int(v)}" for k, v in res.items())] += 1
    print(json.dumps(dict(agg.most_common()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
