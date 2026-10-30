"""Numbers-only report of a working corpus written by ``agentprov import`` (HON-10; D.3.2; MN N.2.2).

    uv run python tools/import_report.py --corpus DIR.partial --summary SUMMARY.json --out REPORT.json \
        [--compare ADHOC.json] [--workers 10] [--wall-s SECONDS] [--command TEXT]

It reads only AgentPROV-format files of the corpus (manifest, index, register, validation rows, AER and PROV files) and
writes counts, codes, digests and versions; never source text. For every index row it:

* reads the AER, checks its execution digest against ``digests.aer`` and the file against the layout path;
* re-derives ``agentprov-prov/0.1`` from the AER and its SEM documents (the inputs of the import's PROV stage) in a fresh
  process and compares the bytes with the stored PROV-JSON and ``digests.prov`` (the recompute check of H.8.5, run here
  because ``agentprov recompute`` is phase 11);
* tallies units, dialect variants, seal accounting verdicts, seal issue codes, PROV statements by rule (the engine's
  derivation report) and bundles.

``--compare`` takes the report of the earlier ad-hoc scan (``tools/agentdojo/import_scan.py``) and records, key by key,
whether the CLI import reproduces its counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

SPEC = "agentprov-prov/0.1"


def _lines(path: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def _row(job: tuple[str, str, str, str | None, str | None, dict[str, str]]) -> dict[str, Any]:
    root, aer_rel, aer_digest, prov_rel, prov_digest, sem_paths = job
    from agentprov.adapters.runner.provjob import PROFILES
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.prov.engine import derive
    from agentprov.sem.reader import load_sem_bytes

    out: dict[str, Any] = {}
    data = Path(root, aer_rel).read_bytes()
    doc = load_aer_bytes(data)
    out["aer_digest_ok"] = doc.execution_digest == aer_digest
    header = doc.header
    out["unit"] = header.get("unit")
    out["variant"] = (header.get("dialect") or {}).get("variant")
    out["accounting"] = (doc.seal.get("accounting") or {}).get("status")
    out["issues"] = [str(i.get("code")) for i in doc.seal.get("issues", ())]
    out["origin_kinds"] = sorted({str(a["origin"]["kind"]) for a in header.get("artifacts", ())})
    out["records"] = len(doc.records) + 1
    if prov_rel is not None:
        stored = Path(root, prov_rel).read_bytes()
        # the stored PROV was derived from the AER and its SEM documents (provjob): re-derive from the same inputs
        sems = [load_sem_bytes(Path(root, rel).read_bytes()) for _ref, rel in sorted(sem_paths.items())]
        profiles = {(PROFILES[ref].id, PROFILES[ref].version): PROFILES[ref] for ref in sorted(sem_paths)}
        result = derive(doc, sems, sem_profiles=profiles, check_aer=False)
        out["prov_digest_ok"] = hashlib.sha256(stored).hexdigest() == prov_digest
        out["recompute_identical"] = result.prov_json == stored
        out["rules_fired"] = dict(result.report.rules_fired)
        out["bundles"] = [b.iri.rsplit(".", 1)[0].removeprefix("xd:bundle.") for b in result.bundles]
    return out


def build(corpus: Path, summary: dict[str, Any], workers: int) -> dict[str, Any]:
    manifest = json.loads((corpus / "corpus.json").read_text(encoding="utf-8"))
    derivation = json.loads((corpus / "derivation.json").read_text(encoding="utf-8"))
    rows = _lines(corpus / "executions.jsonl")
    register = _lines(corpus / "register.jsonl")
    validation = {r["ex"]: r for r in _lines(corpus / "validation" / "results.jsonl")} if (corpus / "validation" / "results.jsonl").exists() else {}
    jobs = []
    for row in rows:
        prov_path = (row["paths"].get("prov") or {}).get(SPEC, {}).get("json")
        prov_digest = ((row["digests"].get("prov") or {}).get(SPEC) or {}).get("json")
        jobs.append((str(corpus), row["paths"]["aer"], row["digests"]["aer"].removeprefix("sha256:"), prov_path,
                     None if prov_digest is None else prov_digest.removeprefix("sha256:"), dict(row["paths"].get("sem") or {})))
    with Pool(workers) as pool:
        facts = pool.map(_row, jobs, chunksize=32)
    issues: Counter[str] = Counter()
    files_by_issue: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    bundles: Counter[str] = Counter()
    for fact in facts:
        issues.update(fact["issues"])
        files_by_issue.update(set(fact["issues"]))
        rules.update(fact.get("rules_fired", {}))
        bundles.update(fact.get("bundles", ()))
    checks: Counter[str] = Counter()
    failed_checks: Counter[str] = Counter()
    for v in validation.values():
        for check, status in v.get("checks", {}).items():
            checks[status] += 1
            if status in ("fail", "skipped"):
                failed_checks[check] += 1
    derived = [f for f in facts if "recompute_identical" in f]
    return {
        "format": "agentprov-import-report/0.1",
        "corpus": {"corpus_id": manifest["corpus_id"], "state": manifest["state"], "partial": manifest["partial"],
                   "source": manifest["sources"][0]["source_id"], "parts": manifest["sources"][0]["parts"],
                   "profile": manifest["sources"][0]["profile"], "snapshot": manifest["sources"][0]["snapshots"][0]},
        "cli": {"exit_code": summary["exit_code"], "outcome": summary["outcome"], "counters": summary["counters"],
                "issues_by_code": summary["issues_by_code"], "failures": len(summary["failures"]),
                "options": {k: v for k, v in summary["options"].items() if k not in ("corpus", "input", "cache_dir")}},
        "derivation": {s["stage"]: {k: s[k] for k in sorted(s) if k in ("engine", "engine_code_sha256", "adapter",
                                                                         "adapter_code_sha256", "profile", "spec",
                                                                         "fn_digest", "mode")}
                       for s in derivation["stages"]},
        "producer": {k: manifest["producer"][k] for k in ("agentprov_version", "python", "isolation", "key_distributions",
                                                           "interpreter_advisory", "lockfile_sha256")},
        "executions": len(rows),
        "by_status": dict(sorted(Counter(r["status"] for r in rows).items())),
        "by_completeness": dict(sorted(Counter(r["completeness"] for r in rows).items())),
        "units": dict(sorted(Counter(f["unit"] for f in facts).items())),
        "variants": dict(sorted(Counter(f["variant"] for f in facts).items())),
        "origin_kinds": dict(sorted(Counter(k for f in facts for k in f["origin_kinds"]).items())),
        "accounting": dict(sorted(Counter(f["accounting"] for f in facts).items())),
        "seal_issues_by_code": dict(sorted(issues.items())),
        "files_by_seal_issue_code": dict(sorted(files_by_issue.items())),
        "register_by_code": dict(sorted(Counter(e["code"] for e in register).items())),
        "register_by_disposition": dict(sorted(Counter(e["disposition"] for e in register).items())),
        "aer": {"digest_ok": sum(f["aer_digest_ok"] for f in facts),
                "validator_pass": sum(1 for v in validation.values() if v["aer"]["verdict"] == "pass"),
                "validator_mode": sorted({v["aer"]["mode"] for v in validation.values()})},
        "prov": {"derived": len(derived), "digest_ok": sum(f["prov_digest_ok"] for f in derived),
                 "recompute_identical": sum(f["recompute_identical"] for f in derived),
                 "validation_pass": sum(1 for v in validation.values() if v["verdict"] == "pass"),
                 "check_outcomes": dict(sorted(checks.items())), "failed_or_skipped_checks": dict(sorted(failed_checks.items())),
                 "statements_by_rule": dict(sorted(rules.items())), "bundles": dict(sorted(bundles.items()))},
        "records": sum(f["records"] for f in facts),
    }


def compare_derive_scan(report: dict[str, Any], scan: dict[str, Any], tree: str) -> dict[str, Any]:
    """Comparison with one tree of the phase-5 derive scan (tools/prov/derive_scan.py)."""
    t = scan["trees"][tree]
    pairs = {
        "derived": (report["prov"]["derived"], t["derived"]),
        "degenerate": (report["cli"]["counters"].get("degenerate"), t["degenerate"]),
        "statements_by_rule": (report["prov"]["statements_by_rule"], t["statements_by_rule"]),
        "bundles": (report["prov"]["bundles"], t["bundles"]),
    }
    return {key: {"equal": a == b, "cli": a if not isinstance(a, dict) else None, "scan": b if not isinstance(b, dict) else None}
            for key, (a, b) in pairs.items()}


def compare_accounting(report: dict[str, Any], gate: dict[str, Any], tree: str) -> dict[str, Any]:
    """Comparison of the seal accounting verdicts with a migration gate report (details.accounting.by_tree)."""
    expected = gate["details"]["accounting"]["by_tree"][tree]
    return {"accounting": {"equal": report["accounting"] == expected, "gate": expected}}


def compare(report: dict[str, Any], adhoc: dict[str, Any]) -> dict[str, Any]:
    """Key-by-key comparison with the ad-hoc scan report (import_scan.py)."""
    pairs = {
        "sealed": (report["executions"], adhoc.get("sealed")),
        "degenerate": (report["cli"]["counters"].get("degenerate"), adhoc.get("degenerate")),
        "crashes": (0 if report["cli"]["exit_code"] in (0, 1) else None, adhoc.get("crashes")),
        "units": (report["units"], adhoc.get("units")),
        "variants": (report["variants"], adhoc.get("variants")),
        "accounting": (report["accounting"], adhoc.get("accounting")),
        "issues_by_code": (report["seal_issues_by_code"], adhoc.get("issues_by_code")),
        "files_by_issue_code": (report["files_by_seal_issue_code"], adhoc.get("files_by_issue_code")),
        "aer_validator_pass": (report["aer"]["validator_pass"], (adhoc.get("aer_validator") or {}).get("passed_release")),
        "prov_derived": (report["prov"]["derived"], (adhoc.get("prov") or {}).get("derived")),
        "validate_prov_pass": (report["prov"]["validation_pass"], (adhoc.get("prov") or {}).get("validate_prov_passed")),
        "statements_by_rule": (report["prov"]["statements_by_rule"], (adhoc.get("prov") or {}).get("statements_by_rule")),
        "bundles": (report["prov"]["bundles"], (adhoc.get("prov") or {}).get("bundles")),
    }
    return {key: {"equal": a == b, "cli": a if not isinstance(a, dict) else None, "adhoc": b if not isinstance(b, dict) else None}
            for key, (a, b) in pairs.items() if b is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True, help="the working corpus (DIR.partial)")
    parser.add_argument("--summary", type=Path, required=True, help="the import's --summary-json document")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path, help="an earlier ad-hoc report to compare with")
    parser.add_argument("--compare-scan", type=Path, help="the phase-5 derive-scan report (docs/reports/prov/derive-scan.json)")
    parser.add_argument("--compare-gate", type=Path, help="a migration gate report holding details.accounting (A-full.json)")
    parser.add_argument("--tree", default="release", help="the baseline tree of --compare-scan and --compare-gate")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--wall-s", type=float, help="wall time of the import, measured outside it")
    parser.add_argument("--command", help="the import command line, with paths written relative or <home>")
    parser.add_argument("--extra", type=Path, help="a JSON object merged into the report (determinism checks, dates)")
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    report = build(args.corpus, summary, args.workers)
    if args.wall_s is not None:
        report["wall_s"] = round(args.wall_s, 1)
    if args.command:
        report["command"] = args.command
    keys: dict[str, Any] = {}
    sources = []
    if args.compare:
        keys.update(compare(report, json.loads(args.compare.read_text())))
        sources.append(args.compare.as_posix())
    if args.compare_scan:
        keys.update(compare_derive_scan(report, json.loads(args.compare_scan.read_text()), args.tree))
        sources.append(f"{args.compare_scan.as_posix()} (tree {args.tree})")
    if args.compare_gate:
        keys.update(compare_accounting(report, json.loads(args.compare_gate.read_text()), args.tree))
        sources.append(f"{args.compare_gate.as_posix()} (tree {args.tree})")
    if keys:
        report["comparison"] = {"with": sources, "keys": keys}
    if args.extra:
        report.update(json.loads(args.extra.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = report.get("comparison", {}).get("keys", {})
    print(f"{report['executions']} executions; exit {report['cli']['exit_code']}; recompute identical "
          f"{report['prov']['recompute_identical']}/{report['prov']['derived']}; comparison equal "
          f"{sum(v['equal'] for v in keys.values())}/{len(keys)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
