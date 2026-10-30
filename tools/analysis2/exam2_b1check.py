"""Examination 2, A05 complement: census of injection markers that are not ``present`` although the payload, with
AutoDojo's YAML escape undone (the inverse of ``hooks/autodojo.yaml_escape``), occurs in the marked tool output
(verbatim or whitespace-collapsed). This is the first analysis' B1 miss class, measured exactly (whole payload, not a
40-character window) on every attacked execution of a corpus (read-only; counts and ids only).

Usage: ``python tools/analysis2/exam2_b1check.py --corpus DIR --out REPORT.json [--jobs 4]``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

_ROOT: Path | None = None
_UNESC = re.compile(r"\\(.)", re.DOTALL)
_MAP = {"\\": "\\", '"': '"', "n": "\n", "t": "\t"}


def unescape(p: str) -> str:
    return _UNESC.sub(lambda m: _MAP.get(m.group(1), m.group(0)), p)


def _init(root: str) -> None:
    global _ROOT
    _ROOT = Path(root)


def one(row: dict[str, Any]) -> dict[str, Any]:
    assert _ROOT is not None
    fixtures, texts, attack = {}, {}, None
    autodojo = set()
    for line in (_ROOT / row["paths"]["aer"]).read_bytes().split(b"\n"):
        if not line:
            continue
        r = json.loads(line)
        k = r.get("k")
        if k == "execution":
            attack = (r.get("task") or {}).get("attack_id")
        elif k == "fixture":
            fixtures[r["id"]] = r.get("content")
            if "autodojo" in json.dumps(r.get("ext") or {}):
                autodojo.add(r["id"])
        elif k == "message":
            for i, p in enumerate(r.get("parts") or []):
                if isinstance(p, dict) and p.get("t") == "tool_result":
                    texts[f"{r['id']}#{i}"] = p.get("text")
    c: Counter = Counter()
    if not fixtures:
        return {"c": {}, "ex": row["ex"], "miss": False}
    miss = False
    for p in (row["paths"].get("sem") or {}).values():
        for line in (_ROOT / p).read_bytes().split(b"\n"):
            if b'"injection_marker"' not in line:
                continue
            r = json.loads(line)
            v = r.get("value") or {}
            st = v.get("status")
            pay, txt = fixtures.get(v.get("fixture")), texts.get(r.get("target"))
            if st == "present" or not isinstance(pay, str) or not isinstance(txt, str):
                continue
            u = unescape(pay)
            if u == pay:
                continue
            wu, wt = " ".join(u.split()), " ".join(txt.split())
            if wu and wu in wt:
                miss = True
                c[f"{attack}|{st}|fixture_autodojo_linked={v.get('fixture') in autodojo}"] += 1
    return {"c": dict(c), "ex": row["ex"], "miss": miss, "attack": attack}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    root = a.corpus.expanduser()
    rows = sorted((json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x), key=lambda r: r["ex"])
    total: Counter = Counter()
    ex_by_attack: Counter = Counter()
    examples: list[str] = []
    with Pool(a.jobs, initializer=_init, initargs=(str(root),)) as pool:
        for res in pool.imap(one, rows, chunksize=32):
            total.update(res["c"])
            if res["miss"]:
                ex_by_attack[str(res.get("attack"))] += 1
                if len(examples) < 5:
                    examples.append(res["ex"])
    rep = {"corpus": root.name, "markers_missed_by_escape": dict(total), "executions_with_miss_by_attack": dict(ex_by_attack),
           "examples": examples}
    a.out.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
