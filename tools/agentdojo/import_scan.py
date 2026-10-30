"""Full import of the pinned AgentDojo ``2024-06`` snapshot and gate R (local only; numbers, never content).

    uv run python tools/agentdojo/import_scan.py --out docs/reports/agentdojo [--workers 10] [--limit N]

What it does (D.6.10 item 3; J.4.2-J.4.3; PQ phase 6 exit):

1. **Import.** Every ``runs/**/*.json`` blob of ``ethz-spylab/agentdojo@c274885`` is read from the bare, extraction-free
   object store (``git ls-tree`` / ``git cat-file --batch``; no checkout). The ``runs`` tree id is checked against the
   profile pin and every blob against its git blob SHA-1 before it is mapped. Each blob is mapped with the
   ``agentdojo-upstream`` profile (origin ``git``, the pinned commit and path), sealed by the core writer, validated by
   the AER validator in release mode (locators resolved against the bytes), derived with the ``agentprov-prov/0.1``
   engine and checked with every tier-4 validator (``validate_prov``).
2. **Gate R** (J.4.3). Each native AER is joined to the converted tree of the frozen baseline by the converter's own
   layout rule (``convert_runs._output_relpath``, ported below as :func:`output_relpath`); R1 compares
   ``serialise(render_converted(AER))`` with the stored converted transcript bytes, R2 the compat graph bytes. R4
   compares every outcome-only AER with its ``EXCLUDED.json`` row; R5 lists the unmatched sets. Mismatches are counted
   by category: the first differing JSON Pointer with array indices replaced by ``*``.

The converted tree and ``EXCLUDED.json`` are read from ``$AGENTPROV_BASELINE_CORPUS`` (the AgentDojo-PROV checkout,
``corpus/corpus-og-agentdojo-runs-prov``); only files present in its listing are opened. Nothing prints or writes source
text: reports hold counts, issue codes, digests and corpus-relative paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from collections.abc import Iterator, Mapping
from multiprocessing import Pool
from pathlib import Path, PurePosixPath
from typing import Any, Final

REPO: Final = "https://github.com/ethz-spylab/agentdojo"
COMMIT: Final = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
RUNS_TREE: Final = "1227480d637f06ac435c809ab39803afa72f78fc"
DEFAULT_CACHE: Final = Path("~/.agentprov/cache/git/github.com/ethz-spylab/agentdojo.git").expanduser()
CONVERTED: Final = "corpus/corpus-og-agentdojo-runs-prov"
PROFILE: Final = "agentdojo-upstream"
BENIGN: Final = "benign"
MIXTRAL: Final = "runs/mistralai_Mixtral-8x7B-Instruct-v0.1/"


# ------------------------------------------------------------------------------------------------ the pinned blobs
def _git(cache: Path, *args: str) -> bytes:
    return subprocess.run(["git", "--git-dir", str(cache), *args], capture_output=True, check=True).stdout


def list_blobs(cache: Path) -> list[tuple[str, str, int]]:
    """``(path, blob sha1, size)`` of every ``runs/*.json`` blob at the pin, sorted by path. Checks the tree id."""
    tree = _git(cache, "rev-parse", f"{COMMIT}:runs").decode().strip()
    if tree != RUNS_TREE:
        raise SystemExit(f"runs tree {tree} != pinned {RUNS_TREE}")
    out = []
    for line in _git(cache, "ls-tree", "-r", "-l", COMMIT, "runs").decode().splitlines():
        meta, path = line.split("\t", 1)
        _mode, kind, sha, size = meta.split()
        if kind == "blob" and path.endswith(".json"):
            out.append((path, sha, int(size)))
    return sorted(out)


def read_blobs(cache: Path, entries: list[tuple[str, str, int]]) -> Iterator[tuple[str, str, bytes]]:
    """Stream the blobs with ``git cat-file --batch``; each is verified against its git blob SHA-1."""
    proc = subprocess.Popen(["git", "--git-dir", str(cache), "cat-file", "--batch"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for path, sha, size in entries:
            proc.stdin.write(sha.encode() + b"\n")
            proc.stdin.flush()
            head = proc.stdout.readline().split()
            if len(head) != 3 or head[0].decode() != sha or int(head[2]) != size:
                raise SystemExit(f"cat-file: unexpected header for {path}")
            data = proc.stdout.read(size)
            proc.stdout.read(1)
            if hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() != sha:
                raise SystemExit(f"blob {sha} of {path} does not hash to its id")
            yield path, sha, data
    finally:
        proc.stdin.close()
        proc.wait()


# ------------------------------------------------------------------------------------------------ the converter's layout
def pipeline_folder(pipeline_name: str) -> str:
    """``convert_runs._pipeline_folder`` (agentdojo_prov/convert_runs.py:136-138 @ 579a908).

    The baseline keeps ``.``, so a pipeline name ``..`` would be a ``..`` path component; this comparison tool refuses a
    result that is empty, ``.`` or ``..`` (escaping audit F-14). Every other name maps exactly as in the baseline."""
    folder = re.sub(r"[^A-Za-z0-9._-]", "_", str(pipeline_name))
    if folder in ("", ".", ".."):
        raise ValueError("pipeline name does not map to a safe folder name")
    return folder


def output_relpath(pipeline: str, suite: str, user: str, attack: str | None, injection: str | None) -> str:
    """``convert_runs._output_relpath`` plus the pipeline folder (convert_runs.py:175-183 @ 579a908): the v1 stem."""
    attack_type = attack or BENIGN
    if attack_type == BENIGN:
        rel = PurePosixPath(BENIGN) / f"{suite}_{user}_benign"
    else:
        inj = injection or "injection_task_unknown"
        rel = PurePosixPath(attack_type) / f"{suite}_{user}_x_{str(inj).replace('_', '')}_injection"
    path = PurePosixPath(pipeline_folder(pipeline)) / "prov" / rel
    if path.is_absolute() or ".." in path.parts:  # an attack or suite name from the log must not leave the tree
        raise ValueError("the converted stem is not a relative path inside the tree")
    return str(path)


def _category(expected: bytes, actual: bytes) -> str:
    from agentprov.testing.golden import diff_bytes

    diff = diff_bytes(expected, actual)
    if diff is None:
        return "equal"
    pointer = diff.pointer or "(unparsed)"
    return re.sub(r"/[0-9]+(?=/|$)", "/*", pointer)


# ------------------------------------------------------------------------------------------------ the worker
_STATE: dict[str, Any] = {}


def _init(converted_root: str | None, listing: frozenset[str], derive: bool) -> None:
    _STATE.update(root=converted_root, listing=listing, derive=derive)


class _Store:
    def __init__(self, raw: bytes) -> None:
        self.sha, self.raw = hashlib.sha256(raw).hexdigest(), raw

    def has(self, sha256: str) -> bool:
        return sha256 == self.sha

    def size(self, sha256: str) -> int:
        return len(self.raw)

    def read_bytes(self, sha256: str) -> bytes:
        return self.raw


def work(job: tuple[str, str, bytes]) -> dict[str, Any]:
    path, blob, raw = job
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import AerValidator

    row: dict[str, Any] = {"path": path, "mixtral": path.startswith(MIXTRAL)}
    try:
        origin = Origin.git(REPO, COMMIT, path, blob)
        outcome, unit = map_artefact(raw, origin, profile_id=PROFILE)
        data, info = aer_bytes(outcome)
        row.update(status="degenerate" if outcome.degenerate else "sealed", variant=unit.primary.variant if unit else None,
                   error_code=outcome.error_code, issues=[i["code"] for i in info.issues],
                   accounting=info.accounting.to_json()["status"], ex=info.ex, aer_sha256=info.file_sha256)
        profile = load_profile(PROFILE)
        validator = AerValidator(store=_Store(raw), catalogues=RuleRegistry.default(), mode="release",
                                 profile_digests={(profile.id, profile.version): profile.sha256})
        for line in data.splitlines(keepends=True):
            validator.feed(line)
        report = validator.finish()
        row.update(aer_ok=report.ok, aer_passed=report.passed and not report.skipped,
                   aer_errors=sorted({f.code for f in report.errors}), aer_skipped=sorted(report.skipped))
        with tempfile.TemporaryDirectory(prefix="agentprov-scan-") as tmp:
            target = Path(tmp) / "a.aer.jsonl"
            target.write_bytes(data)
            doc = load_aer(target)
        row["unit"] = doc.header.get("unit")
        _census(row, doc, info)
        if _STATE.get("derive"):
            _derive(row, doc)
        _gate_r(row, doc)
    except Exception as exc:  # a crash is a finding; the label is the pinned path, never content
        row.update(status="crash", code=getattr(exc, "code", type(exc).__name__),
                   where=traceback.format_exc().splitlines()[-1][:160])
    return row


def _census(row: dict[str, Any], doc: Any, info: Any) -> None:
    """Per-file facts for the profile census (D.6.10 item 3): cited rules and a few counts, no content."""
    cited: set[str] = set()
    pid_absent = pid_empty = 0
    for record in doc.records:
        cited.update(str(r).split("#", 1)[0] for r in record.get("rule", ()))
        for pointer, reason in (record.get("unk") or {}).items():
            if pointer.endswith("/provider_call_id"):
                pid_absent += reason == "not_recorded"
                pid_empty += reason == "ambiguous"
    duplicate = False
    for record in doc.records:
        if record.get("k") == "message" and record.get("role") == "assistant":
            ids = [p.get("provider_call_id") for p in record.get("parts", ()) if p.get("t") == "tool_call"]
            named = [i for i in ids if isinstance(i, str) and i]
            duplicate = duplicate or len(named) != len(set(named))
    row["rules_cited"] = sorted(cited)
    task = doc.header.get("task", {})
    row["benign"] = task.get("attack_id") is None
    row["defense_id"] = task.get("defense_id")
    row["counts"] = {
        "duplicate_id_logs": int(duplicate),
        "redactions": sum(1 for r in doc.records if r.get("k") == "decision" and r.get("verdict") == "redact"),
        "unexecuted_calls": sum(len(i.get("ids", ())) for i in info.issues if i["code"] == "unexecuted_tool_call"),
        "calls_id_absent": pid_absent,
        "calls_id_empty": pid_empty,
    }


def _derive(row: dict[str, Any], doc: Any) -> None:
    from agentprov.prov.engine import derive
    from agentprov.validate import validate_prov

    start = time.perf_counter()
    result = derive(doc)
    row["derive_s"] = time.perf_counter() - start
    report = validate_prov(result.prov_json, doc)
    row.update(prov_ok=report.ok, prov_passed=report.passed, prov_fail=sorted(o.id for o in report.failed()),
               rules_fired=dict(result.report.rules_fired),
               bundles=[b.iri.rsplit(".", 1)[0].removeprefix("xd:bundle.") for b in result.bundles])


def _gate_r(row: dict[str, Any], doc: Any) -> None:
    from agentprov.prov.compat.adprov_v2_3 import SPEC
    from agentprov.views.transcript_v1 import render_converted, serialise

    header = doc.header
    task = header.get("task", {})
    pipeline = (header.get("ext", {}).get("agentdojo", {}) or {}).get("pipeline_name")
    stem = output_relpath(str(pipeline), str(task.get("suite")), str(task.get("task_id")), task.get("attack_id"),
                          task.get("attack_target_id"))
    row["stem"] = stem
    if row.get("unit") == "outcome_only":
        judgements = {j.get("name"): j.get("value") for j in doc.of_kind("judgement")}
        run = doc.get("run") or {}
        duration = (run.get("t") or {}).get("dur_s")
        row["excluded_projection"] = {
            "pipeline": pipeline, "suite": task.get("suite"), "user_task_id": task.get("task_id"),
            "injection_task_id": task.get("attack_target_id"), "attack_type": task.get("attack_id") or BENIGN,
            "utility": judgements.get("utility"), "security": judgements.get("security"),
            "wall_clock_s": round(float(duration), 3) if duration is not None else None,
        }
    root = _STATE.get("root")
    if root is None or f"{stem}.transcript.json" not in _STATE["listing"]:
        row["converted"] = False
        return
    row["converted"] = True
    want_t = Path(root, f"{stem}.transcript.json").read_bytes()
    want_g = Path(root, f"{stem}.json").read_bytes()
    view = render_converted(doc)
    got_t = serialise(view)
    row["r1"] = got_t == want_t
    if not row["r1"]:
        row["r1_category"] = _category(want_t, got_t)
    got_g = SPEC.serialise(SPEC.build(view))
    row["r2"] = got_g == want_g
    if not row["r2"]:
        row["r2_category"] = _category(want_g, got_g)


# ------------------------------------------------------------------------------------------------ the parent
def converted_listing(root: Path) -> frozenset[str]:
    """Corpus-relative paths of the converted tree's ``*.transcript.json`` files (no file is opened)."""
    out = set()
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            if name.endswith(".transcript.json") and not name.startswith("._"):
                out.add(str(Path(dirpath, name).relative_to(root).as_posix()))
    return frozenset(out)


def scan(cache: Path, baseline: Path | None, *, workers: int = 10, limit: int | None = None,
         derive: bool = True) -> dict[str, Any]:
    entries = list_blobs(cache)
    if limit is not None:
        entries = entries[:limit]
    root = baseline / CONVERTED if baseline is not None else None
    listing = converted_listing(root) if root is not None and root.is_dir() else frozenset()
    started = time.perf_counter()
    with Pool(workers, initializer=_init, initargs=(str(root) if listing else None, listing, derive)) as pool:
        rows = list(pool.imap(work, read_blobs(cache, entries), chunksize=16))
    elapsed = time.perf_counter() - started
    return {"rows": rows, "entries": len(entries), "bytes": sum(e[2] for e in entries), "elapsed_s": elapsed,
            "listing": listing, "excluded": _excluded(root) if listing else None}


def _excluded(root: Path) -> list[dict[str, Any]]:
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    doc = strict_json_loads((root / "EXCLUDED.json").read_bytes(), IngestLimits())
    return list(doc["logs"])


def _jcs(value: Any) -> bytes:
    from agentprov.io.canonical import jcs_bytes

    return jcs_bytes(value)


def _profile_census(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """The quantities of the profile's ``observed`` counts for the ``2024-06`` part (D.6.10 item 3)."""
    def files(rule: str) -> int:
        return sum(rule in r.get("rules_cited", ()) for r in rows)

    def issue_files(code: str) -> int:
        return sum(code in r.get("issues", ()) for r in rows)

    def defence(name: str) -> int:
        return sum(r.get("defense_id") == name for r in rows)

    def total(key: str) -> int:
        return sum(r.get("counts", {}).get(key, 0) for r in rows)

    return {
        "agentdojo.benign_security_constant": {"files": sum(bool(r.get("benign")) for r in rows),
                                               "origin_rule_applied": files("agentdojo.benign_security_constant@1")},
        "agentdojo.dos_security_not_utility": {"files": files("agentdojo.dos_security_rule@1")},
        "agentdojo.silent_rerun_last_pass_only": {"null_final_logs": issue_files("retry_passes_inferred")},
        "agentdojo.injection_task_as_user_task_prepass": {"files": files("agentdojo.injection_task_as_user_task@1")},
        "agentdojo.empty_messages_with_outcome": {"files": sum(r.get("unit") == "outcome_only" for r in rows)},
        "agentdojo.run_error_imposes_outcome": {"files": issue_files("outcome_imposed_by_runner")},
        "agentdojo.incomplete_run": {"files": issue_files("incomplete_run") + issue_files("no_outcome_recorded")},
        "agentdojo.provider_call_id_anomalies": {
            "logs_with_absent_or_empty_ids": sum(bool(r.get("counts", {}).get("calls_id_absent") or
                                                      r.get("counts", {}).get("calls_id_empty")) for r in rows),
            "calls_id_absent": total("calls_id_absent"), "calls_id_empty": total("calls_id_empty"),
            "logs_with_duplicate_ids": total("duplicate_id_logs")},
        "agentdojo.unexecuted_trailing_calls": {"calls": total("unexecuted_calls"), "logs": issue_files("unexecuted_tool_call")},
        "agentdojo.pi_detector_redaction": {"logs": files("agentdojo.pi_detector_sentinel@1"), "redactions": total("redactions")},
        "agentdojo.tool_filter_aux_llm": {"logs": defence("tool_filter"),
                                          "logs_with_filter_messages": files("agentdojo.tool_filter_aux_message@1")},
        "agentdojo.repeat_user_prompt_reinsertion": {"logs": defence("repeat_user_prompt"),
                                                     "logs_with_copies": files("agentdojo.repeat_user_prompt_copy@1")},
        "agentdojo.spotlighting_delimiters": {"logs": defence("spotlighting_with_delimiting"),
                                              "logs_with_tool_results": files("agentdojo.spotlighting_content@1")},
        "agentdojo.placeholder_args_never_injection_evidence": {"present": 0},
    }


def summarise(result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The import report and the gate-R report (numbers, codes and pinned paths only)."""
    rows: list[dict[str, Any]] = result["rows"]
    issues: Counter[str] = Counter()
    issue_files: Counter[str] = Counter()
    for r in rows:
        issues.update(r.get("issues", ()))
        issue_files.update(set(r.get("issues", ())))
    crashes = [{"path": r["path"], "code": r["code"]} for r in rows if r["status"] == "crash"]
    rules: Counter[str] = Counter()
    bundles: Counter[str] = Counter()
    for r in rows:
        rules.update(r.get("rules_fired", {}))
        bundles.update(r.get("bundles", ()))
    derived = [r for r in rows if "prov_ok" in r]
    secs = sorted(r["derive_s"] for r in derived) or [0.0]
    mixtral = [r for r in rows if r["mixtral"]]
    imp = {
        "source": {"repo": REPO, "commit": COMMIT, "runs_tree": RUNS_TREE, "profile": PROFILE},
        "blobs": result["entries"],
        "bytes": result["bytes"],
        "crashes": len(crashes),
        "crash_rows": crashes,
        "sealed": sum(r["status"] in ("sealed", "degenerate") for r in rows),
        "degenerate": sum(r["status"] == "degenerate" for r in rows),
        "variants": dict(Counter(r.get("variant") for r in rows if r.get("variant"))),
        "units": dict(Counter(r.get("unit") for r in rows if r.get("unit"))),
        "outcome_only": sum(r.get("unit") == "outcome_only" for r in rows),
        "mixtral": {"files": len(mixtral), "sealed": sum(r["status"] == "sealed" for r in mixtral),
                    "units": dict(Counter(r.get("unit") for r in mixtral))},
        "accounting": dict(Counter(r.get("accounting") for r in rows if r.get("accounting"))),
        "issues_by_code": dict(sorted(issues.items())),
        "files_by_issue_code": dict(sorted(issue_files.items())),
        "aer_validator": {"ok": sum(bool(r.get("aer_ok")) for r in rows),
                          "passed_release": sum(bool(r.get("aer_passed")) for r in rows),
                          "error_codes": dict(Counter(c for r in rows for c in r.get("aer_errors", ())))},
        "prov": {"derived": len(derived), "validate_prov_ok": sum(bool(r["prov_ok"]) for r in derived),
                 "validate_prov_passed": sum(bool(r["prov_passed"]) for r in derived),
                 "failed_checks": dict(Counter(c for r in derived for c in r["prov_fail"])),
                 "statements_by_rule": dict(sorted(rules.items())), "bundles": dict(sorted(bundles.items())),
                 "derive_ms": {"median": round(secs[len(secs) // 2] * 1000, 1),
                               "p99": round(secs[int(len(secs) * 0.99)] * 1000, 1),
                               "max": round(secs[-1] * 1000, 1)}},
        "census_2024_06": _profile_census(rows),
        "elapsed_s": round(result["elapsed_s"], 1),
    }
    listing: frozenset[str] = result["listing"]
    gate: dict[str, Any] = {"available": bool(listing)}
    if listing:
        compared = [r for r in rows if r.get("converted")]
        r1_cat = Counter(r["r1_category"] for r in compared if not r["r1"])
        r2_cat = Counter(r["r2_category"] for r in compared if not r["r2"])
        claimed = {f"{r['stem']}.transcript.json" for r in compared}
        excluded = result["excluded"] or []
        by_log = {f"runs/{e['log']}": e for e in excluded}
        r4_rows = [r for r in rows if r.get("unit") == "outcome_only"]
        r4_equal = 0
        r4_missing = 0
        for r in r4_rows:
            e = by_log.get(r["path"])
            if e is None:
                r4_missing += 1
                continue
            keys = ("pipeline", "suite", "user_task_id", "injection_task_id", "attack_type", "utility", "security",
                    "wall_clock_s")
            r4_equal += _jcs({k: e.get(k) for k in keys}) == _jcs({k: r["excluded_projection"].get(k) for k in keys})
        native_only = sorted(r["path"] for r in rows if not r.get("converted") and r["path"] not in by_log)
        gate.update({
            "converted_transcripts": len(listing),
            "comparable_pairs": len(compared),
            "R1": {"pass": sum(bool(r["r1"]) for r in compared), "fail": sum(not r["r1"] for r in compared),
                   "categories": dict(r1_cat.most_common())},
            "R2": {"pass": sum(bool(r["r2"]) for r in compared), "fail": sum(not r["r2"] for r in compared),
                   "categories": dict(r2_cat.most_common())},
            "R4": {"excluded_rows": len(excluded), "outcome_only_aers": len(r4_rows), "equal": r4_equal,
                   "outcome_only_without_row": r4_missing},
            "R5": {"native_only": native_only, "native_only_count": len(native_only),
                   "v1_only": sorted(listing - claimed), "v1_only_count": len(listing - claimed)},
        })
        gate["claim_gate"] = "pass" if gate["R1"]["fail"] == 0 and gate["R2"]["fail"] == 0 and \
            gate["comparable_pairs"] == 18027 else "fail"
    return imp, gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="the bare object store of ethz-spylab/agentdojo")
    parser.add_argument("--baseline", type=Path, default=os.environ.get("AGENTPROV_BASELINE_CORPUS"),
                        help="the AgentDojo-PROV checkout (gate R); default $AGENTPROV_BASELINE_CORPUS")
    parser.add_argument("--out", type=Path, required=True, help="report directory (docs/reports/agentdojo)")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-derive", action="store_true", help="skip derive + validate_prov")
    args = parser.parse_args()
    result = scan(args.cache, Path(args.baseline) if args.baseline else None, workers=args.workers, limit=args.limit,
                  derive=not args.no_derive)
    imp, gate = summarise(result)
    args.out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.limit is None else f".limit{args.limit}"
    (args.out / f"import-2024-06{suffix}.json").write_text(json.dumps(imp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / f"gate-r-full{suffix}.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{imp['blobs']} blobs, {imp['sealed']} sealed, {imp['crashes']} crashes, {imp['outcome_only']} outcome-only; "
          f"R1 {gate.get('R1', {}).get('pass')}/{gate.get('comparable_pairs')}, R2 {gate.get('R2', {}).get('pass')}; "
          f"{imp['elapsed_s']} s")
    return 1 if imp["crashes"] else 0


if __name__ == "__main__":
    sys.exit(main())
