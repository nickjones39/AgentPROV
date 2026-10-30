"""Examination 2, P06 follow-up: are the references of inference bundles resolved inside their application view?

The census (``exam2_scan.py``) resolved each relation argument in container ∪ core ∪ top level and found many arguments
of inference bundles declared only in *another* inference bundle. EF E.1.6 item 1 defines the application view of an
inference bundle B as core ∪ B ∪ every inference bundle whose method set is a proper subset of B's. This pass resolves
every node argument of every inference bundle in that view, independently of ``agentprov.validate`` (method sets are read
from the bundle IRI ``xd:bundle.inf.<m1>--<m2>....<dk>`` and cross-checked with the bundle entity's ``apv:method``).

Usage: ``python tools/analysis2/exam2_p06view.py --corpus DIR --out REPORT.json [--jobs 4]``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam2_lib import ELEMENTS, NODE_ARGS  # noqa: E402

_ROOT: Path | None = None


def _init(root: str) -> None:
    global _ROOT
    _ROOT = Path(root)


def methods_from_name(name: str) -> frozenset[str] | None:
    if not name.startswith("xd:bundle.inf."):
        return None
    body = name[len("xd:bundle.inf."):].rsplit(".", 1)[0]
    return frozenset(body.split("--"))


def one(row: dict[str, Any]) -> dict[str, int]:
    assert _ROOT is not None
    c: Counter = Counter()
    if not row["paths"].get("prov"):  # a failed prov stage (e.g. worker.limit.rss): counted, not a crash
        c["executions_without_prov"] += 1
        return dict(c)
    doc = json.loads((_ROOT / next(iter(row["paths"]["prov"].values()))["json"]).read_bytes())
    bundles = doc.get("bundle") or {}
    decl: dict[str, set[str]] = {}
    for b, bd in bundles.items():
        decl[b] = {k for sec in ELEMENTS for k in (bd.get(sec) or {})}
    top = {k for sec in ELEMENTS for k in (doc.get(sec) or {}) if sec in doc}
    core = next((b for b in bundles if b.startswith("xd:bundle.core.")), None)
    meth = {b: methods_from_name(b) for b in bundles}
    for b, m in meth.items():  # cross-check with the bundle entity's apv:method
        if m is None:
            continue
        ent = (doc.get("entity") or {}).get(b) or {}
        am = ent.get("apv:method")
        am = frozenset(am if isinstance(am, list) else [am]) if am else None
        if am is not None:
            names = frozenset(x.replace("@", "-v").replace(".", "-") for x in am)
            c["method_set_entity_equals_name" if names == m else "method_set_entity_differs_from_name"] += 1
    for b, bd in bundles.items():
        m = meth[b]
        if m is None:
            continue
        view = set(decl[b]) | top | (decl[core] if core else set())
        for b2, m2 in meth.items():
            if m2 is not None and m2 < m:
                view |= decl[b2]
        for sec, items in bd.items():
            if sec in ELEMENTS or sec == "prefix" or not isinstance(items, dict):
                continue
            for attrs in items.values():
                for arg, v in attrs.items():
                    if arg not in NODE_ARGS:
                        continue
                    for x in (v if isinstance(v, list) else [v]):
                        if not isinstance(x, str):
                            continue
                        c["args"] += 1
                        if x not in view:
                            c[f"unresolved_in_view|{sec}|{arg}"] += 1
    return dict(c)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    root = a.corpus.expanduser()
    rows = sorted((json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x), key=lambda r: r["ex"])
    total: Counter = Counter()
    with Pool(a.jobs, initializer=_init, initargs=(str(root),)) as pool:
        for res in pool.imap(one, rows, chunksize=32):
            total.update(res)
    rep = {"corpus": root.name, "executions": len(rows), "counts": dict(sorted(total.items()))}
    a.out.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
