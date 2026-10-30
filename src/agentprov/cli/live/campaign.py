"""One live campaign: workers, attempts, staging ingestion, resume, canary (MN N.2.1 behaviour 2-4, N.1.8(4), N.1.10;
D.10.9; D.11.3; HL H.6.1 R7).

The caller (``agentprov.cli.run``) has resolved the plan, the agent configuration, the environment and its T0 identity,
and holds the working corpus open. :class:`Campaign` then:

* keeps ``jobs`` backend workers (:class:`Slot`; each with its own T2 home ``$AGENTPROV_HOME/t2home/<worker>`` and empty
  working directory ``$AGENTPROV_HOME/staging/<worker>``, both 0700); every spawn is followed by ``hello`` and the
  identity cross-check; a worker that times out, dies or breaks the protocol is killed and replaced;
* runs each attempt in a fresh session directory ``$AGENTPROV_HOME/staging/<session>/`` (0700; the session UUIDv7 is
  minted by T0 and is the execution id ``ex_<session>``), with a per-cell wall-clock budget; on a kill the parent appends
  ``session.end{aborted, appended_by: parent}`` to the log (``agentprov_capture.log.append_terminal``) and the partial
  evidence is ingested;
* ingests every finished attempt in the main thread (:mod:`.staging`, then the runner's
  :class:`~agentprov.adapters.runner.session.LiveSessionPipeline`): every attempt is its own sealed execution, never
  overwritten;
* re-attempts a cell while it is not conclusive (session ``complete`` and seal accounting ``consistent`` or
  ``unverifiable``) and ``--max-attempts`` (counted across invocations) allows; ``--retry-inconsistent`` also re-attempts a
  cell whose complete attempts are all ``inconsistent``;
* resumes from the attempt ledger in the working manifest (``live.sessions``), whose entries count only while the
  capture log they name is in the raw store (keyed on sealed raw evidence);
* stops after the canary cells when a D.10.9 canary condition appears in their sealed evidence;
* stops starting cells when an attempt's capture log records a fatal ``UnsupportedConfiguration`` at setup: that refusal
  is a property of the configuration, so every further cell and re-attempt would fail the same way (``config_stop``);
* with caps (D-725), starts a cell only while the corpus's billed calls and spend plus the worst case of every in-flight
  cell and the new one fit them (:class:`agentprov.cli.live.policy.Budget`), charging each attempt's capture log.

A session that breaks the identity cross-check aborts the campaign (``IdentityMismatch``, exit 3) and stays in staging;
a session that holds a secret value, or whose capture log the worker sealed after a failed redaction scan (D-290), is
quarantined (nothing stored, the directory kept, register ``capture.quarantined``).
"""

from __future__ import annotations

import logging
import shutil
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov import drain
from agentprov.cli.live import staging as st
from agentprov.cli.live.envs import EnvIdentity, check_hello
from agentprov.cli.live.quality import SessionQuality, canary_conditions, quality_report, session_quality
from agentprov.cli.live.worker import BackendWorker, WorkerDied, WorkerSpec, WorkerTimeout, make_private_dir
from agentprov.errors import AgentProvError, IdentityMismatch
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent

__all__ = ["AttackStaging", "AttemptResult", "Campaign", "Slot", "Task", "unit_key"]

_LOG = logging.getLogger(__name__)
SCRIPT_LABEL: Final = "llm-script.json"
CONCLUSIVE_ACCOUNTING: Final = frozenset({"consistent", "unverifiable"})
HELLO_TIMEOUT_S: Final = 300.0


#: The worker's refusal type for a configuration the harness does not run (``agentprov_backend.attacks``); raised while a
#: cell is set up, it is recorded as a fatal ``error`` event with ``where: setup``.
SETUP_REFUSAL_TYPE: Final = "UnsupportedConfiguration"
SETUP_REFUSAL_MAX_CHARS: Final = 300


def setup_refusal(log: bytes, *, limits: Any = None) -> str | None:
    """The message of a fatal ``UnsupportedConfiguration`` raised at cell setup in one capture log, else ``None``
    (strict, bounded parsing; the message is T2 output, so the caller shows it only through ``safe_text``)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    limits = limits or IngestLimits()
    for line in log.split(b"\n"):
        if not line:
            continue
        try:
            event = strict_json_loads(line, limits, record=True)
        except IngestError:
            continue
        if not isinstance(event, Mapping) or event.get("type") != "error" or not isinstance(event.get("data"), Mapping):
            continue
        data = event["data"]
        exc = data.get("exception")
        if data.get("fatal") is True and data.get("where") == "setup" and isinstance(exc, Mapping) \
                and exc.get("type") == SETUP_REFUSAL_TYPE:
            message = exc.get("message")
            return message[:SETUP_REFUSAL_MAX_CHARS] if isinstance(message, str) else SETUP_REFUSAL_TYPE
    return None


def unit_key(cell_key: str, config_digest: str, repeat: int) -> tuple[str, str, int]:
    """The live unit key of N.1.8(1)."""
    return (cell_key, config_digest, repeat)


@dataclass(frozen=True)
class AttackStaging:
    """A file T0 stages into every session of a cell running ``attack`` before ``run_cell`` (D.11.3 rule 5; the AutoDojo
    cache, D.11.7 item 5): ``label`` inside the session directory, the verified ``data`` and its ``sha256``, the
    ``run_cell.attack_env`` members, and the ``origin`` the raw store and the AER record for it (the pinned fork tree)."""

    attack: str
    label: str
    data: bytes = field(repr=False)
    sha256: str
    env: Mapping[str, Any]
    origin: Any

    def stage(self, session_dir: Path) -> None:
        """Write the file fresh under directories created 0700: ``O_CREAT|O_EXCL`` (0600) fails on any existing entry,
        a link included, so nothing is followed; the session directory itself is fresh and 0700 (``make_private_dir``)."""
        import os

        target = session_dir.joinpath(*self.label.split("/"))
        current = session_dir
        for part in self.label.split("/")[:-1]:
            current = current / part
            os.mkdir(current, 0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(target, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.data)


@dataclass(frozen=True)
class Task:
    cell: Mapping[str, Any]
    repeat: int
    attempt: int

    @property
    def cell_key(self) -> str:
        return str(self.cell["cell_key"])


@dataclass
class AttemptResult:
    task: Task
    session: str
    session_dir: Path
    status: str  # claimed (cell_done) or "aborted" (killed / died)
    reported: list[dict[str, Any]] | None
    parent_appended: bool = False
    note: str | None = None


class Slot:
    """One backend worker and its private directories. Respawned on demand."""

    def __init__(self, index: int, campaign: Campaign) -> None:
        self.index = index
        self.campaign = campaign
        self.worker: BackendWorker | None = None
        self.started_cells = 0
        self.hello: dict[str, Any] | None = None
        self.dirs: list[Path] = []

    def ensure(self) -> BackendWorker:
        if self.worker is not None and self.worker.alive:
            return self.worker
        self.reset()
        c = self.campaign
        name = f"worker-{uuid.uuid4().hex[:16]}"
        cwd = make_private_dir(c.staging_root / name)
        home = make_private_dir(c.t2home_root / name)
        self.dirs += [cwd, home]
        worker = BackendWorker(WorkerSpec(argv=c.argv, env=c.env_for(home), cwd=cwd, stderr_path=cwd / "worker.stderr.log"),
                               on_step=c.on_step)
        worker.start()
        self.worker = worker
        nonce = uuid.uuid4().hex
        try:
            hello = worker.request("hello", "hello_ok", HELLO_TIMEOUT_S, nonce=nonce, expect=c.expect)
        except (WorkerDied, WorkerTimeout) as exc:
            self.reset()
            raise AgentProvError(f"the backend worker did not answer hello: {exc}", code="backend.unavailable",
                                 exit_code=3) from None
        if hello.get("nonce") != nonce:
            self.reset()
            raise IdentityMismatch("IdentityMismatch: hello_ok answered another nonce")
        check_hello(hello, c.identity, c.marker, backend=c.backend)
        self.hello = hello
        return worker

    @property
    def stderr_files(self) -> list[Path]:
        return [d / "worker.stderr.log" for d in self.dirs if d.parent == self.campaign.staging_root]

    def reset(self) -> None:
        if self.worker is not None:
            self.worker.kill()
            self.worker.close()
            self.worker = None

    def shutdown(self) -> None:
        if self.worker is not None:
            self.worker.shutdown()
            self.worker = None


@dataclass
class Ledger:
    """``live.sessions`` of the working manifest: one entry per attempt, in the order attempts finished."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def attempts(self, key: tuple[str, str, int]) -> list[dict[str, Any]]:
        return [e for e in self.entries if (e["cell_key"], e["config_digest"], e["repeat"]) == key]

    def conclusive(self, key: tuple[str, str, int]) -> bool:
        """Some attempt ended ``complete`` with accounting ``consistent`` or ``unverifiable`` (N.1.8(4))."""
        return any(e.get("status") == "complete" and e.get("accounting") in CONCLUSIVE_ACCOUNTING
                   and not e.get("capture_error") for e in self.attempts(key))

    def inconsistent(self, key: tuple[str, str, int]) -> bool:
        """Some attempt ended ``complete`` with accounting ``inconsistent``."""
        return any(e.get("status") == "complete" and e.get("accounting") == "inconsistent" and not e.get("capture_error")
                   for e in self.attempts(key))

    def settled(self, key: tuple[str, str, int], retry_inconsistent: bool) -> bool:
        """No further attempt is due: conclusive, or inconsistent without ``--retry-inconsistent``."""
        return self.conclusive(key) or (self.inconsistent(key) and not retry_inconsistent)


class Campaign:
    def __init__(
        self,
        *,
        pipeline: Any,
        writer: Any,
        argv: Sequence[str],
        env_for: Callable[[Path], dict[str, str]],
        identity: EnvIdentity,
        marker: Mapping[str, Any],
        expect: Mapping[str, Any],
        home: Path,
        agent: Mapping[str, Any],
        plan: Mapping[str, Any],
        config_digest: str,
        jobs: int,
        start_stagger: float,
        cell_timeout: float,
        max_attempts: int,
        retry_inconsistent: bool,
        repeats: int,
        canary: int,
        limit: int | None,
        script: bytes | None,
        redactor: Any,
        snapshot_id: str,
        ledger: Ledger,
        progress: Progress = NULL_PROGRESS,
        keep_staging: bool = False,
        backend: str = "agentdojo",
        attack_staging: AttackStaging | None = None,
        observe_local: Callable[[], dict[str, Any]] | None = None,
        accepted_served: Sequence[str] = (),
        budget: Any = None,
    ) -> None:
        self.keep_staging = keep_staging
        self.budget = budget
        self.cap_stop: str | None = None
        #: ``<cell_key>: <message>`` of the first setup refusal (no further cell starts); see :func:`setup_refusal`
        self.config_stop: str | None = None
        self.backend = backend
        self.attack_staging = attack_staging
        #: D-693: T0's per-cell re-observation of a local model (None for a remote or scripted endpoint)
        self.observe_local = observe_local
        self.accepted_served = tuple(accepted_served)  # D-694: served ids the operator accepted (A12)
        self.pipeline, self.writer = pipeline, writer
        self.argv, self.env_for = list(argv), env_for
        self.identity, self.marker, self.expect = identity, marker, dict(expect)
        self.staging_root = home / "staging"
        self.t2home_root = home / "t2home"
        self.agent, self.plan, self.config_digest = dict(agent), plan, config_digest
        self.jobs, self.start_stagger, self.cell_timeout = jobs, start_stagger, cell_timeout
        self.max_attempts, self.retry_inconsistent, self.repeats = max_attempts, retry_inconsistent, repeats
        self.canary, self.limit, self.script, self.redactor = canary, limit, script, redactor
        self.snapshot_id = snapshot_id
        self.ledger = ledger
        self.progress = progress
        self.qualities: list[SessionQuality] = []
        self.notices: list[str] = []
        self.drained = False
        self.counters: dict[str, int] = {k: 0 for k in (
            "cells_planned", "cells_done_before", "attempted", "conclusive", "inconsistent", "inconclusive", "derived",
            "failed", "quarantined", "rejected_files", "unreported_files")}  # fmt: skip
        self.canary_stop: list[str] = []
        self._req = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()  # set when the campaign stops: no unit starts after it (N.1.10(2))
        self.slots = [Slot(i, self) for i in range(jobs)]
        self._free: list[Slot] = list(self.slots)
        self.on_step = self._on_step

    # -------------------------------------------------------------------------------------- feedback
    def _on_step(self, msg: Mapping[str, Any]) -> None:
        kind = msg.get("kind") if msg.get("op") == "step" else "progress"
        fields = {k: v for k, v in msg.items() if k not in ("v", "op") and isinstance(v, str | int | bool) and not isinstance(v, float)}
        self.progress.emit(ProgressEvent("step", stage=str(kind)[:32], fields={k: fields[k] for k in sorted(fields)[:12]}))

    # -------------------------------------------------------------------------------------- one attempt (worker thread)
    def _run_attempt(self, slot: Slot, task: Task) -> AttemptResult | None:
        """One attempt; ``None`` when the campaign stopped before it started (nothing was created or run)."""
        if slot.started_cells == 0 and self.start_stagger > 0 and self.jobs > 1:
            self._stop.wait(slot.index * self.start_stagger / self.jobs)
        if self._stop.is_set():
            return None
        session = str(uuid.uuid7())
        session_dir = make_private_dir(self.staging_root / session)
        self.progress.emit(ProgressEvent("session", unit=task.cell_key, fields={  # D-393: a live preview finds the log
            "session": session, "attempt": task.attempt, "phase": "start", "staging": f"staging/{session}"}))
        if self.script is not None:
            (session_dir / SCRIPT_LABEL).write_bytes(self.script)
        attack_env: dict[str, Any] = {}
        staging = self.attack_staging
        if staging is not None and task.cell.get("attack") == staging.attack:
            staging.stage(session_dir)  # before run_cell; the worker re-hashes it against the cell's attack_params
            attack_env = dict(staging.env)
        local_model = self.observe_local() if self.observe_local is not None else None
        slot.started_cells += 1
        worker = slot.ensure()
        if self._stop.is_set():  # stopped while the worker was spawned: the stop path may have reset the slot already
            slot.reset()
            shutil.rmtree(session_dir, ignore_errors=True)
            return None
        with self._lock:
            self._req += 1
            req = self._req
        self.progress.emit(ProgressEvent("unit_start", unit=task.cell_key))
        try:
            reply = worker.request(
                "run_cell", "cell_done", self.cell_timeout, req=req, cell=dict(task.cell), agent=self.agent,
                session={"ex": "ex_" + session, "attempt": task.attempt, "dir": str(session_dir)},
                plan_sha256=self.plan["plan_sha256"], backend_config=dict(self.plan.get("backend_config") or {}),
                attack_env=attack_env, **({"local_model": local_model} if local_model is not None else {}),
            )  # fmt: skip
            status = reply.get("status")
            artefacts = reply.get("artefacts")
            if reply.get("req") != req or status not in ("complete", "incomplete", "errored", "aborted") or not isinstance(artefacts, list):
                raise WorkerDied("cell_done does not answer this run_cell")
            return AttemptResult(task, session, session_dir, str(status), [a for a in artefacts if isinstance(a, dict)])
        except (WorkerDied, WorkerTimeout) as exc:
            slot.reset()  # kill the tree; the next attempt gets a fresh worker (D.11.3 rule 3)
            appended = self._append_aborted(session_dir, session)
            note = "timeout" if isinstance(exc, WorkerTimeout) else "worker_died"
            return AttemptResult(task, session, session_dir, "aborted", None, appended, note)

    @staticmethod
    def _append_aborted(session_dir: Path, session: str) -> bool:
        """Continue the chain with the parent's terminal event, after checking the log path like any staged file."""
        from agentprov_capture.log import append_terminal

        from agentprov.errors import IngestError
        from agentprov.ingest.paths import open_evidence

        label = f"raw/capture/{session}.capture.jsonl"
        try:
            with open_evidence(session_dir, label, staging=True):
                pass
        except (IngestError, OSError):
            return False
        try:
            return append_terminal(session_dir / label, "aborted") is not None
        except Exception:  # noqa: BLE001 - a log the parent cannot extend stays unsealed; the mapper says so
            return False

    # -------------------------------------------------------------------------------------- ingest (main thread)
    def _ingest(self, result: AttemptResult) -> dict[str, Any]:
        task = result.task
        files = st.collect_session(result.session_dir, result.session, result.reported, parent_files={SCRIPT_LABEL},
                                   limits=self.pipeline.limits)
        stderr = [p for s in self.slots for p in s.stderr_files]
        hits = st.scan_secrets(result.session_dir, self.redactor, extra_files=stderr, limits=self.pipeline.limits)
        if self.redactor is not None:  # the bytes that will be stored, as read: no name the walk skips, no second read
            hits += [f.label for f in files.files if f.label not in hits and self.redactor.contains_secret(f.data)]
        entry: dict[str, Any] = {
            "session": result.session, "ex": "ex_" + result.session, "cell_key": task.cell_key,
            "config_digest": self.config_digest, "repeat": task.repeat, "attempt": task.attempt,
            "status": None, "accounting": None, "capture_sha256": None, "index_status": None,
            "parent_appended": result.parent_appended,
        }  # fmt: skip
        log = files.capture_log
        if self.budget is not None:  # D-725: billed whether or not it is stored (a quarantined session was billed too)
            from agentprov.cli.live.policy import log_billing

            self.budget.charge(log_billing(log.data if log is not None else None, limits=self.pipeline.limits),
                               label=task.cell_key)
        if log is not None and self.config_stop is None:
            refusal = setup_refusal(log.data, limits=self.pipeline.limits)
            if refusal is not None:
                self.config_stop = f"{task.cell_key}: {refusal}"
        poisoned = log is not None and st.redaction_failed(log.data, self.pipeline.limits)
        if hits or poisoned:
            # G.6.4: nothing from the session is stored; the directory stays for the user (never printed). A failed
            # redaction scan in the worker (D-290) quarantines too: the staged files beside the log are not redacted
            reasons = []
            if hits:
                reasons.append(f"literal secret value found in {len(hits)} staged file(s)")
            if poisoned:
                reasons.append("the worker's redaction scan failed (capture log sealed errored by capture.redact)")
            self.pipeline._register({"snapshot_id": self.snapshot_id, "path": result.session}, "capture.quarantined",
                                    severity="error", stage="capture", disposition="not_imported",
                                    detail="; ".join(reasons) + "; session kept in staging")
            self.pipeline._fail({"path": result.session}, "capture", "capture.quarantined",
                                "secret value in staged files" if hits else "redaction scan failed in the worker")
            self.counters["quarantined"] += 1
            what = "a secret value was found in staged files" if hits else "the worker's redaction scan failed"
            self.notices.append(f"session {result.session} quarantined: {what}; nothing was stored and the staging "
                                "directory was kept")
            return {**entry, "status": "quarantined"}
        if log is not None:
            hello = next((s.hello for s in self.slots if s.hello is not None), None)
            if hello is not None:
                st.check_capture_identity(log.data, hello["identity"], self.pipeline.limits, backend=self.backend)
        for label, code, detail in files.rejected:
            self.pipeline._register({"snapshot_id": self.snapshot_id, "path": f"{result.session}/{label}"[:400]}, code,
                                    severity="error", stage="ingest", disposition="not_imported", detail=detail)
            self.counters["rejected_files"] += 1
        if files.unreported:
            self.counters["unreported_files"] += len(files.unreported)
            self.notices.append(f"session {result.session}: {len(files.unreported)} unreported file(s) ignored")
        extra = [("map.capture_error", "error", "map", f"reported artefact does not verify: {label}"[:200])
                 for label in files.mismatches]
        origins = {}
        staging = self.attack_staging
        if staging is not None:  # the staged cache keeps its pinned origin; the capture origin is recorded as a mirror
            origins = {f.label: staging.origin for f in files.files if f.label == staging.label and f.sha256 == staging.sha256}
        outcome = self.pipeline.ingest(result.session, task.attempt, [(f.label, f.data) for f in files.files], extra,
                                       origins=origins)
        quality = SessionQuality(session=result.session, cell_key=task.cell_key)
        if log is not None:
            data = {f.sha256: f.data for f in files.files}
            quality = session_quality(result.session, log.data, data.get, limits=self.pipeline.limits)
            quality.cell_key = quality.cell_key or task.cell_key
        self.qualities.append(quality)
        entry.update(status=quality.status if log is not None else None, accounting=outcome.accounting,
                     capture_sha256=log.sha256 if log is not None else None, index_status=outcome.status,
                     capture_error=bool(files.mismatches or files.rejected))
        if result.note:
            entry["parent_note"] = result.note
        if not (files.mismatches or files.rejected):
            if not self.keep_staging:
                shutil.rmtree(result.session_dir, ignore_errors=True)
        else:
            self.notices.append(f"session {result.session}: staging kept (rejected or unverified artefacts)")
        self.progress.emit(ProgressEvent("session", unit=task.cell_key, fields={
            "session": result.session, "attempt": task.attempt, "phase": "end", "status": str(entry.get("status"))}))
        return entry

    # -------------------------------------------------------------------------------------- scheduling
    def _next(self, cell: Mapping[str, Any], repeat: int) -> Task | None:
        key = unit_key(str(cell["cell_key"]), self.config_digest, repeat)
        if self.ledger.settled(key, self.retry_inconsistent):
            return None
        done = len(self.ledger.attempts(key))
        return None if done >= self.max_attempts else Task(cell, repeat, done)

    def _drive(self, units: Sequence[tuple[Mapping[str, Any], int]], executor: ThreadPoolExecutor,
               futures: dict[Future[AttemptResult | None], Slot], write_documents: Callable[[], None]) -> list[SessionQuality]:
        """Run ``units`` to the end (re-attempts included); returns the qualities of the sessions ingested."""
        queue_ = list(units)
        out: list[SessionQuality] = []

        def submit(task: Task) -> bool:
            if self.config_stop is not None:  # a setup refusal fails every cell alike: start nothing more
                return False
            if self.limit is not None and self.counters["attempted"] + len(futures) >= self.limit:
                return False
            if self.budget is not None:  # D-725: the worst case of this cell and of those in flight must fit the caps
                reason = self.budget.refusal(len(futures))
                if reason is not None:
                    self.cap_stop = self.cap_stop or reason
                    return False
            slot = self._free.pop()
            futures[executor.submit(self._run_attempt, slot, task)] = slot
            return True

        while queue_ or futures:
            if queue_ and drain.draining():  # D-394: no new attempt; the in-flight ones finish and are ingested
                self.drained = True
                queue_.clear()
            while queue_ and self._free:
                cell, repeat = queue_.pop(0)
                task = self._next(cell, repeat)
                if task is not None and not submit(task):
                    queue_.clear()
            if not futures:
                break
            done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
            for future in done:
                self._free.append(futures.pop(future))
                result = future.result()
                if result is None:
                    continue
                self.counters["attempted"] += 1
                entry = self._ingest(result)
                self.ledger.entries.append(entry)
                write_documents()
                if entry["status"] != "quarantined":
                    out.append(self.qualities[-1])
                    queue_.insert(0, (result.task.cell, result.task.repeat))  # a re-attempt, if one is due
        return out

    def run(self, cells: Sequence[Mapping[str, Any]], *, write_documents: Callable[[], None]) -> None:
        drain.drain_supported()  # D-394: _drive checks it before each scheduling round
        if self.budget is not None:  # D-725: the caps are per corpus, so earlier attempts (resume) count
            self.budget.charge_all((self._stored_log(e) for e in self.ledger.entries), limits=self.pipeline.limits)
        units = [(cell, r) for cell in cells for r in range(self.repeats)]
        self.counters["cells_planned"] = len(units)
        keys = [unit_key(str(cell["cell_key"]), self.config_digest, r) for cell, r in units]
        before = {k for k in keys if self.ledger.settled(k, self.retry_inconsistent)}
        self.counters["cells_done_before"] = len(before)
        pending = [u for u, k in zip(units, keys, strict=True) if k not in before]
        self.progress.emit(ProgressEvent("start", total=len(pending), fields={
            "command": "run", "backend": self.backend, "workers": self.jobs, "plan": f"{len(units)} unit(s)"}))
        executor = ThreadPoolExecutor(max_workers=self.jobs, thread_name_prefix="agentprov-live")
        futures: dict[Future[AttemptResult | None], Slot] = {}
        try:
            canary, rest = pending[: self.canary], pending[self.canary :]
            if canary:
                found = canary_conditions(self._drive(canary, executor, futures, write_documents),
                                          accepted_served=self.accepted_served)
                if found and rest:
                    self.canary_stop = found
                    rest = []
                elif found:
                    self.notices.extend(f"canary condition (every cell ran): {c}" for c in found)
            if rest and not drain.draining() and self.cap_stop is None and self.config_stop is None:
                self._drive(rest, executor, futures, write_documents)
            if drain.draining():
                self.drained = True
                self.notices.append("drained (--control-file): in-flight attempts finished, no new one started; re-run "
                                    "the same command to resume")
        except KeyboardInterrupt:
            self._stop.set()  # first: a slot still in its start stagger never starts
            for slot in self.slots:
                slot.reset()  # the in-flight attempts return "aborted" with the parent's terminal event
            for future in list(futures):
                try:
                    result = future.result(timeout=60)
                except Exception:  # noqa: BLE001
                    continue
                if result is None:
                    continue
                self.counters["attempted"] += 1
                self.ledger.entries.append(self._ingest(result))
            write_documents()
            raise
        except BaseException:
            # a campaign-aborting error (an identity mismatch, a worker that fails hello): the other in-flight workers
            # are killed, not waited for (N.1.10(4)); their sessions stay in staging, unledgered, for the user
            self._stop.set()
            for slot in self.slots:
                slot.reset()
            raise
        finally:
            executor.shutdown(wait=True)
            self._close_slots()
        touched = [k for k in keys if k not in before and self.ledger.attempts(k)]
        for key in touched:
            if self.ledger.conclusive(key):
                self.counters["conclusive"] += 1
            elif self.ledger.inconsistent(key):
                self.counters["inconsistent"] += 1
            else:
                self.counters["inconclusive"] += 1
        self.counters["derived"] = int(self.pipeline.counters["derived"])
        self.counters["failed"] = int(self.pipeline.counters["failed"]) + self.counters["quarantined"]

    def _close_slots(self) -> None:
        for slot in self.slots:
            slot.shutdown()
            for d in slot.dirs:
                if d.parent == self.t2home_root:
                    try:
                        empty = not any(d.iterdir())
                    except OSError:
                        continue
                    if not empty:
                        self.notices.append(f"the T2 home {d.name} is not empty (kept for inspection)")
                        continue
                shutil.rmtree(d, ignore_errors=True)

    def report(self) -> dict[str, Any]:
        """``live.quality`` (D.10.9; N.2.1b item 12): rebuilt from every ledgered session's stored capture log, so it is
        a pure function of the corpus whatever this invocation ingested (D-542). A quarantined session stored nothing
        and is not counted; a session without a capture log counts with no facts."""
        per_cell: dict[str, int] = {}
        qualities: list[SessionQuality] = []
        for e in self.ledger.entries:
            k = f"{e['cell_key']}#{e['repeat']}"
            per_cell[k] = per_cell.get(k, 0) + 1
            if e.get("status") == "quarantined":
                continue
            qualities.append(self._stored_quality(e))
        return quality_report(qualities, per_cell)

    def _stored_log(self, entry: Mapping[str, Any]) -> bytes | None:
        """One ledgered session's stored capture log (``None``: none stored, e.g. a quarantined session)."""
        sha = entry.get("capture_sha256")
        if not isinstance(sha, str):
            return None
        try:
            data: bytes = self.writer.store.read_bytes(sha)
        except (KeyError, OSError):
            return None
        return data

    def _stored_quality(self, entry: Mapping[str, Any]) -> SessionQuality:
        """One ledgered session's quality facts, read from the raw store (``capture_sha256``) as ``_ingest`` reads them."""
        store = self.writer.store
        sha = entry.get("capture_sha256")
        if not isinstance(sha, str):
            return SessionQuality(session=str(entry["session"]), cell_key=str(entry["cell_key"]))

        def read(digest: str) -> bytes | None:
            try:
                return store.read_bytes(digest)
            except (KeyError, OSError):
                return None

        log = read(sha)
        if log is None:
            return SessionQuality(session=str(entry["session"]), cell_key=str(entry["cell_key"]))
        quality = session_quality(str(entry["session"]), log, read, limits=self.pipeline.limits)
        quality.cell_key = quality.cell_key or str(entry["cell_key"])
        return quality
