"""Check a FULL DTap import against the step-1 census (docs/architecture D.16.14 test 12; D.16.6 figures; step 4).

    uv run python -I tools/dtap/census_reproduce.py CORPUS_DIR

Compares the counts of ``tools/dtap/dtap_report.py`` (and the register) with every ``observed`` count of the profile's
``[family.dtap] quirk`` table and the census figures named in D.16.2 and D.16.10. Prints each figure with the expected
and the observed value and exits 1 when any differs. On a sample corpus every figure differs by design: run it on the
step-4 full import only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Census figures (sources/dtap.md) as (name, expected, how the report counts it).
FIGURES = (
    ("synthetic_registered", 20, lambda r: r["register_details"].get("dtap.synthetic", 0)),
    ("lfs_pointers_registered", 2, lambda r: r["register_details"].get("dtap.lfs_pointer", 0)),
    ("harness_failures", 47, lambda r: r["issues"].get("dtap.harness_failure", 0)),
    ("empty_trajectories", 17, lambda r: r["issues"].get("dtap.empty_trajectory", 0)),
    ("join_tier_a", 62419, lambda r: r["join"].get("A", 0)),
    ("join_tier_b", 2899, lambda r: r["join"].get("B", 0)),
    ("join_tier_c", 1693, lambda r: r["join"].get("C", 0)),
    ("join_missing", 786, lambda r: r["join"].get("missing", 0)),
    ("join_unparseable", 9, lambda r: r["join"].get("unparseable", 0)),
    ("rerun_directories", 1291, lambda r: r["rerun_groups"]["groups"]),
    ("judge_errors", 14, lambda r: r["issues"].get("dtap.judge_error", 0)),
)


def main(argv: list[str] | None = None) -> int:
    from dtap_report import _partial, report

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    data = report(args.corpus)
    partial = _partial(args.corpus)
    details: dict[str, int] = {}
    for line in (partial / "register.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["code"] == "select.not_execution_artefact" and row["detail"].startswith("dtap.") and " " not in row["detail"]:
            details[row["detail"]] = details.get(row["detail"], 0) + 1
    data["register_details"] = details
    bad = 0
    for name, expected, count in FIGURES:
        got = count(data)
        bad += got != expected
        print(f"{name:28s} expected {expected:>7} observed {got:>7} {'ok' if got == expected else 'DIFFERS'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
