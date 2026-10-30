"""``validate --corpus``: the validation tiers re-run over a corpus's **stored** outputs (MN N.2.5; D8; DECISIONS D-40).

Read-only: :func:`validate_corpus` reads the stored AER, SEM and PROV files of every execution (or of a seeded sample)
through :class:`~agentprov.corpus.reader.CorpusReader` and runs the validators over them; it derives nothing and writes
nothing. The caller writes the report outside the corpus or to stdout.

Tiers (N.2.5; D8):

* ``aer`` (tier 2): :class:`agentprov.aer.validate.AerValidator` over the AER bytes, with the corpus raw store (read-only,
  objects re-hashed on read) for the locator and artefact checks, the package catalogues and the source profile digest;
  the row member ``aer`` and the check ``aer.validator``, as the importer and ``derive`` record them;
* ``sem`` (tier 3): :func:`agentprov.sem.validate.validate_sem_document` of each stored SEM document against its AER and
  the package profile at the recorded version (checks ``<profile>@<n>:<id>``);
* ``prov`` and ``linkage`` (tier 4): :func:`agentprov.validate.validate_prov` of the stored ``agentprov-prov/0.1`` file;
  the evidence-linkage checks (``pv.linkage.*``) form the ``linkage`` tier, every other tier-4 check the ``prov`` tier.

Each execution gets a row of the ``validation/results.jsonl`` shape. With every default tier and the corpus's own
validation mode, the row is the one ``derive`` would write, and its JCS digest is compared with the index's
``digests.validation`` (``reproduced`` / ``differs``; a difference with equal validator versions is a failure, with other
versions a notice). The summary is :func:`agentprov.corpus.writer.validation_summary` and the corpus-level result the
D-40 ``ValidationSummary`` (:func:`agentprov.corpus.manifest.validation_summary`): per-tier results and
``linkage_resolved_pct`` (claim ``c1-linkage``).

The tier-3 and tier-4 row parts are re-implemented here from ``adapters/runner/provjob.py`` (``tier3_checks``,
``tier4_row``; L6, which ``corpus/`` may not import); a test pins them equal.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.corpus.authority import DRIFT, DRIFT_DETAIL, catalogue_drift
from agentprov.corpus.index import IndexRow
from agentprov.corpus.manifest import CORPUS_FORMATS, LINKAGE_PREFIX, validation_summary
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.stages import stage_map
from agentprov.corpus.verify import sample_executions
from agentprov.corpus.writer import validation_summary as results_summary
from agentprov.errors import AgentProvError
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.io.workers import KIND_RSS_BYTES, Job, JobResult, WorkerLimits, WorkerPool, prov_charge
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent
from agentprov.raw.store import RawObjectStore
from agentprov.sem.types import SemDocument

__all__ = ["DEFAULT_TIERS", "REPORT_FORMAT", "TIERS", "WORKER_CHECK", "CorpusValidation", "default_semantics_profile",
           "tier3_checks", "tier4_row", "validate_corpus", "validate_documents"]

TIERS: Final = ("aer", "sem", "prov", "linkage")
DEFAULT_TIERS: Final = TIERS
SPEC: Final = "agentprov-prov/0.1"
REPORT_FORMAT: Final = "agentprov-validation-report/0.1"


def tier4_row(report: Any, *, strict: bool) -> dict[str, Any]:
    """The tier-4 part of a results row (equal to ``adapters.runner.provjob.tier4_row``; pinned by a test)."""
    checks = {o.id: o.status for o in report.outcomes}
    passed = report.passed if strict else report.ok
    return {"checks": dict(sorted(checks.items())), "verdict": "pass" if passed else "fail",
            "versions": dict(sorted(report.versions.items()))}


def tier3_checks(report: Any, profile: str) -> dict[str, str]:
    """The tier-3 checks of one SEM document (equal to ``adapters.runner.provjob.tier3_checks``; pinned by a test)."""
    from agentprov.sem.validate import SEM_CHECKS
    from agentprov.validate.tiers import report_outcomes

    return {f"{profile}:{o.id}": o.status for o in report_outcomes(report, SEM_CHECKS)}


@dataclass
class CorpusValidation:
    """The outcome of :func:`validate_corpus`."""

    mode: str  # dev | release
    tiers: tuple[str, ...]
    rows: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)  # {"ex", "code", "checks"}
    counters: dict[str, int] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)  # validation/summary.json shape
    validation: dict[str, Any] = field(default_factory=dict)  # the D-40 ValidationSummary
    sample: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return not self.failures

    def report(self, corpus: Mapping[str, Any]) -> dict[str, Any]:
        """The ``agentprov-validation-report/0.1`` document (no wall-clock time: byte-stable)."""
        return {"corpus": dict(corpus), "counters": dict(sorted(self.counters.items())), "failures": self.failures,
                "format": REPORT_FORMAT, "mode": self.mode, "notices": list(self.notices), "results": self.rows,
                "sample": self.sample, "summary": self.summary, "tiers": list(self.tiers), "validation": self.validation}


def _stage(reader: CorpusReader) -> Mapping[str, Any]:
    for stage in (reader.derivation() or {}).get("stages", ()):
        if isinstance(stage, Mapping) and stage.get("stage") == "validation":
            return stage
    return {}


def _semantics(stage: Mapping[str, Any], rows: Iterable[IndexRow]) -> list[str]:
    refs = [str(c)[len("tier3:"):] for c in stage.get("checks", ()) if str(c).startswith("tier3:")]
    return refs or sorted({p for r in rows for p in (r.sem or {})})


def validate_corpus(
    reader: CorpusReader,
    *,
    tiers: Sequence[str] = DEFAULT_TIERS,
    mode: str = "dev",
    sample: int | None = None,
    seed: str | None = None,
    semantics_profile: Callable[[str], Any] | None = None,
    source_profile_sha256: Callable[[str, int], str | None] | None = None,
    progress: Progress = NULL_PROGRESS,
    jobs: int | None = None,
    limits: WorkerLimits | None = None,
    cache: Any = None,
) -> CorpusValidation:
    """Re-run ``tiers`` over the stored outputs of ``reader`` (see the module docstring). ``mode`` is ``release``
    (strict: a skipped check fails) or ``dev``. ``semantics_profile(ref)`` and ``source_profile_sha256(id, version)`` are
    the package lookups (``adapters``, injected; defaults read package data).

    ``jobs`` (D-413): ``None`` runs every tier in this process; an integer runs tiers 3 and 4 in T1 ``validate`` jobs
    (``0`` = the host default worker count), the AER tier and everything else here. The two give the same result. A
    caller that injects a lookup always gets the in-process path (a worker resolves profiles from package data only).
    ``limits`` overrides the pool's limits (tests).

    ``cache`` (D-550): a :class:`agentprov.validate.cache.DiskCache` for the tier-4 round trip, or ``None`` (no cache).
    In process it is the ``fidelity`` handle of ``validate_prov``; with ``jobs`` the parent prefetches each document's
    entry for its job and stores what the jobs computed. The result is the same with and without it."""
    unknown = [t for t in tiers if t not in TIERS]
    if unknown or not tiers:
        raise ValueError(f"tiers are {', '.join(TIERS)}")
    if mode not in ("dev", "release"):
        raise ValueError("mode is dev or release")
    injected = semantics_profile is not None or source_profile_sha256 is not None
    if semantics_profile is None or source_profile_sha256 is None:
        from agentprov.corpus.verify import default_catalogues

        catalogues = default_catalogues()
        source_profile_sha256 = source_profile_sha256 or catalogues.source_profile_sha256
        if semantics_profile is None:
            semantics_profile = default_semantics_profile

    wanted = tuple(t for t in TIERS if t in tiers)
    result = CorpusValidation(mode=mode, tiers=wanted)
    rows = reader.index()
    if sample is not None:
        chosen = set(sample_executions([r.ex for r in rows], sample, str(seed)))
        result.sample = {"n": len(chosen), "of": len(rows), "seed": str(seed)}
        rows = [r for r in rows if r.ex in chosen]
    stage = _stage(reader)
    drift = catalogue_drift(stage_map(reader.derivation()))
    for ns, version in drift.items():  # D-460: one finding per namespace; the rows that declare it are gated below
        result.notices.append(f"{DRIFT}: catalogue {ns}@{version}: " + DRIFT_DETAIL.format(version=version))
    counters_drift = len(drift)
    stored_mode = stage.get("mode")
    semantics = _semantics(stage, rows)
    comparable = wanted == TIERS and stored_mode == mode
    if not comparable:
        result.notices.append("the stored validation results are compared only when every default tier runs in the "
                              f"corpus's own validation mode ({stored_mode or 'none recorded'})")
    stored = {r["ex"]: r for r in reader.validation_results()}
    registry = RuleRegistry.default()
    store: RawObjectStore | None = None
    try:
        store = RawObjectStore(reader.root / "raw", limits=reader.limits, create=False, verify_on_read=True)
    except (AgentProvError, OSError):
        result.notices.append("the corpus has no readable raw store: the AER locator checks are skipped")
    profiles: dict[str, Any] = {}

    def profile_of(ref: str) -> Any:
        if ref not in profiles:
            try:
                profiles[ref] = semantics_profile(ref)
            except (AgentProvError, ValueError):
                profiles[ref] = None
        return profiles[ref]

    counters = result.counters
    for name in ("executions", "passed", "failed", "results_reproduced", "results_differ", "results_not_compared"):
        counters[name] = 0
    if counters_drift:
        counters["rules_drift"] = counters_drift
    pool: WorkerPool | None = None
    scratch: Path | None = None
    if jobs is not None and not injected:
        scratch = Path(tempfile.mkdtemp(prefix="agentprov-validate-"))  # 0700; removed below
        staging = RawObjectStore(scratch / "inputs")
        charges: dict[str, int] = {}  # D-554: AER digest -> the job's memory charge (timing only, never outputs)
        cap = (limits or VALIDATE_LIMITS).for_kind("validate").rss_bytes
        pool = WorkerPool(store_root=staging.objects_dir, workers=jobs, limits=limits or VALIDATE_LIMITS,
                          release=mode == "release",
                          charge=lambda job, _root: charges.get(str(job.inputs[0]["sha256"]), cap))
    progress.emit(ProgressEvent("start", total=len(rows), fields={"command": "validate", "plan": ",".join(wanted),
                                                                  "workers": pool.workers if pool is not None else 1}))

    def record(row: IndexRow, out: dict[str, Any], failing: list[str]) -> None:
        counters["executions"] += 1
        out["ex"] = row.ex
        result.rows.append(out)
        if out["verdict"] == "pass":
            counters["passed"] += 1
        else:
            counters["failed"] += 1
            result.failures.append({"checks": failing, "code": "validate.failed", "ex": row.ex})
        if comparable and row.validation is not None and row.validation.digest is not None:
            if sha256_hex(jcs_bytes(out)) == row.validation.digest:
                counters["results_reproduced"] += 1
            else:
                counters["results_differ"] += 1
                before = stored.get(row.ex) or {}
                if before.get("versions") == out.get("versions"):
                    result.failures.append({"checks": [], "code": "validate.results.differ", "ex": row.ex})
                else:
                    result.notices.append("a stored validation row differs and was made by other validator versions")
        else:
            counters["results_not_compared"] += 1
        progress.emit(ProgressEvent("unit_done", unit=row.ex, status="ok" if out["verdict"] == "pass" else "failed"))

    try:
        if pool is None:
            for row in rows:
                progress.emit(ProgressEvent("unit_start", unit=row.ex))
                read = _read_row(reader, row, wanted, mode, semantics, registry, store, source_profile_sha256, drift)
                if read.failing is None:
                    read.out["checks"].update(_documents_part(read, wanted, mode, semantics, profile_of, cache))
                record(row, *_finish_row(read, wanted, mode))
        else:
            _validate_pooled(pool, staging, rows, reader, wanted, mode, semantics, registry, store, source_profile_sha256,
                             profile_of, result, record, progress, drift, charges, cap, cache)
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
    result.notices = list(dict.fromkeys(result.notices))
    result.summary = results_summary(result.rows)
    from agentprov.corpus.derive import validation_stage_definition

    definition = validation_stage_definition(semantics, mode)
    aer_format = CORPUS_FORMATS.get(str((reader.manifest() or {}).get("format")), "aer/0.2")
    result.validation = validation_summary(result.summary, definition, result.rows, aer_format=aer_format)
    linkage = result.validation["linkage"]
    counters["linkage_applicable"] = int(linkage["applicable"])
    counters["linkage_resolved"] = int(linkage["resolved"])
    result.failures.sort(key=lambda f: (f["ex"], f["code"]))
    return result


def default_semantics_profile(ref: str) -> Any:
    """The package's semantics profile for ``ref`` (``<id>@<version>``): the default lookup of :func:`validate_corpus`,
    also the one a T1 ``validate`` job uses."""
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.sem.profiles import parse_profile_ref

    return load_semantics_profile(*parse_profile_ref(ref))


@dataclass
class _Read:
    """What the parent read and checked for one row (D-413): the row so far (the AER tier), the documents, and the read
    outcomes that decide the verdict. ``failing`` is set when the row is already finished (the AER cannot be read)."""

    out: dict[str, Any]
    aer: AerDocument | None = None
    aer_bytes: bytes = b""
    sems: dict[str, SemDocument] = field(default_factory=dict)
    sem_bytes: dict[str, bytes] = field(default_factory=dict)
    sem_ok: bool = True
    prov_ok: bool = False
    prov_bytes: bytes | None = None
    hint: bytes | None = None  # the round-trip cache entry staged for the job (D-550)
    staged: list[str] = field(default_factory=list)  # the digests put in the pool's staging store for this row
    failing: list[str] | None = None


def _read_row(reader: CorpusReader, row: IndexRow, tiers: Sequence[str], mode: str, semantics: Sequence[str],
              registry: RuleRegistry, store: RawObjectStore | None,
              source_profile_sha256: Callable[[str, int], str | None], drift: Mapping[str, int] | None = None) -> _Read:
    """The parent's part of a row: every read (verified, as the reader does) and the AER tier. The bytes kept are the
    exact buffers that were read and verified; nothing is read again for a job (D-413 §3.3).

    ``drift`` (D-460, :func:`agentprov.corpus.authority.catalogue_drift`): a row whose AER declares a drifted catalogue
    version is finished here with the one check ``aer.rules.drift``. Its rule-dependent checks (AER rules, tier 4
    linkage) would read a catalogue other than the one it was built against, and report per-rule errors that are wrong."""
    release = mode == "release"
    read = _Read({"checks": {}})
    out = read.out
    try:
        data = reader.aer_bytes(row)
        aer: AerDocument = load_aer_bytes(data, verify=True)
    except AgentProvError as exc:
        out["checks"]["aer.validator"] = "fail"
        out["verdict"] = "fail"
        read.failing = [f"aer.read:{exc.code}"]
        return read
    read.aer, read.aer_bytes = aer, data
    declared = aer.header.get("rules")
    if drift and isinstance(declared, Mapping) and any(declared.get(ns) == v for ns, v in drift.items()):
        out["checks"][DRIFT] = "fail"
        out["verdict"] = "fail"
        read.failing = [DRIFT]
        return read
    if "aer" in tiers:
        pid, _, number = row.profile.rpartition("@")
        sha = source_profile_sha256(pid, int(number)) if number.isdigit() else None
        validator = AerValidator(store=store, catalogues=registry, mode=mode,  # type: ignore[arg-type]
                                 profile_digests=None if sha is None else {(pid, int(number)): sha})
        for line in data.splitlines(keepends=True):
            validator.feed(line)
        report = validator.finish()
        aer_ok = bool(report.passed if release else report.ok)
        out["aer"] = {"errors": sorted({f.code for f in report.errors}), "mode": mode,
                      "skipped": sorted(report.skipped), "verdict": "pass" if aer_ok else "fail"}
        out["checks"]["aer.validator"] = out["aer"]["verdict"]
    for ref in semantics:
        stage = (row.sem or {}).get(ref)
        if stage is None or stage.digest is None:
            read.sem_ok = False
            continue
        try:
            sem_data, doc = reader.read_sem_bytes(row, ref)
        except AgentProvError:
            read.sem_ok = False
            continue
        read.sems[ref], read.sem_bytes[ref] = doc, sem_data
    read.prov_ok = (row.prov or {}).get(SPEC) is not None and (row.prov or {})[SPEC].digest is not None
    if read.prov_ok and ("prov" in tiers or "linkage" in tiers):
        try:
            read.prov_bytes = reader.prov_bytes(row, SPEC)
        except AgentProvError:
            read.prov_ok = False
    return read


def _documents_part(read: _Read, tiers: Sequence[str], mode: str, semantics: Sequence[str],
                    profile_of: Callable[[str], Any], cache: Any = None) -> dict[str, Any]:
    """Tiers 3 and 4 of one row in this process: the checks to merge into the row's ``checks``."""
    part = validate_documents(read.aer, read.sems, read.prov_bytes, tiers=tiers, mode=mode, semantics=semantics,
                              profile_of=profile_of, fidelity=cache)
    for key in ("spec", "versions"):
        if key in part:
            read.out[key] = part[key]
    return dict(part["checks"])


def validate_documents(aer: Any, sems: Mapping[str, SemDocument], prov_bytes: bytes | None, *, tiers: Sequence[str],
                       mode: str, semantics: Sequence[str], profile_of: Callable[[str], Any],
                       fidelity: Any = None) -> dict[str, Any]:
    """Tiers 3 (``sem``) and 4 (``prov``, ``linkage``) of one execution over its verified documents: ``{"checks"}`` plus
    ``spec`` and ``versions`` when tier 4 ran. Pure; the in-process path and the T1 ``validate`` job (D-413) both call it.
    ``sems`` holds the SEM documents that were read, by profile ref; ``prov_bytes`` is ``None`` when tier 4 does not
    run (not requested, no PROV output, or unreadable). ``profile_of(ref)`` returns a profile or ``None``. ``fidelity``
    is the round-trip cache handle of ``validate_prov`` (D-550)."""
    release = mode == "release"
    checks: dict[str, str] = {}
    out: dict[str, Any] = {"checks": checks}
    if "sem" in tiers:
        from agentprov.sem.validate import validate_sem_document

        for ref in semantics:
            if ref not in sems:
                continue
            profile = profile_of(ref)
            if profile is None:
                checks[f"{ref}:profile"] = "skipped"
                continue
            sem_report = validate_sem_document(sems[ref], aer, mode="release" if release else "dev", profile=profile)
            checks.update(tier3_checks(sem_report, ref))
    if prov_bytes is not None:
        from agentprov.validate import validate_prov

        report = validate_prov(prov_bytes, aer, sems=[sems[r] for r in semantics if r in sems], fidelity=fidelity)
        tier4 = tier4_row(report, strict=release)
        checks.update({k: v for k, v in tier4["checks"].items()
                       if ("linkage" in tiers if k.startswith(LINKAGE_PREFIX) else "prov" in tiers)})
        out["spec"] = SPEC
        out["versions"] = tier4["versions"]
    return out


def _finish_row(read: _Read, tiers: Sequence[str], mode: str) -> tuple[dict[str, Any], list[str]]:
    """The verdict and the failing check ids of one row (unchanged rules)."""
    out = read.out
    if read.failing is not None:
        return out, read.failing
    release = mode == "release"
    prov_ok, sem_ok = read.prov_ok, read.sem_ok
    verdicts = [out["checks"].get("aer.validator", "pass")]
    if prov_ok and sem_ok:
        statuses = [v for k, v in out["checks"].items() if k != "aer.validator"]
        bad = {"fail", "skipped"} if release else {"fail"}
        verdicts.append("fail" if (not statuses and ("prov" in tiers or "linkage" in tiers or "sem" in tiers))
                        or any(s in bad for s in statuses) else "pass")
    elif "prov" in tiers or "linkage" in tiers or "sem" in tiers:
        verdicts.append("fail")
    out["verdict"] = "pass" if set(verdicts) == {"pass"} else "fail"
    bad_status = {"fail", "skipped"} if release else {"fail"}
    failing = sorted(k for k, v in out["checks"].items() if v in bad_status)
    if out["verdict"] == "fail" and not failing:
        failing = ["stage.output_missing"] if not (prov_ok and sem_ok) else []
    return out, failing


def _validate_row(reader: CorpusReader, row: IndexRow, tiers: Sequence[str], mode: str, semantics: Sequence[str],
                  registry: RuleRegistry, store: RawObjectStore | None, profiles: dict[str, Any],
                  semantics_profile: Callable[[str], Any], source_profile_sha256: Callable[[str, int], str | None],
                  ) -> tuple[dict[str, Any], list[str]]:
    """One row in this process: the parent's reads and AER tier, tiers 3 and 4, the verdict."""

    def profile_of(ref: str) -> Any:
        if ref not in profiles:
            try:
                profiles[ref] = semantics_profile(ref)
            except (AgentProvError, ValueError):
                profiles[ref] = None
        return profiles[ref]

    read = _read_row(reader, row, tiers, mode, semantics, registry, store, source_profile_sha256)
    if read.failing is None:
        read.out["checks"].update(_documents_part(read, tiers, mode, semantics, profile_of))
    return _finish_row(read, tiers, mode)


#: The validate pool's limits: tier 4 grows like the ``prov`` job's (D-55), so a ``validate`` job gets the ``prov`` cap. Set
#: on this pool only; the global KIND_RSS_BYTES (and every other pool's recorded caps) stay as they are.
VALIDATE_LIMITS: Final = WorkerLimits(kind_rss_bytes={**KIND_RSS_BYTES, "validate": KIND_RSS_BYTES["prov"]})
#: Rows per pool batch (as ``derive``): the parent stages one batch's documents while the pool runs the previous batch's
#: jobs, and records the batches in order.
POOL_BATCH: Final = 256
#: The check id of a row whose ``validate`` job was stopped or crashed (D-413 §3.6).
WORKER_CHECK: Final = "validate.worker"


def _validate_pooled(pool: WorkerPool, staging: RawObjectStore, rows: Sequence[IndexRow], reader: CorpusReader,
                     tiers: Sequence[str], mode: str, semantics: Sequence[str], registry: RuleRegistry,
                     store: RawObjectStore | None, source_profile_sha256: Callable[[str, int], str | None],
                     profile_of: Callable[[str], Any], result: CorpusValidation,
                     record: Callable[[IndexRow, dict[str, Any], list[str]], None], progress: Progress,
                     drift: Mapping[str, int] | None = None,
                     charges: dict[str, int] | None = None, cap: int | None = None, cache: Any = None) -> None:
    """Tiers 3 and 4 in T1 ``validate`` jobs (D-413). The parent reads, verifies and runs the AER tier for each row, puts
    the exact verified buffers in ``staging`` (the pool's private store root), and records the rows in index order. A
    job that is stopped or crashes makes its row fail with :data:`WORKER_CHECK`.

    With a ``cache`` (D-550) the parent stages the cache's entry for each PROV document as the job's ``fidelity`` input
    (a hint the job re-checks against the bytes it validates) and stores the round trip a job returns in its second
    frame (``{"fidelity": ...}``). A job never reads the cache itself (G.4.4).

    Pipelined (perf round 2, D-893): while the pool runs one batch, the parent reads and stages the next, as ``derive``
    does; rows are still recorded in index order, so the result does not change. Staged inputs are counted, so bytes two
    batches share are removed only when the last of them is recorded. A cache entry stored by one batch can reach the
    next batch's rows one batch later than before (a hint, re-checked by the job: timing only)."""
    refs: Counter[str] = Counter()

    def put(read: _Read, data: bytes, ext: str) -> str:
        sha = staging.put(data, ext=ext).sha256
        refs[sha] += 1
        read.staged.append(sha)
        return sha

    def stage(batch: Sequence[IndexRow]) -> tuple[list[_Read], list[Job], list[int | None]]:
        reads: list[_Read] = []
        jobs: list[Job] = []
        slots: list[int | None] = []
        for row in batch:
            progress.emit(ProgressEvent("unit_start", unit=row.ex))
            read = _read_row(reader, row, tiers, mode, semantics, registry, store, source_profile_sha256, drift)
            reads.append(read)
            if read.failing is not None or not (("sem" in tiers and read.sems) or read.prov_bytes is not None):
                slots.append(None)  # tiers 3 and 4 have nothing to run: the row is finished here, as in process
                continue
            handed = [ref for ref in semantics if ref in read.sems]
            inputs = [{"sha256": put(read, read.aer_bytes, "jsonl"), "role": "aer"}]
            inputs += [{"sha256": put(read, read.sem_bytes[ref], "jsonl"), "role": "sem"} for ref in handed]
            params: dict[str, Any] = {"tiers": list(tiers), "mode": mode, "semantics": list(semantics), "sems": handed,
                                      "prov": read.prov_bytes is not None}
            if read.prov_bytes is not None:
                inputs.append({"sha256": put(read, read.prov_bytes, "json"), "role": "prov"})
                if cache is not None:
                    hint = cache.hint(sha256_hex(read.prov_bytes))
                    params["fidelity"] = {"collect": True, "hint": hint is not None}
                    if hint is not None:
                        read.hint = hint
                        inputs.append({"sha256": put(read, hint, "json"), "role": "fidelity"})
            if charges is not None:  # D-554: prov-perf's model over the stored PROV (no PROV: the base charge)
                hit = "validate" if read.prov_bytes is not None and params.get("fidelity", {}).get("hint") else None
                charges[inputs[0]["sha256"]] = prov_charge(len(read.prov_bytes or b""), hit=hit, cap=cap)
            slots.append(len(jobs))
            jobs.append(Job(key=f"{len(jobs):09d}", kind="validate", inputs=tuple(inputs), params=params))
        return reads, jobs, slots

    def finish(batch: Sequence[IndexRow], reads: list[_Read], slots: list[int | None],
               running: Future[list[JobResult]] | None) -> None:
        results = running.result() if running is not None else []
        for row, read, slot in zip(batch, reads, slots, strict=True):
            if read.failing is None:
                if slot is None:
                    read.out["checks"].update(_documents_part(read, tiers, mode, semantics, profile_of, cache))
                else:
                    job_result = results[slot]
                    try:
                        frames = job_result.json if job_result.ok else ()
                    finally:
                        job_result.close()
                    frame = frames[0] if frames else None
                    if cache is not None and read.prov_bytes is not None and frame is not None:
                        for extra in frames[1:]:
                            if isinstance(extra, Mapping) and "fidelity" in extra:
                                cache.store_frame(read.prov_bytes, extra["fidelity"])
                    if frame is None or not isinstance(frame.get("checks"), dict):
                        code = job_result.error.code if job_result.error is not None else "worker.error"
                        read.out["checks"][WORKER_CHECK] = "fail"
                        result.notices.append(f"execution {row.ex}: the validate job was stopped ({code})")
                    else:
                        read.out["checks"].update(frame["checks"])
                        for key in ("spec", "versions"):
                            if key in frame:
                                read.out[key] = frame[key]
            record(row, *_finish_row(read, tiers, mode))
        for read in reads:  # the batch's staged copies are not needed any more, unless the next batch staged them too
            for sha in read.staged:
                refs[sha] -= 1
                if refs[sha] <= 0:
                    del refs[sha]
                    _drop(staging, sha)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="agentprov-validate") as background:
        pending: tuple[Sequence[IndexRow], list[_Read], list[int | None], Future[list[JobResult]] | None] | None = None
        for start in range(0, len(rows), POOL_BATCH):
            batch = rows[start : start + POOL_BATCH]
            reads, jobs, slots = stage(batch)
            running = background.submit(pool.run, jobs) if jobs else None
            if pending is not None:
                finish(*pending)
            pending = (batch, reads, slots, running)
        if pending is not None:
            finish(*pending)


def _drop(store: RawObjectStore, sha: str) -> None:
    for ext in ("jsonl", "json"):
        path = store.path_for(sha, ext)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
            path.unlink()
