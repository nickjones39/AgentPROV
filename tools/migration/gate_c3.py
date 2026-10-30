"""Gate C3 (J.3.4 row C3): the baseline's scoring against the ``agentdojo.scoring`` rule sets, over all 35,691 traces.

    uv run python tools/migration/gate_c3.py --report docs/reports/migration/C3.json [--baseline DIR] [--baseline-python PY]
        [--cache GITDIR] [--workers N] [--limit N] [--old-from DIR]

Local, no network.

* **old**: ``baseline_probe.py c3`` in the baseline interpreter: ``stats.trace_record`` and ``scoring.score_trace`` on
  every trace of both trees with its model folder's ``outcome_replay.json`` row; the verdict
  ``{scored, attack_success, unscored_reason, rerun}`` and the record and row fields the rule reads (``--old-from`` reuses
  a probe output directory);
* **new**: each trace mapped by the product mappers (``corpus-og-agentdojo-runs-prov``: the native June-2024 log, profile
  ``agentdojo-upstream``, from the pinned blobs of the fetch cache and joined by the converter's layout rule as in gate R;
  ``corpus-prov``: the released transcript, profile ``adprov-v1``), annotated by ``agentdojo.suites@1``, and its facts
  built by :mod:`agentprov.migration.gate_c3` from the AER and SEM; then
  ``agentprov.adapters.agentdojo.semantics.scoring.score`` under ``agentdojo.scoring@1`` (the v2.3 rules verbatim) and
  ``@2`` (F-60's DoS gating), the regen-batch session's item 19, with the baseline's replay row as the shared input.

Observations (register ``migration/expected_differences.toml``, ``comparison = "C3"``): ``rec:<field>:<old>-><new>`` for
a fact that differs, ``run_error:<old>-><new>``, ``verdict@1:<member>`` and ``verdict@2:<member>`` for a verdict that
differs, ``new:missing`` for a trace AgentPROV does not map. Pass (J.3.4): every observation absorbed; ``@1`` verdicts
may differ only through a registered fact difference. Until item 19 is in the build the facts are still compared and the
verdicts are reported ``missing`` (``ok: null``). The report holds item paths, labels and counts; never transcript text.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentdojo"))
import import_scan as scan  # noqa: E402  (gate R's pinned-blob reader and the converter's layout rule)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "tools" / "migration" / "baseline_probe.py"
HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
DEFAULT_PYTHON = HOME / "baseline" / "venv-579a908" / "bin" / "python3.12"
BASELINE_COMMIT: Final = "579a908354b93361efe0905ffb7623256aa96a06"
OG_TREE: Final = "corpus-og-agentdojo-runs-prov"


def old_side(baseline: Path, python: Path, work: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(python), "-I", "-B", str(PROBE), "c3", "--corpus", str(baseline / "corpus"), "--out", str(work)],
                   cwd=work, check=True, capture_output=True, timeout=7200,
                   env={"PATH": os.environ.get("PATH", ""), "HOME": str(work)})
    rows = [json.loads(line) for line in (work / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows, json.loads((work / "probe.json").read_text(encoding="utf-8"))


_STATE: dict[str, Any] = {}


def new_scorer() -> Any:
    try:
        from agentprov.adapters.agentdojo.semantics import scoring
    except ImportError:
        return None
    return getattr(scoring, "score", None)


def _init(baseline: str) -> None:
    from agentprov.adapters.runner.provjob import PROFILES

    _STATE.update(baseline=baseline, profile=PROFILES["agentdojo.suites@1"])


def _facts(data: bytes, origin: Any, profile_id: str) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    from agentprov.adapters.runner import aer_bytes, map_artefact
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.migration.gate_c3 import facts
    from agentprov.sem.engine import annotate, dumps_sem

    aer_data, _info = aer_bytes(map_artefact(data, origin, profile_id=profile_id)[0])
    records = [json.loads(line) for line in aer_data.splitlines()]
    sem = [json.loads(line) for line in dumps_sem(annotate(load_aer_bytes(aer_data), _STATE["profile"])).splitlines()]
    rec, run_error = facts(records, [a for a in sem if a.get("k") == "ann"])
    return rec, run_error, records[0]


def work_native(job: tuple[str, str, bytes]) -> dict[str, Any]:
    from agentprov.adapters.types import Origin

    path, blob, raw = job
    try:
        rec, run_error, header = _facts(raw, Origin.git(scan.REPO, scan.COMMIT, path, blob), scan.PROFILE)
        task = header.get("task", {})
        pipeline = (header.get("ext", {}).get("agentdojo", {}) or {}).get("pipeline_name")
        stem = scan.output_relpath(str(pipeline), str(task.get("suite")), str(task.get("task_id")), task.get("attack_id"),
                                   task.get("attack_target_id"))
        return {"path": path, "rec": rec, "run_error": run_error, "stem": stem}
    except Exception as exc:  # a crash is a finding; the label is the pinned path, never content
        return {"path": path, "crash": getattr(exc, "code", type(exc).__name__)}


def work_release(item: str) -> dict[str, Any]:
    from agentprov.adapters.types import Origin

    rel = item.split("/", 1)[1] + ".transcript.json"
    try:
        data = Path(_STATE["baseline"], "corpus", "corpus-prov", rel).read_bytes()
        origin = Origin.corpus("AgentDojo-PROV", "2.3", f"corpus-prov/{rel}", producer_commit=BASELINE_COMMIT)
        rec, run_error, _header = _facts(data, origin, "adprov-v1")
        return {"item": item, "rec": rec, "run_error": run_error}
    except Exception as exc:
        return {"item": item, "crash": getattr(exc, "code", type(exc).__name__)}


def new_side(baseline: Path, cache: Path, items: list[str], *, workers: int,
             native_limit: int | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """``item -> {rec, run_error}`` for every mappable trace, and ``item -> crash code`` (``native_limit``: map only the
    first N pinned logs, for a development run)."""
    out: dict[str, dict[str, Any]] = {}
    crashes: dict[str, str] = {}
    wanted = set(items)
    release = [i for i in items if i.startswith("corpus-prov/")]
    with Pool(workers, initializer=_init, initargs=(str(baseline),)) as pool:
        if any(i.startswith(OG_TREE + "/") for i in items):
            entries = scan.list_blobs(cache)[:native_limit]
            for row in pool.imap(work_native, scan.read_blobs(cache, entries), chunksize=16):
                if "crash" in row:
                    crashes[f"native:{row['path']}"] = str(row["crash"])
                    continue
                item = f"{OG_TREE}/{row['stem']}"
                if item in wanted:
                    out[item] = {"rec": row["rec"], "run_error": row["run_error"]}
        for row in pool.imap(work_release, release, chunksize=16):
            if "crash" in row:
                crashes[row["item"]] = str(row["crash"])
            else:
                out[row["item"]] = {"rec": row["rec"], "run_error": row["run_error"]}
    return out, crashes


def compare(old_rows: list[dict[str, Any]], new: dict[str, dict[str, Any]], score: Any) -> list[Any]:
    from agentprov.migration.gate_c3 import field_differences
    from agentprov.migration.xd import Observation

    observations: list[Any] = []
    for row in old_rows:
        item = row["item"]
        got = new.get(item)
        if got is None:
            observations.append(Observation("C3", item, "new:missing"))
            continue
        for name in field_differences(row["rec"], got["rec"]):
            observations.append(Observation("C3", item, f"rec:{name}:{_label(row['rec'].get(name))}->{_label(got['rec'].get(name))}"))
        if row["run_error"] != got["run_error"]:
            observations.append(Observation("C3", item, f"run_error:{_label(row['run_error'])}->{_label(got['run_error'])}"))
        if score is None:
            continue
        for rule_set in ("agentdojo.scoring@1", "agentdojo.scoring@2"):
            verdict = score(got["rec"], row["row"] or None, run_error=got["run_error"], rule_set=rule_set).as_dict()
            for member in sorted(verdict):
                if verdict[member] != row["verdict"].get(member):
                    tag = rule_set.rsplit("@", 1)[1]
                    observations.append(Observation("C3", item, f"verdict@{tag}:{member}:{_label(row['verdict'].get(member))}"
                                                                f"->{_label(verdict[member])}"))
    return observations


def _label(value: Any) -> str:
    return json.dumps(value) if not isinstance(value, str) else value


def main() -> int:
    from agentprov.migration.xd import check, load_register

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=os.environ.get("AGENTPROV_BASELINE_CORPUS"))
    parser.add_argument("--baseline-python", type=Path,
                        default=Path(os.environ["AGENTPROV_BASELINE_PYTHON"]) if os.environ.get("AGENTPROV_BASELINE_PYTHON")
                        else DEFAULT_PYTHON)
    parser.add_argument("--work", type=Path, default=HOME / "migration-work" / "c3")
    parser.add_argument("--old-from", type=Path, help="reuse this probe output directory (verdicts.jsonl, probe.json)")
    parser.add_argument("--cache", type=Path, default=scan.DEFAULT_CACHE)
    parser.add_argument("--register", type=Path, default=REPO_ROOT / "migration" / "expected_differences.toml")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int, help="development: the first N released traces and N pinned logs only")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.baseline is None:
        parser.error("--baseline or $AGENTPROV_BASELINE_CORPUS is required")
    if args.old_from is not None:
        rows = [json.loads(line) for line in (args.old_from / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()]
        probe = json.loads((args.old_from / "probe.json").read_text(encoding="utf-8"))
    else:
        rows, probe = old_side(Path(args.baseline), args.baseline_python, args.work)
    score = new_scorer()
    started = time.perf_counter()
    if args.limit is not None:  # the first N released traces, and the og traces the first N pinned logs map to
        release = [r for r in rows if r["item"].startswith("corpus-prov/")][: args.limit]
        og = [r for r in rows if r["item"].startswith(OG_TREE + "/")]
        new, crashes = new_side(Path(args.baseline), args.cache, [r["item"] for r in release + og], workers=args.workers,
                                native_limit=args.limit)
        rows = release + [r for r in og if r["item"] in new]
    else:
        new, crashes = new_side(Path(args.baseline), args.cache, [r["item"] for r in rows], workers=args.workers)
    table: Counter[tuple[str, bool, str | None, Any]] = Counter()
    for row in rows:
        verdict = row["verdict"]
        table[(row["item"].split("/", 1)[0], verdict["scored"], verdict["unscored_reason"], verdict["attack_success"])] += 1
    observations = compare(rows, new, score)
    result = check(observations, load_register(args.register))
    keys: Counter[str] = Counter(o.key for o in observations)
    firsts: dict[str, list[str]] = {}
    for o in observations:
        bucket = firsts.setdefault(o.key, [])
        if len(bucket) < 5:
            bucket.append(o.item)
    report: dict[str, Any] = {
        "format": "agentprov-migration-gate/0.1", "gate": "C3", "traces": len(rows), "mapped": len(new),
        "crashes": len(crashes), "crash_codes": dict(sorted(crashes.items())[:20]),
        "old": {"identity": probe.get("identity"), "replay_files": probe.get("replay_files"),
                "verdicts": [{"tree": t, "scored": s, "unscored_reason": r, "attack_success": a, "count": n}
                             for (t, s, r, a), n in sorted(table.items(), key=lambda kv: str(kv[0]))]},
        "observations": dict(sorted(keys.items())), "observation_items_first": dict(sorted(firsts.items())),
        "failures": result.failures(), "absorbed_by_entry": result.counts_by_entry(),
        "limit": args.limit, "elapsed_s": round(time.perf_counter() - started, 1),
    }
    if score is None:
        report.update(ok=None, new_side="facts only: agentdojo.scoring@1/@2 are not in this build (regen-batch item 19)")
    else:
        report.update(ok=result.ok and not crashes, new_side="present")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True).replace(str(Path.home()), "<home>")  # the probe identity's paths
    args.report.write_text(text + "\n", encoding="utf-8")
    print(f"C3: {len(rows)} traces, {len(new)} mapped, {len(crashes)} crash(es), {len(observations)} observation(s), "
          f"{len(result.failures())} failure(s); new side: {report['new_side']}")
    return 0 if report["ok"] in (True, None) else 1


if __name__ == "__main__":
    sys.exit(main())
