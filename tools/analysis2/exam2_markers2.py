"""Examination 2, A05 attribution: for the markers where the scanner's literal readings and the SEM status disagree,
which normaliser reading decided (read-only).

Input: the scanner output of one corpus (``exam2_scan.py``), whose rows list ``a05_present_nofound`` (SEM ``present``,
no literal/whitespace/YAML-decoded reading of the scanner finds the payload) and ``a05_found_notpresent`` (a reading
finds it, SEM not ``present``). For each such marker this tool recomputes every reading of
``agentdojo.semantics.markers`` separately (the six fast forms, the YAML-decoded form, the Python-repr and JSON
fallbacks) and records which ones contain the normalised payload, plus whether the payload holds characters that an
unescape step rewrites (backslash, quote, newline, tab).

With ``--show N`` it prints, for N seeded examples per class, short escaped excerpts (``escape_untrusted``) for the
analyst's judgement; the report file holds counts and ids only.

Usage: ``python tools/analysis2/exam2_markers2.py --corpus DIR --scan SCAN.jsonl --out REPORT.json [--show 0]``.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from agentprov.adapters.agentdojo.semantics import markers as M
from agentprov.ingest.quote import escape_untrusted


def readings(text: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        "fast_unescape_undouble": M._norm_match(text),
        "fast_unescape": M._norm_match(text, undouble=False),
        "fast_unescape2_undouble": M._norm_match(text, levels=2),
        "fast_unescape2": M._norm_match(text, undouble=False, levels=2),
        "fast_raw": M.norm_payload(text),
        "fast_raw_undouble": M.norm_payload(text).replace("''", "'"),
    }
    for name, fn in (("yaml_decoded", M.yaml_decoded_form), ("pyrepr", M.pyrepr_form), ("json", M.json_form)):
        try:
            out[name] = fn(text)
        except M.Rejected:
            out[name] = None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--scan", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    root = a.corpus.expanduser()
    want: dict[str, dict[str, list[str]]] = {}
    for line in a.scan.open(encoding="utf-8"):
        d = json.loads(line)
        for k in ("a05_present_nofound", "a05_found_notpresent"):
            if d.get(k):
                want.setdefault(d["ex"], {})[k] = d[k]
    idx = {}
    for x in (root / "executions.jsonl").read_bytes().splitlines():
        if x:
            r = json.loads(x)
            if r["ex"] in want:
                idx[r["ex"]] = r
    stats: dict[str, Counter] = {"a05_present_nofound": Counter(), "a05_found_notpresent": Counter()}
    examples: dict[str, list] = {k: [] for k in stats}
    for ex in sorted(want):
        row = idx[ex]
        fixtures, texts = {}, {}
        for line in (root / row["paths"]["aer"]).read_bytes().split(b"\n"):
            if not line:
                continue
            r = json.loads(line)
            if r.get("k") == "fixture":
                fixtures[r["id"]] = r.get("content")
            elif r.get("k") == "message":
                for i, p in enumerate(r.get("parts") or []):
                    if isinstance(p, dict) and p.get("t") == "tool_result":
                        texts[f"{r['id']}#{i}"] = p.get("text")
        sem = []
        for p in (row["paths"].get("sem") or {}).values():
            sem += [json.loads(x) for x in (root / p).read_bytes().split(b"\n") if x and b"injection_marker" in x]
        for cls, targets in want[ex].items():
            tset = set(targets)
            for r in sem:
                if r.get("target") not in tset:
                    continue
                v = r.get("value") or {}
                st = v.get("status")
                if (cls == "a05_present_nofound") != (st == "present"):
                    continue
                payload, text = fixtures.get(v.get("fixture")), texts.get(r["target"])
                if not isinstance(payload, str) or not isinstance(text, str):
                    continue
                n = M.norm_payload(payload)
                rd = readings(text)
                hit = sorted(k for k, s in rd.items() if s is not None and n and n in s)
                esc = any(ch in payload for ch in "\\\"'\n\t")
                key = f"status={st}|norm={v.get('normaliser')}|escapable_payload={esc}|readings={'+'.join(hit) or 'none'}"
                stats[cls][key] += 1
                examples[cls].append([ex, r["target"], key])
    rnd = random.Random(20261011)
    rep = {"executions": len(want), "classes": {k: dict(v.most_common()) for k, v in stats.items()},
           "example_ids": {k: [e[:2] for e in rnd.sample(v, min(10, len(v)))] for k, v in examples.items()}}
    a.out.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if a.show:
        for cls, v in examples.items():
            for ex, target, key in rnd.sample(v, min(a.show, len(v))):
                row = idx[ex]
                print("==", cls, ex, target, key)
                for line in (root / row["paths"]["aer"]).read_bytes().split(b"\n"):
                    if not line:
                        continue
                    r = json.loads(line)
                    if r.get("k") == "message" and target.startswith(r["id"] + "#"):
                        t = r["parts"][int(target.split("#")[1])].get("text") or ""
                        print("  text:", escape_untrusted(t[:300]))
                    if r.get("k") == "fixture":
                        c = r.get("content")
                        print("  fixture", r["id"], ":", escape_untrusted(str(c)[:160]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
