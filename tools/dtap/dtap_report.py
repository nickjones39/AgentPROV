"""Per-source report of a DTap working corpus (docs/architecture D.16.8, D.16.15; D.16.17 open question 4).

    uv run python -I tools/dtap/dtap_report.py CORPUS_DIR [--json OUT]

Reads the corpus's ``executions.jsonl``, the AER and SEM files and ``register.jsonl`` (never a raw text field into the
output) and reports counts only:

* executions by harness/model, split, unit and index status; register rows by code;
* seal issue counts; join tiers; judge links (content, colocation, unresolved, judge-only);
* exposure classes by channel (``dtap.exposure``) and the runs without a verified configuration
  (``no_verified_configuration``); injection markers by status;
* re-run groups: resolved and unresolved, and for each unresolved group a **group-level outcome** computed from the
  directory's judge file (read from the raw store by its digest; the only place such an outcome is computed: stats
  stays source-neutral, D.16.17 question 4).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _partial(root: Path) -> Path:
    return root if (root / "executions.jsonl").exists() else root.with_name(root.name + ".partial")


def _raw(partial: Path, sha256: str) -> bytes | None:
    for path in (partial / "raw" / "objects" / sha256[:2]).glob(f"{sha256}.*"):
        return path.read_bytes()
    return None


def report(root: Path) -> dict[str, Any]:
    from agentprov.ingest.loaders import strict_json_loads

    partial = _partial(root)
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text(encoding="utf-8").splitlines()]
    out: dict[str, Any] = {"executions": len(rows)}
    by: dict[str, Counter[str]] = defaultdict(Counter)
    issues: Counter[str] = Counter()
    exposure: Counter[str] = Counter()
    markers: Counter[str] = Counter()
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        lines = (partial / row["paths"]["aer"]).read_bytes().splitlines()
        head = json.loads(lines[0])
        seal = json.loads(lines[-1])
        dtap = head.get("ext", {}).get("dtap", {})
        facets = dtap.get("path_facets", {})
        split = "benign" if facets.get("split") == "benign" else str(facets.get("threat"))
        pair = f"{facets.get('framework')}|{facets.get('model')}"
        by["pair"][pair] += 1
        by["split"][split] += 1
        by["unit"][head["unit"]] += 1
        by["status"][row.get("status", "?")] += 1
        by["split_status"][f"{split}|{row.get('status', '?')}"] += 1
        for issue in seal.get("issues", []):
            issues[issue["code"]] += 1
        join = dtap.get("join")
        by["join"][str(join.get("tier") or join.get("status")) if isinstance(join, dict) else "none"] += 1
        link = dtap.get("judge_link")
        by["judge_link"]["judge_only" if head["unit"] == "outcome_only" and link is None and facets.get("file") == "judge_result.json"
                         else (link or {}).get("method", "none")] += 1
        if isinstance(link, dict) and link.get("group_size", 1) > 1:
            key = link["judge_sha256"]
            group = groups.setdefault(key, {"size": link["group_size"], "resolved": link["resolved"], "split": split})
            group["resolved"] = group["resolved"] or link["resolved"]
        sem = row.get("paths", {}).get("sem", {})
        payloads = 0
        for _ref, rel in (sem.items() if isinstance(sem, dict) else []):
            for line in (partial / rel).read_text(encoding="utf-8").splitlines()[1:-1]:
                ann = json.loads(line)
                if ann["type"] == "dtap.exposure":
                    payloads += 1
                    exposure[f"{ann['value']['channel']}|{ann['value']['class']}"] += 1
                elif ann["type"] == "injection_marker" or ann["type"].endswith("_marker"):
                    markers[f"{ann['type']}|{ann['value']['status']}"] += 1
        if payloads == 0 and split in ("direct", "indirect") and head["unit"] == "agent_execution":
            by["exposure_runs"]["no_verified_configuration"] += 1
        elif payloads:
            by["exposure_runs"]["with_payload_fixtures"] += 1
    unresolved = {k: g for k, g in groups.items() if not g["resolved"]}
    outcomes: Counter[str] = Counter()
    for sha, _group in unresolved.items():
        raw = _raw(partial, sha)
        if raw is None:
            outcomes["judge_not_stored"] += 1
            continue
        judge = strict_json_loads(raw)
        outcomes[f"attack_success={judge.get('attack_success')}"] += 1
    register = Counter(json.loads(line)["code"] for line in (partial / "register.jsonl").read_text(encoding="utf-8").splitlines()) \
        if (partial / "register.jsonl").exists() else Counter()
    out.update({k: dict(sorted(v.items())) for k, v in sorted(by.items())})
    out["issues"] = dict(sorted(issues.items()))
    out["register"] = dict(sorted(register.items()))
    out["exposure_classes"] = dict(sorted(exposure.items()))
    out["markers"] = dict(sorted(markers.items()))
    out["rerun_groups"] = {"groups": len(groups), "resolved": len(groups) - len(unresolved), "unresolved": len(unresolved),
                           "group_level_outcomes": dict(sorted(outcomes.items()))}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    data = report(args.corpus)
    text = json.dumps(data, indent=2, sort_keys=True)
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
