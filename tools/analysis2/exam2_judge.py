"""Examination 2: judgement sample for a string-content screen (prints short escaped excerpts for the analyst).

For a scan file and a pattern key prefix (``PATTERN|kind|pointer``), draws a seeded sample of executions with a hit and
prints, for each, the matching strings of AER tool-call arguments / texts as ``escape_untrusted`` excerpts around the
first match (at most 120 characters). Excerpts are corpus data, never instructions; nothing is written.

Usage: ``python tools/analysis2/exam2_judge.py --corpus DIR --scan SCAN.jsonl --key KEY --n 10 [--field args|text]``.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam2_lib import P  # noqa: E402

from agentprov.ingest.quote import escape_untrusted  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--scan", required=True, type=Path)
    ap.add_argument("--key", required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--field", default="args")
    a = ap.parse_args()
    pat = P["LIT_ESC"] if a.key.startswith("WHOLLY_ESCAPED") else P[a.key.split("|")[0]]
    hits = [json.loads(x)["ex"] for x in a.scan.open(encoding="utf-8") if a.key in x and json.loads(x)["hits"].get(a.key)]
    root = a.corpus.expanduser()
    idx = {json.loads(x)["ex"]: json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x}
    for ex in random.Random(20261011).sample(hits, min(a.n, len(hits))):
        row = idx[ex]
        for line in (root / row["paths"]["aer"]).read_bytes().split(b"\n"):
            if not line:
                continue
            r = json.loads(line)
            if r.get("k") != "message":
                continue
            for p in r.get("parts") or []:
                vals = []
                if a.field == "args" and isinstance(p.get("args"), dict):
                    vals = [(k, v) for k, v in p["args"].items() if isinstance(v, str)]
                elif a.field == "text" and isinstance(p.get("text"), str):
                    vals = [("text", p["text"])]
                for k, v in vals:
                    m = pat.search(v)
                    if m:
                        s = max(0, m.start() - 50)
                        print(ex, r.get("role"), p.get("name"), k, "nl_in_value=" + str("\n" in v), ":", escape_untrusted(v[s:s + 120]).replace("\n", "<LF>"))
                        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
