"""Examination 2, X06: validate every AER record against the published AER schema of the corpus's format (read-only).

Uses ``jsonschema.Draft202012Validator.iter_errors`` (an engine independent of the project's typed validator in
``agentprov.aer._structure``) and collects every error per record, keyed by keyword, schema-path tail and normalised
instance path. Records are parsed with the stdlib (duplicate keys rejected).

Usage: ``python tools/analysis2/exam2_schema.py --corpus DIR --out REPORT.json [--jobs 4] [--every N]``
(``--every N`` validates every N-th execution in id order, a systematic sample; default 1 = census).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

_V: Any = None
_ROOT: Path | None = None
_DIG = re.compile(r"/[0-9]+")


def _init(root: str, schema_path: str) -> None:
    global _V, _ROOT
    from jsonschema import Draft202012Validator

    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    _V = Draft202012Validator(schema)
    _ROOT = Path(root)


def _pairs(items: list) -> dict:
    d = dict(items)
    if len(d) != len(items):
        raise ValueError("duplicate key")
    return d


def one(row: dict[str, Any]) -> dict[str, Any]:
    assert _ROOT is not None and _V is not None
    c: Counter = Counter()
    first: dict[str, str] = {}
    for line in (_ROOT / row["paths"]["aer"]).read_bytes().split(b"\n"):
        if not line:
            continue
        rec = json.loads(line, object_pairs_hook=_pairs)
        c["records"] += 1
        kind = rec.get("k")
        errs = list(_V.iter_errors(rec))
        if errs:
            c["records_with_errors"] += 1
        for e in errs:
            path = _DIG.sub("/*", "/" + "/".join(str(x) for x in e.absolute_path))
            key = f"{kind}|{e.validator}|{path}"
            c[key] += 1
            first.setdefault(key, row["ex"])
    return {"ex": row["ex"], "c": dict(c), "first": first}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--every", type=int, default=1)
    a = ap.parse_args()
    root = Path(a.corpus).expanduser()
    # the published AER schema of the corpus's own format (aer-0.1 for agentprov-corpus/0.1, aer-0.2 for /0.2)
    fmt = str(json.loads((root / "corpus.json").read_bytes()).get("format") or "agentprov-corpus/0.1")
    version = {"agentprov-corpus/0.1": "0.1", "agentprov-corpus/0.2": "0.2"}.get(fmt)
    if version is None:
        sys.exit(f"exam2_schema: unknown corpus format {fmt!r}")
    schema = str(Path(__file__).resolve().parents[2] / f"src/agentprov/schemas/aer-{version}.schema.json")
    rows = sorted((json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x), key=lambda r: r["ex"])
    rows = rows[:: a.every]
    total: Counter = Counter()
    first: dict[str, str] = {}
    with Pool(a.jobs, initializer=_init, initargs=(str(root), schema)) as pool:
        for res in pool.imap(one, rows, chunksize=32):
            total.update(res["c"])
            for k, v in res["first"].items():
                first.setdefault(k, v)
    rep = {"corpus": root.name, "executions": len(rows), "every": a.every, "counts": dict(sorted(total.items())),
           "first_example": first}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(root.name, total.get("records"), total.get("records_with_errors", 0), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
