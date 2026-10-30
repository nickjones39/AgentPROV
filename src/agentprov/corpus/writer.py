"""The working-corpus writer, phase-3 subset: objects, origins, members, index and register (docs/architecture PQ phase 3;
HL H.1.5, H.6.1, K.5.7; MN M.1.2).

MN M.1.2 names no module for the writer that holds a working tree open (``package.py`` seals it, ``derive.py`` runs the
derivation DAG), so it lives here and is recorded as a gap in AGENTS.md.

:class:`CorpusWriter` writes into ``<DIR>.partial`` (H.1.5(1)) under the single-writer lock (guard G6). It never seals:
``corpus.json``, ``checksums.sha256``, validation and the swap to ``<DIR>`` are phase 11. Sequence::

    with CorpusWriter(final_dir, limits=..., release=False) as corpus:
        put = corpus.add_object(fp, Origin.git(...), ext="zip")                  # object + mandatory origin (K.5.7(1))
        corpus.expand([ContainerSpec(put.sha256, "snapshot-1", "deposit.zip", (Selection(...),))], pool)
        corpus.write_aer(ex, aer_bytes)
        corpus.add_execution(ExecutionEntry(...))
        # leaving the block flushes the four JSONL files

Guards, in this order: the final directory must not exist; ``assert_writable`` (no sealed ancestor); the directory is
created; the git work-tree guard; the lock. ``flush`` re-checks ``assert_writable`` and writes ``raw/origins.jsonl``,
``raw/members.jsonl``, ``register.jsonl`` and ``executions.jsonl`` atomically and always (a 0-byte file when empty,
H.1.4(1)). It reconciles the index with the register (H.6.1 R5): every code in a row's ``issues`` needs a register entry
for that ``ex``, and its severity decides ``status``. A row's raw entries must be stored when ``included`` and the
primary artefact must have an origin.

The dev-mode interpreter advisory of ``expand`` is kept on :attr:`CorpusWriter.interpreter_advisory` for the
``corpus.json`` producer block (phase 11).

Phase 6 (the import pipeline, MN N.2.2) adds the derived layers an import writes: PROV-JSON files
(:meth:`CorpusWriter.write_prov`), the per-execution validation rows of ``validation/results.jsonl`` and their
``validation/summary.json`` (:meth:`CorpusWriter.add_validation`, written at flush, sorted by ``ex``), and the single JSON
documents ``derivation.json`` and the working ``corpus.json`` (:meth:`CorpusWriter.write_document`, H.1.4(2) formatting).
:meth:`CorpusWriter.discard_execution` drops one execution's index row, register entries and validation row before it is
re-processed (``import --retry-failed``); its files are overwritten in place.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import IO, Any

from agentprov.corpus.buildstep import BuildStep, BuildStepError, StepTracker
from agentprov.corpus.index import ExecutionEntry, IndexLog, IndexRow, compute_status, primary_role
from agentprov.corpus.layout import (
    CorpusLayout,
    assert_outside_git_work_tree,
    assert_writable,
    partial_dir,
)
from agentprov.corpus.register import RegisterEntry, RegisterLog
from agentprov.envinfo import InterpreterAdvisory
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov.io.atomic import DestinationExistsError, LockFile, atomic_write_bytes
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.io.workers import WorkerPool
from agentprov.raw.members import ContainerSpec, ExpandOutcome, MemberLog, MemberRow, expand_containers
from agentprov.raw.origins import Origin, OriginError, OriginLog
from agentprov.raw.store import PutResult, RawObjectStore

__all__ = ["CorpusWriter", "CorpusWriterError"]


class CorpusWriterError(AgentProvError):
    """The working corpus is inconsistent (``corpus.writer.*``)."""

    code = "corpus.writer.error"
    exit_code = 1


class CorpusWriter:
    """Writes the phase-3 files of one working corpus. See the module docstring."""

    def __init__(
        self,
        final_dir: str | os.PathLike[str],
        *,
        limits: IngestLimits | None = None,
        shard_depth: int = 1,
        release: bool = False,
        command: str = "import",
        break_stale_lock: bool = False,
        git_ignored: Callable[[Path, Path], bool] | None = None,
        build_step: BuildStep | None = None,
    ) -> None:
        self.final_dir = Path(final_dir)
        self.partial = partial_dir(self.final_dir)
        self.layout = CorpusLayout(self.partial, shard_depth=shard_depth)
        self.limits = limits or IngestLimits()
        self.release = release
        self._command = command
        self._break_stale = break_stale_lock
        self._git_ignored = git_ignored
        self._lock: LockFile | None = None
        self.store: RawObjectStore
        self.origins = OriginLog()
        self.members = MemberLog()
        self.register = RegisterLog()
        self.index = IndexLog()
        self._pending: list[ExecutionEntry] = []
        #: BF-20, CB-6: included raw objects this corpus may list without storing (purged, withheld or referenced in the
        #: source of a derivation, which sets it); any other absent included object is refused.
        self.absent_ok: frozenset[str] = frozenset()
        self._validation: dict[str, dict[str, Any]] = {}
        self.interpreter_advisory: InterpreterAdvisory | None = None
        #: D-780: the process's commit facts (the CLI computes them; ``corpus/`` runs no subprocess) merged into the
        #: manifest this writer writes. ``None`` (library use, scratch trees): the manifest gets no build record.
        self._builds = None if build_step is None else StepTracker(build_step)

    # ----------------------------------------------------------------------------------------- lifecycle
    def open(self) -> CorpusWriter:
        """Run the guards, create the working tree, take the lock and load any existing logs (a resumed run)."""
        if os.path.lexists(self.final_dir):
            raise DestinationExistsError("the final corpus directory already exists")
        assert_writable(self.partial)
        # Before mkdir, so a refusal leaves nothing (not even missing parents) in the work tree (RC-1).
        assert_outside_git_work_tree(self.partial, is_ignored=self._git_ignored)
        self.partial.mkdir(parents=True, exist_ok=True)
        lock = LockFile(self.layout.lock, command=self._command, break_stale=self._break_stale)
        lock.acquire()
        self._lock = lock
        try:
            self.store = RawObjectStore(self.layout.raw, limits=self.limits)
            if self.layout.origins.exists():
                self.origins = OriginLog.load(self.layout.origins, self.limits)
            if self.layout.members.exists():
                self.members = MemberLog.load(self.layout.members, self.limits)
            if self.layout.register.exists():
                self.register = RegisterLog.load(self.layout.register, self.limits)
            if self.layout.executions.exists():
                self.index = IndexLog.load(self.layout.executions, self.layout, self.limits)
            if self.layout.validation_results.exists():
                self._validation = _load_validation(self.layout.validation_results.read_bytes(), self.limits)
        except BaseException:
            self.close()
            raise
        return self

    def close(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def __enter__(self) -> CorpusWriter:
        return self.open()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        try:
            if exc_type is None:
                self.flush()
        finally:
            self.close()

    def _require_open(self) -> None:
        if self._lock is None:
            raise CorpusWriterError("the corpus writer is not open", code="corpus.writer.closed")

    # ----------------------------------------------------------------------------------------- objects and origins
    def _check_origin(self, origin: Origin) -> None:
        if not isinstance(origin, Origin):
            raise OriginError("an object needs an origin record (K.5.7(1))", code="raw.origin.missing")
        if self.release and origin.kind == "local":
            raise OriginError("release mode refuses a local origin", code="raw.origin.local_in_release")

    def add_object(
        self,
        data: bytes | IO[bytes],
        origin: Origin,
        *,
        ext: str = "bin",
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> PutResult:
        """Store ``data`` (bytes or a binary stream) and record ``origin``; an object without an origin is refused.

        ``expected_sha256`` / ``expected_size`` (for example a verified pin) are checked by the store before publishing:
        a difference raises ``raw.object.mismatch`` and neither the object nor its origin is recorded (CB-20)."""
        self._require_open()
        self._check_origin(origin)
        if isinstance(data, bytes):
            put = self.store.put(data, ext=ext, expected_sha256=expected_sha256, expected_size=expected_size)
        else:
            put = self.store.put_stream(data, ext=ext, expected_sha256=expected_sha256, expected_size=expected_size)
        self.origins.add(put.sha256, origin)
        return put

    def add_origin(self, sha256: str, origin: Origin) -> bool:
        """Record a further (mirror) origin of an object that is already stored."""
        self._require_open()
        self._check_origin(origin)
        if not self.store.has(sha256):
            raise CorpusWriterError("an origin names an object that is not stored", code="corpus.writer.unknown_object")
        return self.origins.add(sha256, origin)

    def expand(
        self, containers: Sequence[ContainerSpec], pool: WorkerPool, *, limits: IngestLimits | None = None
    ) -> ExpandOutcome:
        """Run the ``expand`` stage (AD-12) for stored containers and record rows, member origins and register entries.

        Every root container needs an origin already (K.5.7(1)). The outcome's interpreter advisory (dev mode below the
        floor) is kept on the writer.
        """
        self._require_open()
        for spec in containers:
            if self.origins.count(spec.sha256) == 0:
                raise CorpusWriterError("a container to expand has no origin record", code="raw.origin.missing")
        outcome = expand_containers(
            self.store, containers, pool=pool, limits=limits or self.limits, release=self.release
        )
        self._note_stage("expand", bool(containers))
        grouped: dict[str, list[MemberRow]] = {}
        for row in outcome.rows:
            grouped.setdefault(row.container, []).append(row)
        for container, rows in grouped.items():
            self.members.add_container(container, rows)
        for sha, origin in outcome.origins:
            self.origins.add(sha, origin)
        self.register.extend(RegisterEntry.from_event(event) for event in outcome.events)
        if outcome.advisory is not None:
            self.interpreter_advisory = outcome.advisory
        return outcome

    # ----------------------------------------------------------------------------------------- register, AER, index
    def add_register(self, entry: RegisterEntry) -> None:
        self._require_open()
        self.register.add(entry)

    def write_aer(self, ex: str, data: bytes) -> Path:
        """Write one execution's AER file at its layout path (atomic). ``data`` is produced by ``aer.writer``."""
        self._require_open()
        path = self.layout.aer_path(ex)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)
        self._note_stage("aer")
        return path

    def add_execution(self, entry: ExecutionEntry) -> None:
        """Queue one execution for the index; the row is built and checked at :meth:`flush`."""
        self._require_open()
        self._pending.append(entry)

    def write_prov(self, spec: str, ex: str, data: bytes) -> str:
        """Write one execution's PROV-JSON for ``spec`` at its layout path (atomic); returns the file's sha256 (hex)."""
        self._require_open()
        path = self.layout.prov_path(spec, ex)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)
        self._note_stage("compat" if spec != "agentprov-prov/0.1" else "prov")
        return sha256_hex(data)

    def write_sem(self, profile: str, ex: str, data: bytes) -> str:
        """Write one execution's SEM file for ``profile`` (``<id>@<version>``) at its layout path (atomic); returns the
        file's sha256 (hex). The index records the SEM digest (the seal's ``records_sha256``), which the caller knows."""
        self._require_open()
        path = self.layout.sem_path(profile, ex)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)
        self._note_stage("sem")
        return sha256_hex(data)

    def add_validation(self, ex: str, row: Mapping[str, Any]) -> str:
        """Record one execution's ``validation/results.jsonl`` row (``ex`` is added); returns its JCS sha256 (hex)."""
        self._require_open()
        body = {**dict(row), "ex": ex}
        self._validation[ex] = body
        self._note_stage("validation")
        return sha256_hex(jcs_bytes(body))

    def has_execution(self, ex: str) -> IndexRow | None:
        """The index row of ``ex`` when one is recorded (a resumed run skips it)."""
        return self.index.get(ex)

    def pending_row(self, ex: str) -> IndexRow | None:
        """The row :meth:`flush` will write for ``ex`` while it is still queued, built by the same rule (``_build_row``
        with the register entries of ``ex``); ``None`` when nothing is queued for it. Nothing is added or written."""
        self._require_open()
        entry = next((e for e in reversed(self._pending) if e.ex == ex), None)
        if entry is None:
            return None
        registered = {(item.code, item.severity) for item in self.register.entries() if item.subject.get("ex") == ex}
        return self._build_row(entry, {ex: registered} if registered else {})

    def add_snapshot(self, ex: str, snapshot_id: str) -> None:
        """H.7.2(1) (D-202): the execution ``ex`` is also a member of ``snapshot_id`` (identical bytes, same mapping
        identity, another snapshot). Its row lists the snapshot and its ``n_origins`` is recounted from
        ``raw/origins.jsonl`` (the new origin is recorded first); nothing else of the row changes."""
        self._require_open()
        for n, entry in enumerate(self._pending):
            if entry.ex == ex:  # queued in this run: the row is built (and n_origins counted) at flush
                self._pending[n] = dataclasses.replace(entry, snapshot_ids=tuple(sorted({*entry.snapshot_ids, snapshot_id})))
                return
        row = self.index.get(ex)
        if row is None:
            raise CorpusWriterError("a snapshot is added to an execution the index does not hold", code="corpus.writer.index")
        primary = [r for r in row.raw if r.role == primary_role(row.mode)]
        n_origins = self.origins.count(primary[0].sha256) if len(primary) == 1 else row.n_origins
        self.index.discard(ex)
        self.index.add(dataclasses.replace(row, snapshot_ids=tuple(sorted({*row.snapshot_ids, snapshot_id})),
                                           n_origins=max(1, n_origins)))

    def discard_execution(self, ex: str) -> None:
        """Forget ``ex``'s index row, register entries and validation row (``--retry-failed`` re-processes it)."""
        self._require_open()
        self.index.discard(ex)
        self.register.discard_execution(ex)
        self._validation.pop(ex, None)
        self._pending = [e for e in self._pending if e.ex != ex]

    def discard_failure(self, subject: Mapping[str, str]) -> None:
        """Forget ``subject``'s recorded ``map`` failures before it is mapped again (:meth:`RegisterLog.discard_failure`)."""
        self._require_open()
        self.register.discard_failure(subject)

    def write_document(self, path: Path, document: Mapping[str, Any]) -> None:
        """A single JSON document (``derivation.json``, ``corpus.json``): sorted keys, 2-space indentation,
        ``ensure_ascii=False`` and a final LF (H.1.4(2)); integers only (H.1.4(3))."""
        self._require_open()
        assert_writable(self.partial)
        if self._builds is not None and path == self.layout.manifest and isinstance(document.get("producer"), Mapping):
            document = {**document, "producer": self._with_build(document["producer"])}
        atomic_write_bytes(path, document_bytes(document))

    def _note_stage(self, stage: str, wrote: bool = True) -> None:
        if self._builds is not None and wrote:
            self._builds.note(stage)

    def plan_build_stages(self, stages: Sequence[str]) -> None:
        """A derivation names the stages it recomputes (D-780); the carried layers it copies through this writer are not
        this process's work. Call before the manifest is written."""
        if self._builds is not None:
            self._builds.plan(stages)

    def _with_build(self, producer: Mapping[str, Any]) -> dict[str, Any]:
        assert self._builds is not None
        on_disk = None
        if producer.get("build_steps") is None:
            current = self.read_document(self.layout.manifest)
            on_disk = ((current or {}).get("producer") or {}).get("build_steps") if isinstance(current, dict) else None
        try:
            return self._builds.apply(producer, on_disk)
        except BuildStepError as exc:
            raise CorpusWriterError(f"the manifest's build_steps cannot be extended: {exc}", code="corpus.writer.document") from None

    def read_document(self, path: Path) -> dict[str, Any] | None:
        """A JSON document of this working corpus, parsed strictly; ``None`` when it does not exist."""
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            value = strict_json_loads(data, self.limits)
        except IngestError:
            raise CorpusWriterError(f"{path.name} of the working corpus cannot be parsed", code="corpus.writer.document") from None
        if not isinstance(value, dict):
            raise CorpusWriterError(f"{path.name} of the working corpus is not an object", code="corpus.writer.document")
        return value

    # ----------------------------------------------------------------------------------------- flush
    def _build_row(self, entry: ExecutionEntry, registered_by_ex: dict[str, set[tuple[str, str]]]) -> IndexRow:
        primary = [r for r in entry.raw if r.role == primary_role(entry.mode)]
        if len(primary) != 1:
            raise CorpusWriterError("an execution has exactly one primary raw artefact", code="corpus.writer.raw")
        for ref in entry.raw:
            if ref.included and ref.sha256 not in self.absent_ok and not self.store.has(ref.sha256):
                raise CorpusWriterError("an included raw artefact is not in the store", code="corpus.writer.raw")
        n_origins = self.origins.count(primary[0].sha256)
        if n_origins == 0:
            raise CorpusWriterError("the primary artefact has no origin record", code="raw.origin.missing")
        registered = registered_by_ex.get(entry.ex, set())
        severities: list[str] = []
        for code in sorted(set(entry.issues)):
            found = [sev for c, sev in registered if c == code]
            if not found:
                raise CorpusWriterError(
                    "an issue code in a row has no register entry for that execution (H.6.1 R5)",
                    code="corpus.index.issue_unregistered",
                )
            severities.extend(found)
        if not self.layout.aer_path(entry.ex).is_file():
            raise CorpusWriterError("the execution's AER file is not written", code="corpus.writer.aer_missing")
        prov_paths: dict[str, str] | None = None
        if entry.prov is not None:
            prov_paths = {}
            for spec, out in entry.prov.items():
                if out.digest is not None:
                    if not self.layout.prov_path(spec, entry.ex).is_file():
                        raise CorpusWriterError("the execution's PROV file is not written", code="corpus.writer.prov_missing")
                    prov_paths[spec] = self.layout.prov_relpath(spec, entry.ex)
        sem_paths: dict[str, str] | None = None
        if entry.sem is not None:
            sem_paths = {}
            for profile, out in entry.sem.items():
                if out.digest is not None:
                    if not self.layout.sem_path(profile, entry.ex).is_file():
                        raise CorpusWriterError("the execution's SEM file is not written", code="corpus.writer.sem_missing")
                    sem_paths[profile] = self.layout.sem_relpath(profile, entry.ex)
        stages: dict[str, Any] = dict(entry.stages)
        if entry.sem is not None:
            stages["sem"] = {profile: out.state for profile, out in entry.sem.items()}
        if entry.prov is not None:
            stages["prov"] = {spec: out.state for spec, out in entry.prov.items()}
        if entry.validation is not None:
            stages["validation"] = entry.validation.state
        return IndexRow(
            ex=entry.ex,
            mode=entry.mode,
            unit=entry.unit,
            source_id=entry.source_id,
            snapshot_ids=tuple(sorted(set(entry.snapshot_ids))),
            source_key=entry.source_key,
            raw=tuple(entry.raw),
            n_origins=n_origins,
            adapter=entry.adapter,
            profile=entry.profile,
            aer_digest=entry.aer_digest,
            aer_path=self.layout.aer_relpath(entry.ex),
            stages=dict(entry.stages),
            status=compute_status(stages, severities),
            completeness=entry.completeness,
            execution_observed=entry.execution_observed,
            issues=tuple(sorted(set(entry.issues))),
            attempt=entry.attempt,
            sem=None if entry.sem is None else dict(entry.sem),
            sem_paths=sem_paths,
            prov=None if entry.prov is None else dict(entry.prov),
            prov_paths=prov_paths,
            validation=entry.validation,
            facet_members=entry.facet_members,
        )

    def flush(self) -> None:
        """Write ``raw/origins.jsonl``, ``raw/members.jsonl``, ``register.jsonl``, the validation files and
        ``executions.jsonl`` (always, sorted). The index is written last: it is the resume commit point, so a flush that
        fails part-way never leaves an index row whose validation row is missing (a resume re-processes the execution)."""
        self._require_open()
        assert_writable(self.partial)
        registered_by_ex: dict[str, set[tuple[str, str]]] = {}
        for item in self.register.entries():
            if "ex" in item.subject:
                registered_by_ex.setdefault(item.subject["ex"], set()).add((item.code, item.severity))
        for entry in self._pending:
            self.index.add(self._build_row(entry, registered_by_ex))
        self._pending.clear()
        self.origins.write(self.layout.origins)
        self.members.write(self.layout.members)
        self.register.write(self.layout.register)
        if self._validation or self.layout.validation_results.exists():
            self.layout.validation_results.parent.mkdir(parents=True, exist_ok=True)
            rows = [self._validation[ex] for ex in sorted(self._validation, key=lambda e: e.encode("ascii"))]
            atomic_write_bytes(self.layout.validation_results, b"".join(jcs_bytes(r) + b"\n" for r in rows))
            atomic_write_bytes(self.layout.validation_summary, document_bytes(validation_summary(rows)))
        self.index.write(self.layout.executions)


def document_bytes(document: Mapping[str, Any]) -> bytes:
    """H.1.4(2): sorted keys, 2-space indentation, ``ensure_ascii=False``, final LF. Floats are refused (H.1.4(3))."""
    _refuse_floats(document)
    return (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _refuse_floats(value: Any) -> None:
    if isinstance(value, float):
        raise CorpusWriterError("corpus-layer JSON holds no floating-point numbers (H.1.4(3))", code="corpus.writer.float")
    if isinstance(value, Mapping):
        for item in value.values():
            _refuse_floats(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _refuse_floats(item)


def _load_validation(data: bytes, limits: IngestLimits) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        for _, _, value in iter_jsonl(io.BytesIO(data), limits):
            if not isinstance(value, dict) or not isinstance(value.get("ex"), str):
                raise CorpusWriterError("a validation row is an object with an ex", code="corpus.writer.validation")
            rows[value["ex"]] = value
    except IngestError as exc:
        raise CorpusWriterError(f"validation/results.jsonl is not strict JSONL ({exc.code})", code="corpus.writer.validation") from None
    return rows


def validation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``validation/summary.json`` (H.2.12 subset): per check id, the executions by status, over every row's ``checks``."""
    checks: dict[str, dict[str, int]] = {}
    for row in rows:
        for check_id, status in sorted(dict(row.get("checks", {})).items()):
            tally = checks.setdefault(check_id, {"fail": 0, "not_applicable": 0, "pass": 0, "skipped": 0})
            key = status if status in tally else "fail"
            tally[key] += 1
    return {
        "checks": [{"id": cid, **tally} for cid, tally in sorted(checks.items())],
        "executions": len(rows),
        "format": "agentprov-validation-summary/0.1",
    }
