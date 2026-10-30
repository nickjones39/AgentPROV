"""Gate D: ``agentprov-prov/0.1`` derivation validated on all migration AERs (J.3.5; D-49).

The gate reads **sealed AERs that already exist** (the golden mappings at golden scope; the stored AERs of the given
corpora at full scope), re-derives SEM (``agentdojo.suites@1``) and PROV in worker processes, validates every D8 tier in release
mode (a skipped check is a failure, MP-3), runs the dedicated never-emit and generic-kind checks and, on the full trees,
compares the cross-count invariants with the J.3.5 table. The per-execution work is :mod:`agentprov.migration.gate_d_worker`.

**Read-only.** A corpus is opened through :class:`~agentprov.corpus.reader.CorpusReader`; nothing is written into it, no scratch
store is used (the workers keep SEM and PROV in memory) and a report path inside a corpus is refused (exit 4). The only
outputs are the report JSON, its short markdown and the per-execution JSONL, written where the caller says.

**Scopes.** ``golden``: the 19 v1 AERs and 9 native AERs of ``tests/golden/test_gate_d.py``, derived twice (byte-identical), with the
committed pins ``gate_d_digests.json`` (E.9). ``full``: every execution of every given corpus; the corpora are classified into the
trees ``release`` and ``converted`` (v1 imports of the two baseline trees) and ``native`` (the June-2024 upstream import); each
tree must be present, complete and match its column of the J.3.5 table, or the gap must be accepted explicitly
(``accept_gaps``; recorded in the report). ``sample``: ``full`` with ``limit``, an evenly spaced subset; a diagnostic report that
never satisfies the order of AD-07. The performance record (per-execution wall time and statement counts) is in the report; the
digest listings (J.3.0) are in its ``outputs``.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.reader import CorpusReader, resolve_corpus
from agentprov.envinfo import interpreter_advisory
from agentprov.errors import AgentProvError
from agentprov.io.atomic import atomic_write_text
from agentprov.io.workers import resolve_worker_count
from agentprov.migration import gates
from agentprov.migration.gate_d_worker import NATIVE_PROFILE, WorkItem, classify_tree, run_item
from agentprov.migration.gates import DEFAULT_SEED, FAIL, LISTED_FAILURES, PASS, Check, GateReport
from agentprov.migration.lock import REPO_ROOT, lock_sha256
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent

__all__ = [
    "CROSS_COUNTS",
    "EXPECTED_EXECUTIONS",
    "GateDError",
    "GateDResult",
    "gate_d_validate",
    "markdown",
    "write_outputs",
]

#: Executions per tree (J.3.5 "Inputs"; J.1.4; J.4): the v1 import of the release tree, of the converted tree, and the native import.
EXPECTED_EXECUTIONS: Final = {"release": 17_664, "converted": 18_027, "native": 18_241}
TREES: Final = ("release", "converted", "native")
DEFAULT_PINS: Final = REPO_ROOT / "tests" / "golden" / "gate_d_digests.json"
BASELINE_COMMIT: Final = "579a908354b93361efe0905ffb7623256aa96a06"


@dataclass(frozen=True, slots=True)
class Invariant:
    name: str
    metric: str  # the summed per-execution metric (gate_d_worker)
    release: int
    converted: int


#: The cross-count invariants of J.3.5 (release, converted); the native import's matched executions take the converted column.
CROSS_COUNTS: Final = (
    Invariant("tool_execution_activities", "te_prov", 64_781, 68_620),
    Invariant("tool_call_request_entities", "req_prov", 64_829, 68_773),
    Invariant("requests_without_execution", "unexec_prov", 48, 153),
    Invariant("model_invocations_generating_assistant_message", "inv_prov", 64_897, 73_551),
    Invariant("user_message_entities", "user_prov", 17_664, 21_658),
    Invariant("system_message_entities", "system_prov", 17_664, 18_027),
    Invariant("executions_without_tool_execution", "zero_te", 1_417, 762),
    Invariant("wasGeneratedBy_tool_result_tool_execution", "gen_result_te", 64_781, 68_620),
    Invariant("activity_records", "activity_records", 0, 0),
    Invariant("artefact_records", "artefact_records", 0, 0),
    Invariant("generic_rule_statements", "generic_statements", 0, 0),
)


class GateDError(AgentProvError):
    """Gate D cannot run (exit 70: a worker died) or was refused (exit 4: the report would be written into a corpus)."""

    code = "migration.gate_d"
    exit_code = 70


@dataclass(slots=True)
class GateDResult:
    report: GateReport
    rows: list[dict[str, Any]] = field(default_factory=list)  # one per execution, for the JSONL


@dataclass(slots=True)
class _Source:
    label: str
    root: Path
    tree: str
    total: int
    selected: int
    index_sha256: str
    sealed: bool


# ------------------------------------------------------------------------------------------------------------- inputs


def _label(path: Path) -> str:
    name = path.name
    return name[: -len(".partial")] if name.endswith(".partial") else name


def _select(rows: Sequence[Any], limit: int | None) -> list[Any]:
    """The whole index, or ``limit`` rows evenly spaced over it (deterministic: the index is sorted by execution id)."""
    if limit is None or limit >= len(rows):
        return list(rows)
    return [rows[i * len(rows) // limit] for i in range(limit)]


def corpus_items(
    corpora: Sequence[Path], limit: int | None
) -> tuple[list[WorkItem], list[_Source]]:
    items: list[WorkItem] = []
    sources: list[_Source] = []
    seen: dict[str, str] = {}
    for given in corpora:
        reader = CorpusReader.open(given)
        rows = reader.index()
        trees = Counter(classify_tree(r) for r in rows)
        if len(trees) > 1:
            raise GateDError("a corpus mixes trees; gate D takes one tree per corpus", code="migration.gate_d.mixed", exit_code=2)
        tree = next(iter(trees), "other")
        if tree in TREES and tree in seen:
            raise GateDError(
                f"two corpora classify as the {tree} tree ({seen[tree]}, {_label(Path(reader.root))})",
                code="migration.gate_d.duplicate_tree", exit_code=2,
            )  # fmt: skip
        label = _label(Path(reader.root))
        seen[tree] = label
        chosen = _select(rows, limit)
        index_sha = hashlib.sha256(reader.read_bytes("executions.jsonl")).hexdigest()
        sources.append(_Source(label, Path(reader.root), tree, len(rows), len(chosen), index_sha, reader.sealed))
        for row in chosen:
            profiles = (NATIVE_PROFILE,) if tree in TREES else tuple(sorted(row.sem_paths or row.sem or {}))
            items.append(
                WorkItem(
                    row.ex, tree, root=str(reader.root), state=reader.state, used_partial=reader.used_partial,
                    shard_depth=reader.shard_depth, row=row, adapter=row.adapter, profiles=profiles,
                )  # fmt: skip
            )
    return items, sources


def golden_items(golden_dir: Path | None) -> list[WorkItem]:
    """The 19 golden v1 AERs and 9 native AERs of ``tests/golden/test_gate_d.py``: mapped here, as that test maps them.

    ``golden_dir`` holds ``golden_index.json`` (J.2.2; default ``$AGENTPROV_GOLDEN_DIR`` or the repository fixtures); the files it
    lists are read relative to the fixtures root two levels above and checked against the indexed sha256."""
    from agentprov.adapters.runner import aer_bytes, map_artefact  # noqa: PLC0415 - golden scope only
    from agentprov.adapters.types import Origin  # noqa: PLC0415
    from agentprov.ingest.loaders import strict_json_loads  # noqa: PLC0415

    directory = Path(golden_dir) if golden_dir is not None else Path(os.environ.get(gates.ENV_GOLDEN_DIR, "").strip() or gates.DEFAULT_GOLDEN_DIR).expanduser()
    fixtures = directory.parent.parent
    try:
        index = strict_json_loads((directory / "golden_index.json").read_bytes())
    except (OSError, AgentProvError, ValueError):
        raise GateDError("golden fixtures not found or unreadable", code="migration.gate_d.golden", exit_code=3) from None
    if not isinstance(index, list):
        raise GateDError("the golden index is not a JSON list", code="migration.gate_d.golden", exit_code=3)
    by_id = {str(e.get("id")): e for e in index if isinstance(e, dict)}

    def read(entry: dict[str, Any], role: str) -> bytes:
        file = next(f for f in entry["files"] if f["role"] == role)
        try:
            data = (fixtures / file["path"]).read_bytes()
        except OSError:
            raise GateDError(f"golden fixture {entry['id']} is unreadable", code="migration.gate_d.golden", exit_code=3) from None
        if hashlib.sha256(data).hexdigest() != file["sha256"]:
            raise GateDError(f"golden fixture {entry['id']} does not match its index", code="migration.gate_d.golden", exit_code=3)
        return data

    items: list[WorkItem] = []
    for entry in index:
        if not isinstance(entry, dict) or entry.get("kind") != "v1_pair":
            continue
        source = read(entry, "v1_transcript")
        origin_info = entry.get("origin") or {}
        relpath = str(origin_info.get("corpus_relpath") or next(f["path"] for f in entry["files"] if f["role"] == "v1_transcript"))
        origin = Origin.corpus("AgentDojo-PROV", "2.3", relpath, producer_commit=BASELINE_COMMIT)
        outcome, _ = map_artefact(source, origin, profile_id="adprov-v1")
        data, _ = aer_bytes(outcome)
        tree = "converted" if origin_info.get("tree") == "converted" else "release"
        items.append(WorkItem(str(entry["id"]), tree, aer=data, raw=source, adapter="adprov.transcript_v1@0.1.0", twice=True))
        native = by_id.get(str(entry["native"])) if entry.get("native") else None
        if native is not None:
            o = native["origin"]
            raw = read(native, "native_log")
            outcome, _ = map_artefact(
                raw, Origin.git(o["repo"], o["commit"], o["path"], o["git_blob_sha1"]), profile_id="agentdojo-upstream"
            )
            data, _ = aer_bytes(outcome)
            items.append(WorkItem(str(native["id"]), "native", aer=data, raw=raw, adapter="agentdojo.tracelogger@0.1.0", twice=True))
    return items


# ----------------------------------------------------------------------------------------------------------- execution


def _chunks(items: Sequence[WorkItem], size: int) -> Iterator[Sequence[WorkItem]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def execute(
    items: Sequence[WorkItem], *, workers: int, in_process: bool, progress: Progress = NULL_PROGRESS
) -> list[dict[str, Any]]:
    """Run every item; results are in item order whatever the worker count (the determinism contract)."""
    results: list[dict[str, Any]] = []

    def done(result: dict[str, Any]) -> None:
        results.append(result)
        progress.emit(
            ProgressEvent(
                "unit_done", unit=result["item"], status="ok" if not result["codes"] else "failed",
                duration_s=result["t"]["total"], codes=tuple(result["codes"][:3]),
            )
        )  # fmt: skip

    progress.emit(ProgressEvent("start", total=len(items), fields={"command": "migrate gate-d", "workers": 0 if in_process else workers}))
    if in_process:
        for item in items:
            done(run_item(item))
        return results
    context = multiprocessing.get_context("spawn")
    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            for result in pool.map(run_item, items, chunksize=2):
                done(result)
    except BrokenProcessPool:
        raise GateDError("a gate D worker process died (out of memory?)", code="migration.gate_d.worker") from None
    return results


# ------------------------------------------------------------------------------------------------------------- report


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def _digest_listing(results: Sequence[dict[str, Any]], key: str) -> str:
    digest = hashlib.sha256()
    for r in sorted(results, key=lambda r: r["item"]):
        value = r["digests"].get(key)
        if isinstance(value, dict):
            value = "|".join(f"{ref}={d}" for ref, d in sorted(value.items()))
        digest.update(f"{value}  {r['item']}\n".encode())
    return digest.hexdigest()


def _performance(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    walls = sorted(r["t"]["total"] for r in results)
    statements = sorted(r["statements"] for r in results)
    stages: dict[str, float] = defaultdict(float)
    for r in results:
        for name, seconds in r["t"].items():
            if name != "total":
                stages[name] += seconds
    slowest = sorted(results, key=lambda r: (-r["t"]["total"], r["item"]))[:10]
    n = len(results) or 1
    return {
        "executions": len(results),
        "wall_s": {
            "sum": round(sum(walls), 3), "mean": round(sum(walls) / n, 4), "p50": round(_percentile(walls, 0.5), 4),
            "p95": round(_percentile(walls, 0.95), 4), "max": round(walls[-1] if walls else 0.0, 4),
        },
        "statements": {
            "sum": sum(statements), "mean": round(sum(statements) / n, 1), "p50": _percentile(statements, 0.5),
            "p95": _percentile(statements, 0.95), "max": statements[-1] if statements else 0,
        },
        "stage_wall_s": {k: round(v, 3) for k, v in sorted(stages.items())},
        "slowest": [{"item": r["item"], "wall_s": round(r["t"]["total"], 4), "statements": r["statements"]} for r in slowest],
    }  # fmt: skip


def _tree_details(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    subsets = Counter(r["subset"] for r in results)
    matched = [r for r in results if r["subset"] == "matched"]
    metrics: Counter[str] = Counter()
    for r in matched:
        metrics.update(r["m"])
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        for check, status in r["checks"].items():
            statuses[check][status] += 1
    stored: Counter[str] = Counter()
    for r in results:
        for kind in ("sem", "prov"):
            value = r["stored"].get(kind)
            stored[f"{kind}_{'unrecorded' if value is None else 'equal' if value else 'differs'}"] += 1
    codes = Counter(c.split(":")[0] for r in results for c in r["codes"])
    separate: dict[str, Counter[str]] = {}
    for name in ("mixtral", "outcome_only"):
        part = [r for r in results if r["subset"] == name]
        if part:
            separate[name] = Counter()
            for r in part:
                separate[name].update(r["m"])
            separate[name]["executions"] = len(part)
    return {
        "executions": len(results),
        "passed": sum(1 for r in results if not r["codes"]),
        "subsets": dict(sorted(subsets.items())),
        "metrics": dict(sorted(metrics.items())),
        "reported_separately": {k: dict(sorted(v.items())) for k, v in sorted(separate.items())},
        "check_statuses": {k: dict(sorted(v.items())) for k, v in sorted(statuses.items())},
        "rederived_vs_stored_digests": dict(sorted(stored.items())),
        "failure_codes": dict(sorted(codes.items())),
        "tier4_diagnostics": sum(r["diagnostics"] for r in results),
        "performance": _performance(results),
    }


def _pins_check(results: Sequence[dict[str, Any]], pins: Path) -> Check:
    try:
        pinned = json.loads(pins.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Check("pins.golden_digests", FAIL, "the committed pins (gate_d_digests.json) cannot be read")
    observed = {
        r["item"]: {"prov": "sha256:" + r["digests"].get("prov", ""), "sem": "sha256:" + r["digests"].get("sem", {}).get(NATIVE_PROFILE, "")}
        for r in results
    }  # fmt: skip
    changed = sorted(i for i in observed if pinned.get(i) != observed[i])
    extra = sorted(set(pinned) - set(observed))
    if changed or extra:
        return Check("pins.golden_digests", FAIL, f"changed without a version bump: {', '.join(changed[:10])}; unpinned: {', '.join(extra[:10])}")
    return Check("pins.golden_digests", PASS, f"{len(observed)} SEM and PROV digests equal the committed pins (E.9)")


def _tree_checks(tree: str, results: Sequence[dict[str, Any]], details: dict[str, Any], *, complete: bool) -> list[Check]:
    out: list[Check] = []
    for code, prefixes, text in (
        (f"d8.tiers.{tree}", ("d8.", "input."), "executions failing a D8 tier (a skipped check counts as a failure)"),
        (f"never_emit.{tree}", ("ne.",), "executions violating a J.3.5 never-emit check"),
        (f"cross_counts.per_execution.{tree}", ("xc.",), "executions whose PROV counts differ from their AER"),
        (f"errors.{tree}", ("gate_d.error",), "executions that raised"),
    ):
        bad = sum(1 for r in results if any(c.startswith(p) for c in r["codes"] for p in prefixes))
        out.append(Check(code, PASS if bad == 0 else FAIL, f"{bad} {text}"))
    skipped = sum(counts.get("skipped", 0) for counts in details["check_statuses"].values())
    out.append(Check(f"strict.skipped.{tree}", PASS if skipped == 0 else FAIL, f"{skipped} skipped checks in release mode (MP-3)"))
    if tree in ("release", "converted", "native") and complete:
        column = "release" if tree == "release" else "converted"
        metrics = details["metrics"]
        for inv in CROSS_COUNTS:
            expected = getattr(inv, column)
            observed = int(metrics.get(inv.metric, 0))
            out.append(Check(f"crosscount.{tree}.{inv.name}", PASS if observed == expected else FAIL, f"{observed} observed, {expected} in J.3.5"))
        observed, derived = int(metrics.get("env_load_activities", 0)), int(metrics.get("env_load_expected", 0))
        out.append(Check(f"crosscount.{tree}.environment_load_activities", PASS if observed == derived else FAIL,
                         f"{observed} observed, {derived} derived (one per TraceLogger execution with injection payload "
                         "fixtures; regeneration-batch item 5)"))
    return out


def gate_d_validate(
    cfg: gates.MigrationConfig,
    *,
    scope: str,
    corpora: Sequence[Path] = (),
    limit: int | None = None,
    accept_gaps: Sequence[str] = (),
    golden_dir: Path | None = None,
    pins: Path | None = None,
    report_path: Path | None = None,
    progress: Progress = NULL_PROGRESS,
    clock: Callable[[], datetime] | None = None,
) -> GateDResult:
    """Gate D (J.3.5). ``scope`` is ``golden`` or ``full``; ``full`` with ``limit`` is reported as scope ``sample``."""
    now = clock or (lambda: datetime.now(UTC))
    started = now()
    t0 = time.perf_counter()
    golden_scope = scope == "golden"
    if not golden_scope and not corpora:
        raise GateDError("gate D at full scope needs --corpus DIR for each tree", code="migration.gate_d.usage", exit_code=2)
    if report_path is not None:
        _refuse_inside(report_path, corpora)
    sources: list[_Source] = []
    if golden_scope:
        items = golden_items(golden_dir or cfg.golden_dir)
    else:
        items, sources = corpus_items([Path(c) for c in corpora], limit)
    if not items:
        raise GateDError("no executions to check", code="migration.gate_d.empty", exit_code=3)
    sample = not golden_scope and limit is not None
    report_scope = "golden" if golden_scope else "sample" if sample else "full"

    # 0 = the host default (min(CPUs, 0.75 RAM / the per-worker cap), as --workers 0 says); was min(8, CPUs)
    workers = cfg.workers if cfg.workers > 0 else resolve_worker_count(0)
    results = execute(items, workers=workers, in_process=cfg.in_process, progress=progress)

    checks: list[Check] = []
    notes: list[str] = []
    details_trees: dict[str, Any] = {}
    by_tree: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_tree[r["tree"]].append(r)
    for tree in sorted(by_tree):
        rs = by_tree[tree]
        details_trees[tree] = _tree_details(rs)
        complete = report_scope == "full" and tree in EXPECTED_EXECUTIONS and len(rs) == EXPECTED_EXECUTIONS[tree]
        checks += _tree_checks(tree, rs, details_trees[tree], complete=complete)
        if report_scope == "full" and tree in EXPECTED_EXECUTIONS:
            ok = len(rs) == EXPECTED_EXECUTIONS[tree]
            checks.append(Check(f"inputs.{tree}.complete", PASS if ok else FAIL, f"{len(rs)} executions, {EXPECTED_EXECUTIONS[tree]} expected (J.3.5)"))
    gaps: list[str] = []
    if report_scope == "full":
        for tree in TREES:
            if tree in by_tree:
                continue
            if tree in accept_gaps:
                gaps.append(tree)
                checks.append(Check(f"inputs.{tree}.present", PASS, "accepted gap: no stored AERs of this tree were given (--accept-gap)"))
                notes.append(f"accepted gap: the {tree} tree is not covered ({EXPECTED_EXECUTIONS[tree]} executions); J.3.5 asks for it")
            else:
                checks.append(Check(f"inputs.{tree}.present", FAIL, f"no corpus classified as the {tree} tree was given (J.3.5 inputs)"))
        # An accepted gap passes (D-49), but a full report that validated none of the trees cannot stand for J.3.5.
        validated = [t for t in TREES if t in by_tree]
        checks.append(Check(
            "inputs.migration_trees.present", PASS if validated else FAIL,
            f"J.3.5 trees validated: {', '.join(validated)}" if validated else "no J.3.5 tree was validated; every one is an accepted gap or absent",
        ))  # fmt: skip
    elif sample:
        notes.append("sample scope: a subset of each corpus; completeness, the J.3.5 table and the order of AD-07 are not evaluated")
    if golden_scope:
        twice = sum(1 for r in results if any(c.startswith("determinism.") for c in r["codes"]))
        checks.append(Check("determinism.twice", PASS if twice == 0 else FAIL, f"{twice} golden executions with differing SEM or PROV bytes across two derivations"))
        checks.append(_pins_check(results, pins or DEFAULT_PINS))
        r08 = next((r for r in results if r["item"] == "R08"), None)
        if r08 is not None:
            done = not any(c.startswith("gate_d.error") for c in r08["codes"])
            checks.append(Check("performance.r08_completes", PASS if done else FAIL, f"R08: {r08['t']['total']:.2f}s, {r08['statements']} statements"))
    elif report_scope == "full":
        notes.append("full scope: the AER, SEM and PROV digest listings are recorded in outputs so that two runs can be compared (J.3.0)")
    notes.append("gate D re-derives from stored AERs in worker processes (no T1 isolation grade); nothing is written into a corpus")

    failed = [r for r in results if r["codes"]]
    trace_failures = tuple(
        {"item": r["item"], "check": r["codes"][0].split(":")[0], "detail": "; ".join(r["codes"])[:300]}
        for r in failed[:LISTED_FAILURES]
    )
    outputs: list[dict[str, Any]] = []
    for tree in sorted(by_tree):
        for key in ("aer", "sem", "prov"):
            outputs.append({"name": f"{key}_digest_listing", "tree": tree, "files": len(by_tree[tree]), "sha256": _digest_listing(by_tree[tree], key)})
    rows = [_row(r) for r in sorted(results, key=lambda r: (r["tree"], r["item"]))]
    inputs = (
        [{"name": s.label, "tree": s.tree, "files": s.total, "selected": s.selected, "sealed": s.sealed, "index_sha256": s.index_sha256} for s in sources]
        if sources else [{"name": "golden", "files": len(items)}]
    )  # fmt: skip
    ended = now()
    report = GateReport(
        gate="D",
        scope=report_scope,
        role="diagnostic" if sample else "release",
        agentprov=gates._agentprov_identity(),
        baseline_lock_sha256=lock_sha256(cfg.lock_path),
        specs=gates._specs(),
        environment=gates._environment(interpreter_advisory()),
        inputs=tuple(inputs),
        params={"workers": 0 if cfg.in_process else workers, "seed": DEFAULT_SEED, "strict": cfg.strict, "limit": limit, "accept_gaps": sorted(accept_gaps), "profile": NATIVE_PROFILE},
        checks=tuple(checks),
        outputs=tuple(outputs),
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
        wall_s=round(time.perf_counter() - t0, 3),
        notes=tuple(notes),
        trace_counts={"expected": len(items), "checked": len(results), "passed": len(results) - len(failed), "failed": len(failed), "skipped": 0},
        trace_failures=trace_failures,
        details={
            "trees": details_trees,
            "gaps": gaps,
            "table": {"source": "J.3.5", "columns": {"release": {i.name: i.release for i in CROSS_COUNTS}, "converted": {i.name: i.converted for i in CROSS_COUNTS}}},
            "isolation": {"mode": "in-process" if cfg.in_process else "process-pool", "grade": None},
            "performance": _performance(results),
        },
    )  # fmt: skip
    return GateDResult(report, rows)


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "item": r["item"], "tree": r["tree"], "subset": r["subset"], "unit": r["unit"], "ok": not r["codes"], "codes": r["codes"],
        "wall_s": round(r["t"]["total"], 4), "statements": r["statements"],
        "aer": r["digests"].get("aer"), "sem": r["digests"].get("sem"), "prov": r["digests"].get("prov"),
        "stored_equal": r["stored"],
    }  # fmt: skip


def _refuse_inside(report_path: Path, corpora: Sequence[Path]) -> None:
    """A report is never written into a corpus (N.1.5: a consumer never writes there)."""
    target = Path(os.path.realpath(report_path))
    for given in corpora:
        try:
            location = resolve_corpus(given)
        except AgentProvError:
            continue
        for root in {Path(os.path.realpath(location.root)), Path(os.path.realpath(location.final))}:
            if target == root or root in target.parents:
                raise GateDError("the report path is inside a corpus; gate D never writes into a corpus", code="migration.gate_d.inside_corpus", exit_code=4)


# ------------------------------------------------------------------------------------------------------------- outputs


def markdown(report: GateReport) -> str:
    """A short markdown rendering of the report (verdict, counts, the J.3.5 table per tree, performance, failures)."""
    counts = report.counts
    d = report.details
    lines = [
        f"# Gate D ({report.scope}, {'release' if report.params.get('strict') else 'dev'} mode): {report.verdict}",
        "",
        f"- commit `{report.agentprov.get('commit')}`, started {report.started_at}, {report.wall_s:.1f} s, "
        f"{report.params.get('workers')} workers",
        f"- executions {counts['checked']}/{counts['expected']} checked, {counts['passed']} passed, {counts['failed']} failed",
        f"- profile `{report.params.get('profile')}`; every D8 tier in release mode, a skipped check is a failure (MP-3)",
    ]
    if d.get("gaps"):
        lines.append(f"- **accepted gaps:** {', '.join(d['gaps'])}")
    for tree, info in d.get("trees", {}).items():
        perf = info["performance"]
        lines += ["", f"## {tree}: {info['passed']}/{info['executions']} passed", ""]
        lines.append(f"wall per execution: mean {perf['wall_s']['mean']} s, p95 {perf['wall_s']['p95']} s, max {perf['wall_s']['max']} s; "
                     f"statements: mean {perf['statements']['mean']}, max {perf['statements']['max']}")
        column = "release" if tree == "release" else "converted"
        if report.scope == "full" and tree in EXPECTED_EXECUTIONS:
            lines += ["", "| invariant | observed | J.3.5 | result |", "|---|---|---|---|"]
            for inv in CROSS_COUNTS:
                observed = info["metrics"].get(inv.metric, 0)
                expected = getattr(inv, column)
                lines.append(f"| {inv.name} | {observed} | {expected} | {'ok' if observed == expected else 'FAIL'} |")
            observed, derived = info["metrics"].get("env_load_activities", 0), info["metrics"].get("env_load_expected", 0)
            lines.append(f"| environment_load_activities (item 5) | {observed} | {derived} derived | {'ok' if observed == derived else 'FAIL'} |")
        for name, part in info["reported_separately"].items():
            lines.append(f"\nreported separately ({name}): {part.get('executions', 0)} executions")
    failed = [c for c in report.checks if c.status == FAIL]
    if failed or report.failures:
        lines += ["", "## Failures", ""]
        lines += [f"- `{c.check}`: {c.detail}" for c in failed[:20]]
        lines += [f"- `{f['item']}`: {f['check']}" for f in report.failures[:20]]
    lines += [""]
    return "\n".join(lines)


def write_outputs(result: GateDResult, report_path: Path) -> list[Path]:
    """Write ``<stem>.json`` (the report), ``<stem>.md`` and ``<stem>.executions.jsonl`` beside ``report_path``."""
    target = Path(report_path)
    stem = target.name[: -len(".json")] if target.name.endswith(".json") else target.name
    rows = target.with_name(stem + ".executions.jsonl")
    text = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in result.rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(rows, text)
    listing = {"name": "executions_jsonl", "files": len(result.rows), "sha256": hashlib.sha256(text.encode()).hexdigest()}
    report = replace(result.report, outputs=(*result.report.outputs, listing))
    result.report = report
    written = gates.write_report(report, path=target)
    atomic_write_text(target.with_name(stem + ".md"), gates._redacted(markdown(report)))
    return [written, target.with_name(stem + ".md"), rows]
