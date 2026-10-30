"""Run the mechanical pre-check steps for many parts inside ONE queued job (docs/reports/precheck/README.md §8, A2).

    uv run python tools/suite_queue.py --class import --cpu 2 --mem-gib 8 --label precheck-batch-<name> -- \\
        uv run python tools/precheck/run_batch.py --plan tools/precheck/plans/<name>.toml [--only C[:P]] [--force]

The import lane of the shared machine queue admits a job after hours, so one ticket per step and part is not workable.
This driver runs, per ``[[part]]`` of the plan and in plan order: ``l1`` (``l1_scan.py``), ``sample`` (``l2_sample.py
select``), ``import_j2`` and ``import_j1`` (``l2_import.py`` at ``--jobs 2`` and ``--jobs 1`` into two scratch corpora),
``check`` (``l2_check.py`` with the determinism compare); with ``l1_09 = true``, also ``l1_09`` (``l1_appledouble.py``,
OS-metadata members of archive inputs) after ``l1``; and ``l1_10`` (``l1_context.py``, L1-10: secret shapes and account
paths in non-JSON raw-store files) for every part with an ``l1`` input. A step whose output already exists is skipped (resumable);
``--force`` reruns. A failed step stops that part only. Each step's stdout/stderr goes to
``<precheck root>/_batch/<plan>/<corpus>.<part>.<step>.log`` (scratch, never committed); one status row per step goes to
``.../status.jsonl``.

Plan keys per part: ``corpus_id``, ``source``, ``part``, ``l1`` (extra ``l1_scan.py`` args: the input), ``sample`` (extra
``l2_sample.py select`` args, e.g. ``--exclude-facet``), ``import`` (extra ``l2_import.py`` args), ``units_from`` (another
part's L1 rows, e.g. the AutoDojo slice reads ROPE's), ``steps`` (subset, default all), ``l2_blocked`` (a reason: L1
only), ``force`` (steps re-run although their output exists, e.g. a recheck after a tool fix). Paths may start with ``~/``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO: Final = Path(__file__).resolve().parents[2]
STEPS: Final = ("l1", "l1_09", "l1_10", "sample", "import_j2", "import_j1", "check")
TIMEOUT: Final = {"l1": 4 * 3600, "l1_09": 3600, "l1_10": 3600, "sample": 600, "import_j2": 4 * 3600, "import_j1": 6 * 3600, "check": 4 * 3600}


def precheck_root() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from l2_common import precheck_root as root

    return root()


def expand(args: Sequence[str]) -> list[str]:
    return [str(Path(a).expanduser()) if a.startswith("~/") else a for a in args]


def commands(p: Mapping[str, Any], root: Path) -> dict[str, tuple[list[str], Path]]:
    """Each step's command line and the output whose existence marks it done."""
    c, s, part = str(p["corpus_id"]), str(p["source"]), str(p["part"])
    w = root / c
    data = REPO / "docs" / "reports" / "precheck" / "data" / c
    units_part = str(p.get("units_from", part))
    units = w / f"l1-units-{units_part}.jsonl"
    sample = data / f"l2-sample-{part}.json"
    py = ["uv", "run", "python"]
    tool = "tools/precheck/"
    return {
        "l1": ([*py, tool + "l1_scan.py", "--source", s, "--part", part, "--corpus-id", c, "--jobs", "2", "--emit-fp",
                *expand(p.get("l1", []))], data / f"l1-{part}.json"),
        "l1_09": ([*py, tool + "l1_appledouble.py", "--source", s, "--part", part, "--corpus-id", c,
                   *expand(p.get("l1", []))], data / f"l1-09-{part}.json"),
        "l1_10": ([*py, tool + "l1_context.py", "--source", s, "--part", part, "--corpus-id", c,
                   *expand(p.get("l1", []))], data / f"l1-10-{part}.json"),
        "sample": ([*py, tool + "l2_sample.py", "select", "--units", str(units), "--source", s, "--part", part,
                    "--corpus-id", c, "--out", str(sample), *expand(p.get("sample", []))], sample),
        "import_j2": ([*py, tool + "l2_import.py", "--sample", str(sample), "--corpus", str(w / f"l2-{part}-j2"),
                       "--source", s, "--part", part, "--jobs", "2", *expand(p.get("import", []))],
                      w / f"l2-{part}-j2.partial" / "executions.jsonl"),
        "import_j1": ([*py, tool + "l2_import.py", "--sample", str(sample), "--corpus", str(w / f"l2-{part}-j1"),
                       "--source", s, "--part", part, "--jobs", "1", *expand(p.get("import", []))],
                      w / f"l2-{part}-j1.partial" / "executions.jsonl"),
        "check": ([*py, tool + "l2_check.py", "--corpus", str(w / f"l2-{part}-j2.partial"), "--out",
                   str(data / f"l2-{part}.json"), "--sample", str(sample), "--l1-units", str(units), "--compare-with",
                   str(w / f"l2-{part}-j1.partial"), "--jobs", "2"], data / f"l2-{part}.json"),
    }  # fmt: skip


def run(plan_path: Path, *, only: Sequence[str] = (), force: bool = False, dry_run: bool = False) -> int:
    plan = tomllib.loads(plan_path.read_text(encoding="utf-8"))
    root = precheck_root()
    logs = root / "_batch" / plan_path.stem
    logs.mkdir(parents=True, exist_ok=True)
    status = logs / "status.jsonl"
    failures = 0
    for p in plan.get("part", []):
        key = f"{p['corpus_id']}:{p['part']}"
        if only and not any(key == o or str(p["corpus_id"]) == o for o in only):
            continue
        wanted = list(p.get("steps", STEPS))
        if not p.get("l1_09"):
            wanted = [s for s in wanted if s != "l1_09"]
        if p.get("l2_blocked"):
            wanted = [s for s in wanted if s in ("l1", "l1_09", "l1_10")]
        cmds = commands(p, root)
        for step in wanted:
            argv, done = cmds[step]
            row: dict[str, Any] = {"corpus_id": p["corpus_id"], "source": p["source"], "part": p["part"], "step": step}
            if done.exists() and not force and step not in p.get("force", ()):
                row["rc"], row["skipped"] = 0, True
                _append(status, row)
                continue
            if dry_run:
                print(" ".join(argv))
                continue
            log = logs / f"{p['corpus_id']}.{p['part']}.{step}.log"
            t0 = time.monotonic()
            row["start"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            try:
                with log.open("wb") as fh:
                    rc = subprocess.run(argv, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, timeout=TIMEOUT[step],
                                        check=False).returncode  # fmt: skip
            except subprocess.TimeoutExpired:
                rc = 124
            row["rc"], row["seconds"] = rc, round(time.monotonic() - t0, 1)
            _append(status, row)
            print(f"{key} {step} rc={rc} {row['seconds']}s", file=sys.stderr, flush=True)
            if rc != 0:
                failures += 1
                break
    return 1 if failures else 0


def _append(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument("--only", action="append", default=[], help="corpus_id or corpus_id:part (repeatable)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the commands only")
    a = ap.parse_args(argv)
    return run(a.plan, only=a.only, force=a.force, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
