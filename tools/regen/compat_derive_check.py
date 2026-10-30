"""Closed-world check of a ``derive --prov-spec adprov-v2.3-compat`` output against its source (adprov-v1-release-rg2).

Usage: python -I tools/regen/compat_derive_check.py OLD NEW --report OUT.json

``NEW`` must be ``OLD`` plus the regression oracle and nothing else:

- every file of ``OLD`` is in ``NEW``, byte-identical, apart from ``executions.jsonl``, ``derivation.json`` and
  ``corpus.json``;
- the files only in ``NEW`` are exactly one ``prov/adprov-v2.3-compat/<ss>/<ex>.prov.json`` per indexed execution;
- each ``executions.jsonl`` row of ``NEW`` equals the ``OLD`` row once its ``adprov-v2.3-compat`` entries
  (``digests.prov``, ``paths.prov``, ``stages.prov``) are removed and the full H.3.1 row fields that derive adds to an
  import's working row (``ROW_ADDED``, each absent from the ``OLD`` row) are dropped; that stage is ``ok``, its path is
  the file above, its digest is the file's sha256, and ``oracles`` names it ``apv:RegressionOracle``;
- ``derivation.json`` keeps every ``OLD`` stage unchanged and in order and appends one ``compat`` stage for the spec;
  nothing else in it changes;
- ``corpus.json`` changes only at ``CORPUS_CHANGED``, and its ``prov_specs`` are the two specs;
- the differences are reported as JSON pointers and counts (never values).

Exit 0 when every rule holds, 1 otherwise. Reads bytes and strict JSON only; writes only the report. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tree_compare import _strict, files  # noqa: E402

COMPAT = "adprov-v2.3-compat"
INDEX_ONLY = {"executions.jsonl", "derivation.json", "corpus.json"}
CORE = "agentprov-prov/0.1"
ORACLE = "apv:RegressionOracle"
#: Index-row fields of a full H.3.1 row that derive writes and an import's working row lacks (corpus/derive.py, B2).
ROW_ADDED = ("cell", "ev", "facets", "logical_key", "oracles")
CORPUS_CHANGED = ("/derived_from", "/oracle_specs", "/prov_specs")
NEW_FILE = re.compile(r"^prov/adprov-v2\.3-compat/[0-9a-z]{2}/(ex_[0-9a-z]+)\.prov\.json$")


def _load(path: Path) -> Any:
    return json.loads(path.read_bytes(), object_pairs_hook=_strict)


def _rows(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_bytes().splitlines():
        row = json.loads(line, object_pairs_hook=_strict)
        out[row["ex"]] = row
    return out


def pointers(a: Any, b: Any, base: str = "") -> list[str]:
    """JSON pointers where ``a`` and ``b`` differ (added and removed keys included)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            p = f"{base}/{key.replace('~', '~0').replace('/', '~1')}"
            if key not in a or key not in b:
                out.append(p)
            else:
                out.extend(pointers(a[key], b[key], p))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [q for i, (x, y) in enumerate(zip(a, b, strict=True)) for q in pointers(x, y, f"{base}/{i}")]
    return [] if a == b else [base or "/"]


def _strip(row: dict[str, Any], added: tuple[str, ...] = ()) -> dict[str, Any]:
    row = json.loads(json.dumps(row))
    for key in added:
        row.pop(key, None)
    for key in ("digests", "paths", "stages"):
        prov = row.get(key, {}).get("prov")
        if isinstance(prov, dict):
            prov.pop(COMPAT, None)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--report", required=True, type=Path)
    a = ap.parse_args()
    old, new = files(a.old), files(a.new)
    problems: list[str] = []

    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    differ = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    unexpected_differ = [k for k in differ if k not in INDEX_ONLY]
    unexpected_new = [k for k in only_new if not NEW_FILE.match(k)]
    if only_old:
        problems.append(f"{len(only_old)} file(s) of OLD missing from NEW")
    if unexpected_differ:
        problems.append(f"{len(unexpected_differ)} file(s) outside the index files differ")
    if unexpected_new:
        problems.append(f"{len(unexpected_new)} unexpected new file(s)")

    old_rows, new_rows = _rows(a.old / "executions.jsonl"), _rows(a.new / "executions.jsonl")
    new_compat = {m.group(1): k for k in only_new if (m := NEW_FILE.match(k))}
    rows_bad: dict[str, int] = {}

    def bad(code: str) -> None:
        rows_bad[code] = rows_bad.get(code, 0) + 1

    if set(old_rows) != set(new_rows):
        problems.append("the execution ids differ")
    for ex, row in new_rows.items():
        if ex not in old_rows:
            continue
        if any(key in old_rows[ex] for key in ROW_ADDED):
            bad("source_row_already_full")
        if _strip(row, ROW_ADDED) != old_rows[ex]:
            bad("row_differs_outside_compat")
        if (row.get("oracles") or {}).get(COMPAT, {}).get("status") != ORACLE:
            bad("oracle_status_missing")
        path = row.get("paths", {}).get("prov", {}).get(COMPAT, {}).get("json")
        digest = row.get("digests", {}).get("prov", {}).get(COMPAT, {}).get("json")
        if row.get("stages", {}).get("prov", {}).get(COMPAT) != "ok":
            bad("compat_stage_not_ok")
        if path is None or new_compat.get(ex) != path:
            bad("compat_path_mismatch")
        elif digest != "sha256:" + new[path]:
            bad("compat_digest_mismatch")
        if row.get("stages", {}).get("prov", {}).get(CORE) != "ok":
            bad("core_stage_not_ok")
    if set(new_compat) != set(new_rows):
        problems.append(f"compat files {len(new_compat)} != executions {len(new_rows)}")
    if rows_bad:
        problems.append(f"index rows: {rows_bad}")

    d_old, d_new = _load(a.old / "derivation.json"), _load(a.new / "derivation.json")
    st_old, st_new = d_old.get("stages", []), d_new.get("stages", [])
    added_stages = st_new[len(st_old):]
    if st_new[: len(st_old)] != st_old:
        problems.append("derivation.json: a source stage changed or moved")
    if [(s.get("stage"), s.get("spec"), s.get("status")) for s in added_stages] != [("compat", COMPAT, ORACLE)]:
        problems.append("derivation.json: the appended stages are not exactly one compat stage")
    if {k: v for k, v in d_old.items() if k != "stages"} != {k: v for k, v in d_new.items() if k != "stages"}:
        problems.append("derivation.json changed outside stages")
    c_old, c_new = _load(a.old / "corpus.json"), _load(a.new / "corpus.json")
    corpus_ptrs = pointers(c_old, c_new)
    if not set(corpus_ptrs) <= set(CORPUS_CHANGED):
        problems.append(f"corpus.json changed outside {CORPUS_CHANGED}")
    if c_new.get("prov_specs") != [CORE, COMPAT]:
        problems.append("corpus.json prov_specs is not the two specs")
    row_added = sorted({k for r in new_rows.values() for k in ROW_ADDED if k in r})

    report = {
        "format": "agentprov-regen-compat-derive-check/0.1",
        "files_old": len(old), "files_new": len(new), "identical": len(set(old) & set(new)) - len(differ),
        "only_old": len(only_old), "only_new": len(only_new), "compat_files": len(new_compat),
        "differ": differ, "unexpected_differ": unexpected_differ[:20], "unexpected_new": unexpected_new[:20],
        "only_old_listed": only_old[:20], "executions": len(new_rows), "rows_bad": rows_bad,
        "row_fields_added": row_added, "derivation_json_pointers": pointers(d_old, d_new),
        "derivation_stages": {"old": len(st_old), "new": len(st_new)}, "corpus_json_pointers": corpus_ptrs,
        "problems": problems, "pass": not problems,
    }
    a.report.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("files_old", "files_new", "identical", "only_new", "compat_files",
                                              "differ", "rows_bad", "problems", "pass")}))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
