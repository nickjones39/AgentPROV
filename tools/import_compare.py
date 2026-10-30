"""Determinism check between two working corpora of one source (numbers only; K.13, N.1.10(1)).

    uv run python tools/import_compare.py --a DIR_A.partial --b DIR_B.partial [--out CHECK.json]

For every execution of ``--b`` (a second import, typically a ``--select`` subset run with another ``--jobs``), the AER
file, the PROV-JSON file, the index row, the validation row and the register entries of that execution must be
byte-identical (JCS for the JSONL rows) in ``--a``. With ``--whole``, the two trees must hold exactly the same files with
the same bytes (``corpus.json`` and ``derivation.json`` included) except the lock and ``raw/tmp``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


def _rows(path: Path, key: str) -> dict[str, list[bytes]]:
    out: dict[str, list[bytes]] = {}
    if not path.exists():
        return out
    for line in path.read_bytes().splitlines():
        if line.strip():
            item = json.loads(line)
            subject = item.get(key) if key != "subject" else (item.get("subject") or {}).get("ex")
            if subject is not None:
                out.setdefault(str(subject), []).append(line)
    return out


def _files(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath, name)
            rel = path.relative_to(root).as_posix()
            if rel == ".agentprov.lock" or rel.startswith("raw/tmp/"):
                continue
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def compare(a: Path, b: Path, whole: bool) -> dict[str, Any]:
    index_a, index_b = _rows(a / "executions.jsonl", "ex"), _rows(b / "executions.jsonl", "ex")
    val_a, val_b = _rows(a / "validation" / "results.jsonl", "ex"), _rows(b / "validation" / "results.jsonl", "ex")
    reg_a, reg_b = _rows(a / "register.jsonl", "subject"), _rows(b / "register.jsonl", "subject")
    result: dict[str, Any] = {"executions_b": len(index_b), "index_rows_equal": 0, "aer_equal": 0, "prov_equal": 0,
                              "validation_rows_equal": 0, "register_entries_equal": 0, "missing_in_a": 0}
    for ex, (row_b,) in index_b.items():
        if ex not in index_a:
            result["missing_in_a"] += 1
            continue
        row = json.loads(row_b)
        result["index_rows_equal"] += index_a[ex] == [row_b]
        aer = row["paths"]["aer"]
        result["aer_equal"] += (a / aer).read_bytes() == (b / aer).read_bytes()
        for spec in (row["paths"].get("prov") or {}).values():
            result["prov_equal"] += (a / spec["json"]).read_bytes() == (b / spec["json"]).read_bytes()
        result["validation_rows_equal"] += val_a.get(ex) == val_b.get(ex)
        result["register_entries_equal"] += sorted(reg_a.get(ex, [])) == sorted(reg_b.get(ex, []))
    if whole:
        fa, fb = _files(a), _files(b)
        result["whole_tree"] = {"files_a": len(fa), "files_b": len(fb), "identical": fa == fb,
                                "differing": sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))[:20]}
    n = result["executions_b"] - result["missing_in_a"]
    result["all_equal"] = result["missing_in_a"] == 0 and all(
        result[k] == n for k in ("index_rows_equal", "aer_equal", "validation_rows_equal", "register_entries_equal")
    ) and (not whole or result["whole_tree"]["identical"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--whole", action="store_true", help="also require identical trees")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = compare(args.a, args.b, args.whole)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["all_equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
