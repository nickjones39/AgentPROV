"""Sanity of ``register.jsonl`` against ``executions.jsonl`` and ``corpus.json`` (read-only; codes and counts only).

Checks: every line parses strictly; ``rid`` unique; every ``map.*`` row names an indexed ``ex`` and appears in that row's
``issues``; every index issue has a register row; ``select.*`` rows are ``not_imported`` and their counts equal
``corpus.json`` ``not_imported_by_code``; owners present exactly for ``select.owned_elsewhere``; severities per code.

Usage: ``python tools/analysis/phase10_register.py CORPUS_DIR [...]``.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from agentprov.ingest.loaders import strict_json_loads


def main() -> int:
    for arg in sys.argv[1:]:
        root = Path(arg).expanduser()
        corpus = json.loads((root / "corpus.json").read_text())
        index = {}
        for ln in (root / "executions.jsonl").read_bytes().splitlines():
            r = strict_json_loads(ln, record=True)
            index[r["ex"]] = set(r["issues"])
        rids: Counter[str] = Counter()
        codes: Counter[str] = Counter()
        sev: dict[str, Counter[str]] = defaultdict(Counter)
        disp: Counter[str] = Counter()
        problems: Counter[str] = Counter()
        reg_issues: dict[str, set[str]] = defaultdict(set)
        owners: Counter[str] = Counter()
        for ln in (root / "register.jsonl").read_bytes().splitlines():
            r = strict_json_loads(ln, record=True)
            rids[r["rid"]] += 1
            code = r["code"]
            codes[code] += 1
            sev[code][r.get("severity")] += 1
            disp[f"{code.split('.')[0]}:{r.get('disposition')}"] += 1
            ex = (r.get("subject") or {}).get("ex")
            if code.startswith("map."):
                if ex not in index:
                    problems["map_row_unknown_ex"] += 1
                elif code not in index[ex]:
                    problems["map_row_not_in_index_issues"] += 1
                reg_issues[ex].add(code)
            if code.startswith("select."):
                if r.get("disposition") != "not_imported":
                    problems["select_row_not_not_imported"] += 1
                if (code == "select.owned_elsewhere") != (r.get("owner") is not None):
                    problems["owner_presence_mismatch"] += 1
                if r.get("owner"):
                    owners[json.dumps(r["owner"], sort_keys=True)] += 1
        for ex, issues in index.items():
            for c in issues:
                if c.startswith("map.") and c not in reg_issues.get(ex, set()):
                    problems["index_issue_without_register_row"] += 1
        sel = {c: n for c, n in codes.items() if c.startswith("select.")}
        if sel != (corpus["counts"].get("not_imported_by_code") or {}):
            problems["select_counts_differ_from_corpus_json"] += 1
        print(json.dumps({"corpus": root.name, "rows": sum(codes.values()), "dup_rid": sum(n - 1 for n in rids.values() if n > 1),
                          "codes": dict(sorted(codes.items())), "severity": {c: dict(v) for c, v in sorted(sev.items())},
                          "dispositions": dict(disp), "owners": dict(owners), "problems": dict(problems)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
