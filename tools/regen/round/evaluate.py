"""Pass/fail of one corpus's round checks (D-354) from the JSON summaries the driver wrote. Exit 0 = pass.

Usage: python -I evaluate.py LOGDIR NAME EXECUTIONS
"""
import json
import sys
from pathlib import Path

log, name, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
fails, line = [], {}


def load(step):
    p = log / f"{name}-{step}.json"
    if not p.exists():
        fails.append(f"{step}: no summary")
        return None
    return json.loads(p.read_text())


imp = load("import")
if imp:
    c = imp["counters"]
    line["import"] = {k: c.get(k) for k in ("mapped", "sealed_clean", "sealed_with_issues", "degenerate", "failed")}
    if imp["exit_code"] != 0 or c.get("failed"):
        fails.append(f"import: exit {imp['exit_code']}, failed {c.get('failed')}")
dry = load("dryrun")
if dry:
    c = dry["counters"]
    line["dryrun_identical"] = c.get("identical")
    if dry["exit_code"] != 0 or c.get("identical") != n or any(c.get(k) for k in ("failed", "unexplained_change", "changed_explained", "unverified")):
        fails.append(f"dry-run: exit {dry['exit_code']}, {c}")
val = load("validate")
if val:
    c = val["counters"]
    line["validate"] = {k: c.get(k) for k in ("passed", "failed", "checks_skipped", "linkage_resolved")}
    if val["exit_code"] != 0 or c.get("failed") or c.get("passed") != n:
        fails.append(f"validate: exit {val['exit_code']}, {c}")
ver = load("verify")
if ver:
    other = {k: v for k, v in ver["issues_by_code"].items() if k != "checksums.absent"}
    line["verify"] = "ok" if not other and not ver["counters"].get("failed") else other
    if other or ver["counters"].get("failed"):
        fails.append(f"verify: {ver['issues_by_code']}")
cmp = load("compare")
if cmp:
    line["compare"] = {"ids_equal": not cmp["ids_only_old"] and not cmp["ids_only_new"],
                       "completeness": cmp["completeness"], "mismatches": len(cmp["mismatches"]),
                       "errors": len(cmp["errors"])}
    if cmp["ids_only_old"] or cmp["ids_only_new"] or cmp["mismatches"] or cmp["errors"]:
        fails.append(f"compare: ids {cmp['ids_only_old']}/{cmp['ids_only_new']}, mismatches {cmp['mismatches'][:5]}, "
                     f"errors {len(cmp['errors'])}")
out = {"corpus": name, "pass": not fails, "fails": fails, **line}
(log / f"{name}-verdict.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps(out, sort_keys=True))
sys.exit(0 if not fails else 1)
