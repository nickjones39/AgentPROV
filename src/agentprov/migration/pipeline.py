"""The v1 -> AER pipeline behind gates A and B (docs/architecture J.3.2, J.3.3; K.7.1, K.7.2).

For every ``transcript/v1`` file with bytes ``B`` (and, for gate B, stored graph bytes ``G``)::

    A  = map(RawArtefact(B, origin), profile adprov-v1)             # in a T1 ``map`` worker, sealed by the parent (T0)
    A1: jcs(render(A)) == jcs(strict_json_loads(B))                 # JCS bytes: value identity
    A2: serialise(render(A)) == B                                   # bytes: byte identity
    B1: compat.serialise(compat.build(render(A))) == G              # the oracle on the view
    B2: compat.serialise(compat.build(strict_json_loads(B))) == G   # the oracle on the source (isolates port faults)

Every comparison is between byte strings; nothing compares decoded values with ``==`` (MP-2). ``render`` runs on an AER
read back from the sealed file, so it reads nothing from raw (AD-02). Each produced AER must also pass the release-mode
validator with its locators resolved against the digest-checked artefact, and must not be degenerate.

Mapping runs in the T1 worker pool (``agentprov.io.workers``; ``job_map``); batches are mapped on a background thread while
the parent seals, renders and compares the previous batch. Items are processed in sorted order, so every output (counts,
listings, rows) is independent of the worker count and of completion order (C.11.7).

Inputs are either the golden set (J.2.2; CI scope) or the two baseline trees (J.1.4; full scope, local only). Reports and
rows carry paths relative to a tree root, sha256 values and counts, never transcript text. Failures print codes, offsets
and sha256 values only: the files are third-party model output with prompt-injection payloads.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import seal_job_result
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.errors import AgentProvError
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes
from agentprov.io.workers import Job, JobResult, WorkerPool
from agentprov.migration.lock import PREDICATES, _regular_files
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent
from agentprov.raw.store import RawObjectStore
from agentprov.views.transcript_v1 import render, serialise

PROFILE_ID: Final = "adprov-v1"
BASELINE_COMMIT: Final = "579a908354b93361efe0905ffb7623256aa96a06"  # J.1.1: the frozen AgentDojo-PROV commit
BATCH: Final = 200
CHECKS: Final = ("A1", "A2", "B1", "B2")


@dataclass(frozen=True, slots=True)
class PairInput:
    """One v1 transcript with its stored graph. ``item`` is the label every report uses (never an absolute path)."""

    item: str
    tree: str  # "release" | "converted"
    transcript: Path
    graph: Path | None
    origin_relpath: str  # the corpus-relative path recorded in the artefact origin (determines the execution id)
    tree_relpath: str = ""  # path relative to the tree root (the listing key of J.1.4)
    graph_relpath: str = ""
    expect_sha256: str | None = None  # golden: the indexed digest (full hex, or a prefix)


@dataclass(slots=True)
class TraceRow:
    """The outcome for one transcript. ``a1``..``b2`` are ``None`` when that check was not requested."""

    item: str
    tree: str
    sha256: str
    n_bytes: int
    graph_sha256: str | None = None
    codes: list[str] = field(default_factory=list)
    a1: bool | None = None
    a2: bool | None = None
    b1: bool | None = None
    b2: bool | None = None
    aer_valid: bool | None = None
    degenerate: bool = False
    accounting: str | None = None  # consistent | inconsistent | unverifiable (the sealed fold)
    accounting_checks: list[dict[str, Any]] = field(default_factory=list)  # non-consistent checks only
    n_records: int = 0
    execution_digest: str | None = None
    aer_file_sha256: str | None = None
    produced_graph_sha256: str | None = None

    @property
    def passed(self) -> bool:
        return not self.codes

    def to_json(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "item": self.item,
            "tree": self.tree,
            "sha256": self.sha256,
            "bytes": self.n_bytes,
            "passed": self.passed,
            "codes": self.codes,
            "accounting": self.accounting,
            "aer_valid": self.aer_valid,
            "degenerate": self.degenerate,
            "n_records": self.n_records,
            "execution_digest": self.execution_digest,
            "aer_file_sha256": self.aer_file_sha256,
        }
        for name in ("a1", "a2", "b1", "b2"):
            if getattr(self, name) is not None:
                row[name] = getattr(self, name)
        if self.graph_sha256 is not None:
            row["graph_sha256"] = self.graph_sha256
        if self.accounting_checks:
            row["accounting_checks"] = self.accounting_checks
        return row


@dataclass(slots=True)
class TreeSummary:
    """Per-tree inputs: file counts and the J.1.4 listing digests of what was read."""

    tree: str
    transcripts: int = 0
    transcript_listing_sha256: str | None = None
    graphs: int = 0
    graph_listing_sha256: str | None = None
    unpaired_transcripts: list[str] = field(default_factory=list)
    unpaired_graphs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineRun:
    """Everything one pass produces."""

    rows: list[TraceRow]
    trees: dict[str, TreeSummary]
    aer_listing_sha256: dict[str, str]  # per tree: sha256 of "<aer file sha256>  <item>\n" lines in item order
    graph_listing_sha256: dict[str, str]  # per tree: the same over the compat graphs produced by B1
    wall_s: float = 0.0
    isolation: dict[str, Any] = field(default_factory=dict)


class PipelineError(AgentProvError):
    """The inputs cannot be enumerated or read (environment problem, exit 3)."""

    code = "migration.pipeline.inputs"
    exit_code = 3


# ------------------------------------------------------------------------------------------------ inputs


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def full_inputs(baseline_repo: Path) -> tuple[list[PairInput], dict[str, TreeSummary]]:
    """The transcript/graph pairs of the two baseline trees (J.1.4), sorted by tree then relative path.

    ``baseline_repo`` is the old repository root (``AGENTPROV_BASELINE_CORPUS``). A transcript pairs with the graph of the
    same stem (``<stem>.transcript.json`` -> ``<stem>.json``); a transcript without a graph and a graph without a
    transcript are recorded in the tree summary (the pairing check of the gate).
    """
    pairs: list[PairInput] = []
    trees: dict[str, TreeSummary] = {}
    for tree, directory in (("release", "corpus-prov"), ("converted", "corpus-og-agentdojo-runs-prov")):
        root = baseline_repo / "corpus" / directory
        if not root.is_dir():
            raise PipelineError(f"the baseline has no corpus/{directory} directory")
        files = sorted(rel for rel, _ in _regular_files(root))
        transcripts = [rel for rel in files if PREDICATES["transcript"](rel)]
        graphs = {rel for rel in files if PREDICATES["graph"](rel)}
        summary = TreeSummary(tree, transcripts=len(transcripts), graphs=len(graphs))
        paired: set[str] = set()
        for rel in transcripts:
            graph_rel = rel[: -len(".transcript.json")] + ".json"
            graph: Path | None = None
            if graph_rel in graphs:
                paired.add(graph_rel)
                graph = root / graph_rel
            else:
                summary.unpaired_transcripts.append(rel)
            pairs.append(
                PairInput(f"{directory}/{rel}", tree, root / rel, graph, f"{directory}/{rel}", rel, graph_rel if graph else "")
            )
        summary.unpaired_graphs = sorted(graphs - paired)
        trees[tree] = summary
    return pairs, trees


def golden_inputs(golden_dir: Path) -> tuple[list[PairInput], dict[str, TreeSummary]]:
    """The golden pairs of ``golden_index.json`` (J.2.2), in id order R01..R10, C01..C09.

    The index is a JSON list; each ``v1_pair`` entry has ``files[]`` with ``role``, ``path`` (relative to the fixtures
    root, two levels above ``golden_dir``), ``sha256`` and ``bytes``. ``origin.corpus_relpath`` fixes the execution id.
    """
    index = golden_dir / "golden_index.json"
    try:
        data = strict_json_loads(index.read_bytes())
    except (OSError, AgentProvError, ValueError) as exc:
        raise PipelineError(f"the golden index cannot be read ({type(exc).__name__})") from None
    if not isinstance(data, list):
        raise PipelineError("the golden index is not a JSON list")
    fixtures = golden_dir.parent.parent
    pairs: list[PairInput] = []
    for entry in data:
        if not isinstance(entry, dict) or entry.get("kind") != "v1_pair":
            continue
        files = {f["role"]: f for f in entry["files"]}
        transcript, graph = files["v1_transcript"], files["compat_graph"]
        origin = entry.get("origin", {})
        relpath = str(origin.get("corpus_relpath") or transcript["path"])
        tree = "converted" if origin.get("tree") == "converted" else "release"
        pairs.append(
            PairInput(
                str(entry["id"]), tree, fixtures / transcript["path"], fixtures / graph["path"], relpath,
                expect_sha256=str(transcript["sha256"]),
            )
        )
    pairs.sort(key=lambda p: (0 if p.item.startswith("R") else 1, int(p.item.lstrip("RC"))))
    trees: dict[str, TreeSummary] = {}
    for pair in pairs:
        summary = trees.setdefault(pair.tree, TreeSummary(pair.tree))
        summary.transcripts += 1
        summary.graphs += 1
    return pairs, trees


def _read(path: Path) -> bytes:
    try:
        with open(path, "rb") as stream:
            return stream.read()
    except OSError as exc:
        raise PipelineError(f"cannot read an input file ({type(exc).__name__})") from None


# ------------------------------------------------------------------------------------------------ evaluation


class _BytesStore:
    """The raw store of one artefact for the validator's locator checks (the ``RawStore`` protocol)."""

    def __init__(self, raw: bytes) -> None:
        self.sha, self.raw = _sha256(raw), raw

    def has(self, sha256: str) -> bool:
        return sha256 == self.sha

    def size(self, sha256: str) -> int:
        return len(self.raw)

    def read_bytes(self, sha256: str) -> bytes:
        return self.raw


def _non_consistent(info_checks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for check in info_checks:
        if check.get("verdict") != "consistent":
            item = {"id": check["id"], "scope": check["scope"], "verdict": check["verdict"]}
            if "reason" in check:
                item["reason"] = check["reason"]
            if isinstance(check.get("observed"), dict):
                item["observed"] = dict(check["observed"])  # counts only
            out.append(item)
    return out


def evaluate_trace(
    pair: PairInput,
    raw: bytes,
    result: JobResult,
    want: frozenset[str],
    *,
    graph: bytes | None,
    tmp: Path,
    registry: RuleRegistry,
    profile_digest: dict[tuple[str, int], str],
    compat: Any,
    hook: Callable[[PairInput, Any, Any], None] | None = None,
) -> TraceRow:
    """Seal the worker's frames, validate the AER, run the requested checks. Never raises for a trace's content."""
    row = TraceRow(pair.item, pair.tree, _sha256(raw), len(raw))
    if pair.expect_sha256 is not None and not row.sha256.startswith(pair.expect_sha256):
        row.codes.append("input.digest_mismatch")
    if not result.ok:
        row.codes.append(f"map.job_failed:{getattr(result.error, 'code', 'unknown')}")
        _mark_all(row, want)
        return row
    frames = result.json
    seal: dict[str, Any] = next((dict(f["seal"]) for f in frames if "seal" in f), {})
    row.degenerate = bool(seal.get("degenerate"))
    path = tmp / f"{_sha256(pair.item.encode())[:24]}.aer.jsonl"
    try:
        info = seal_job_result(frames, path, registry=registry)
    except AgentProvError as exc:
        row.codes.append(f"aer.seal_failed:{exc.code}")
        _mark_all(row, want)
        return row
    try:
        row.accounting = info.accounting.status
        row.accounting_checks = _non_consistent(info.accounting.checks)
        row.n_records = info.n_records
        row.execution_digest = info.execution_digest
        row.aer_file_sha256 = info.file_sha256
        if row.degenerate:
            row.codes.append("aer.degenerate")
        row.aer_valid = _validate(path, raw, registry, profile_digest)
        if not row.aer_valid:
            row.codes.append("aer.invalid")
        try:
            document = load_aer(path)
        except AgentProvError as exc:
            row.codes.append(f"aer.read_failed:{exc.code}")
            _mark_all(row, want)
            return row
        if want & {"A1", "A2"}:
            _check_a(row, raw, document, want)
        if want & {"B1", "B2"}:
            _check_b(row, raw, graph, document, want, compat)
        if hook is not None:
            hook(pair, document, info)
    finally:
        path.unlink(missing_ok=True)
    return row


def _mark_all(row: TraceRow, want: frozenset[str]) -> None:
    for name in want:
        setattr(row, name.lower(), False)


def _validate(path: Path, raw: bytes, registry: RuleRegistry, profile_digest: dict[tuple[str, int], str]) -> bool:
    validator = AerValidator(store=_BytesStore(raw), catalogues=registry, mode="release", profile_digests=profile_digest)
    with open(path, "rb") as stream:
        for line in stream:
            validator.feed(line)
    report = validator.finish()
    return bool(report.ok and report.passed and not report.skipped)


def _check_a(row: TraceRow, raw: bytes, document: Any, want: frozenset[str]) -> None:
    try:
        rendered = render(document)
        expected = jcs_bytes(strict_json_loads(raw))
        produced = jcs_bytes(rendered)
        view_bytes = serialise(rendered)
    except Exception as exc:  # noqa: BLE001 - a view or loader fault fails the trace, with the exception type only
        row.codes.append(f"view.error:{type(exc).__name__}")
        row.a1 = row.a2 = False
        return
    if "A1" in want:
        row.a1 = produced == expected
        if not row.a1:
            row.codes.append("A1.jcs_mismatch")
    if "A2" in want:
        row.a2 = view_bytes == raw
        if not row.a2:
            row.codes.append("A2.byte_mismatch")


def _check_b(row: TraceRow, raw: bytes, graph: bytes | None, document: Any, want: frozenset[str], compat: Any) -> None:
    if graph is None:
        row.codes.append("B.graph_missing")
        row.b1 = row.b2 = False
        return
    row.graph_sha256 = _sha256(graph)
    if "B1" in want:
        try:
            produced = compat.SPEC.serialise(compat.SPEC.build(render(document)))
        except Exception as exc:  # noqa: BLE001
            row.codes.append(f"B1.error:{type(exc).__name__}")
            row.b1 = False
        else:
            row.produced_graph_sha256 = _sha256(produced)
            row.b1 = produced == graph
            if not row.b1:
                row.codes.append("B1.graph_mismatch")
    if "B2" in want:
        try:
            produced = compat.SPEC.serialise(compat.SPEC.build(strict_json_loads(raw)))
        except Exception as exc:  # noqa: BLE001
            row.codes.append(f"B2.error:{type(exc).__name__}")
            row.b2 = False
        else:
            row.b2 = produced == graph
            if not row.b2:
                row.codes.append("B2.graph_mismatch")


# ------------------------------------------------------------------------------------------------ the run


def _listing(entries: list[tuple[str, str]]) -> str:
    """The J.1.4 tree listing digest: ``"<sha256>  <relpath>\\n"`` lines in code-point order of the path."""
    return _sha256("".join(f"{digest}  {rel}\n" for rel, digest in sorted(entries)).encode("utf-8"))


def run_pipeline(
    pairs: Sequence[PairInput],
    trees: dict[str, TreeSummary],
    want: frozenset[str],
    *,
    work: Path | None,
    workers: int,
    release: bool = False,
    in_process: bool = False,
    progress: Progress = NULL_PROGRESS,
    hook: Callable[[PairInput, Any, Any], None] | None = None,
) -> PipelineRun:
    """Map every pair in T1 workers, then seal and check in the parent, in item order. ``want`` is a subset of CHECKS."""
    if not want <= frozenset(CHECKS):
        raise ValueError(f"unknown checks {sorted(want - frozenset(CHECKS))}")
    need_graph = bool(want & {"B1", "B2"})
    compat: Any = None
    if need_graph:
        from agentprov.prov.compat import adprov_v2_3 as compat  # noqa: PLC0415 - quarantined oracle, migration only
    started = time.perf_counter()
    registry = RuleRegistry.default()
    profile = load_profile(PROFILE_ID)
    profile_digest = {(profile.id, profile.version): profile.sha256}
    with tempfile.TemporaryDirectory(prefix="agentprov-gate-") as scratch:
        base = Path(work) if work is not None else Path(scratch)
        store = RawObjectStore(base / "raw")
        tmp = base / "aer-tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        pool = WorkerPool(workers=workers, store_root=store.objects_dir, release=release, in_process=in_process)
        isolation = pool.isolation
        rows: list[TraceRow] = []
        listing_aer: dict[str, list[str]] = {t: [] for t in trees}
        listing_graph: dict[str, list[str]] = {t: [] for t in trees}
        transcript_digests: dict[str, list[tuple[str, str]]] = {t: [] for t in trees}
        graph_digests: dict[str, list[tuple[str, str]]] = {t: [] for t in trees}
        progress.emit(
            ProgressEvent(
                "start", total=len(pairs),
                fields={"command": "migrate", "plan": "map in T1 workers, seal, render, compare", "workers": pool.workers},
            )
        )

        def submit(batch: Sequence[PairInput]) -> tuple[Sequence[PairInput], dict[str, bytes], list[JobResult]]:
            jobs: list[Job] = []
            data: dict[str, bytes] = {}
            for pair in batch:
                raw = _read(pair.transcript)
                data[pair.item] = raw
                put = store.put(raw, ext="json")
                origin = Origin.corpus("AgentDojo-PROV", "2.3", pair.origin_relpath, producer_commit=BASELINE_COMMIT)
                jobs.append(
                    Job(
                        key=pair.item, kind="map", inputs=({"sha256": put.sha256, "role": "primary"},),
                        params={"profile": PROFILE_ID, "origin": origin.to_json()},
                    )
                )
            return batch, data, pool.run(jobs)

        batches = [pairs[i : i + BATCH] for i in range(0, len(pairs), BATCH)]
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="gate-map") as mapper:
            futures: dict[int, Future[Any]] = {}
            if batches:
                futures[0] = mapper.submit(submit, batches[0])
            for number in range(len(batches)):
                if number + 1 < len(batches):
                    futures[number + 1] = mapper.submit(submit, batches[number + 1])
                batch, data, results = futures.pop(number).result()
                by_key = {r.key: r for r in results}
                for pair in batch:
                    t0 = time.perf_counter()
                    raw = data[pair.item]
                    graph = _read(pair.graph) if need_graph and pair.graph is not None else None
                    row = evaluate_trace(
                        pair, raw, by_key[pair.item], want, graph=graph, tmp=tmp, registry=registry,
                        profile_digest=profile_digest, compat=compat, hook=hook,
                    )
                    by_key[pair.item].close()
                    rows.append(row)
                    transcript_digests[pair.tree].append((pair.tree_relpath or pair.item, row.sha256))
                    if row.aer_file_sha256 is not None:
                        listing_aer[pair.tree].append(f"{row.aer_file_sha256}  {pair.item}\n")
                    if row.graph_sha256 is not None:
                        graph_digests[pair.tree].append((pair.graph_relpath or pair.item, row.graph_sha256))
                    if row.produced_graph_sha256 is not None:
                        listing_graph[pair.tree].append(f"{row.produced_graph_sha256}  {pair.item}\n")
                    progress.emit(
                        ProgressEvent(
                            "unit_done", unit=pair.item, status="passed" if row.passed else "failed",
                            duration_s=time.perf_counter() - t0, codes=tuple(row.codes[:4]),
                        )
                    )
    for tree, summary in trees.items():
        if summary.transcripts and len(transcript_digests[tree]) == summary.transcripts:
            summary.transcript_listing_sha256 = _listing(transcript_digests[tree])
        if graph_digests[tree] and len(graph_digests[tree]) == summary.graphs:
            summary.graph_listing_sha256 = _listing(graph_digests[tree])
    return PipelineRun(
        rows=rows,
        trees=trees,
        aer_listing_sha256={t: _sha256("".join(lines).encode()) for t, lines in listing_aer.items()},
        graph_listing_sha256={t: _sha256("".join(lines).encode()) for t, lines in listing_graph.items() if lines},
        wall_s=round(time.perf_counter() - started, 3),
        isolation=isolation,
    )


# ------------------------------------------------------------------------------------------------ summaries


def accounting_summary(rows: Sequence[TraceRow], *, listed: int = 1000) -> dict[str, Any]:
    """Per-tree seal accounting verdicts, and the non-consistent traces counted by ``<verdict>:<check id>:<reason>``.

    Each trace counts once per distinct ``(verdict, check id, reason)`` it carries. Every ``inconsistent`` trace is listed
    (up to ``listed``) with its reason keys and the check's observed counts; ``unverifiable`` traces are counted by reason
    only (an unverifiable verdict is a property of the source, not a defect). Labels are relative paths, never content.
    """
    by_tree: dict[str, Counter[str]] = {}
    by_reason: dict[str, Counter[str]] = {}
    inconsistent: list[dict[str, Any]] = []
    total = {"inconsistent": 0, "unverifiable": 0}
    for row in rows:
        by_tree.setdefault(row.tree, Counter())[row.accounting or "none"] += 1
        keys = sorted({f"{c['verdict']}:{c['id']}:{c.get('reason', '-')}" for c in row.accounting_checks})
        for key in keys:
            by_reason.setdefault(row.tree, Counter())[key] += 1
        if row.accounting in total:
            total[row.accounting] += 1
        if row.accounting == "inconsistent" and len(inconsistent) < listed:
            observed = [c.get("observed", {}) for c in row.accounting_checks if c["verdict"] == "inconsistent"]
            inconsistent.append({"item": row.item, "reasons": keys, "observed": observed})
    return {
        "by_tree": {t: dict(sorted(c.items())) for t, c in sorted(by_tree.items())},
        "by_reason": {t: dict(sorted(c.items())) for t, c in sorted(by_reason.items())},
        "traces_by_status": total,
        "inconsistent_listed": inconsistent,
        "inconsistent_listed_cap": listed,
    }


def tree_counts(rows: Sequence[TraceRow], checks: Sequence[str]) -> dict[str, dict[str, int]]:
    """``{tree: {"traces": n, "passed": n, "failed": n, "A1": passed, ...}}`` over the requested checks."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        c = out.setdefault(row.tree, {"traces": 0, "passed": 0, "failed": 0, **dict.fromkeys(checks, 0)})
        c["traces"] += 1
        c["passed" if row.passed else "failed"] += 1
        for name in checks:
            if getattr(row, name.lower()) is True:
                c[name] += 1
    return out


def default_work_dir() -> Path:
    """``$AGENTPROV_HOME/migration-work`` (J.2.6: a gitignored work directory outside the repository)."""
    raw = os.environ.get("AGENTPROV_HOME")
    return (Path(raw) if raw else Path.home() / ".agentprov") / "migration-work"


__all__ = [
    "BASELINE_COMMIT",
    "CHECKS",
    "PairInput",
    "PipelineError",
    "PipelineRun",
    "TraceRow",
    "TreeSummary",
    "accounting_summary",
    "default_work_dir",
    "evaluate_trace",
    "full_inputs",
    "golden_inputs",
    "run_pipeline",
    "tree_counts",
]
