"""The capture/0.1 log writer (C.13.1, C.13.2, C.13.6) and the parent-side terminal append.

``CaptureLog`` writes one session: an append-only file of ``JCS(event) + LF`` lines hash-chained through ``prev``,
plus content-addressed blobs. Rules it enforces:

* **Append-only.** The log file is opened ``O_APPEND`` (a symbolic link is refused) and **must be empty or absent**: a non-empty file raises
  ``cap.log.exists`` and is never truncated or extended (resume decisions key on sealed evidence, C.13.2).
* **Order.** The first event is ``session.start``, the second ``instrumentation``; ``session.end`` is written by
  :meth:`CaptureLog.close` only. An event's ``actor`` must be declared in ``session.start.actors``.
* **Write discipline** (C.13.6). A blob is written atomically (temporary file in the same directory, ``fsync``,
  rename) *before* any event that references it is written, and an event may only reference blobs that exist. Each
  event is one ``write`` of its whole line; ``pass.end`` and ``session.end`` are ``fsync``ed.
* **Redaction, fail closed** (G.6.4). With a :class:`~agentprov_capture.redact.Redactor`, every event and blob is
  redacted before it is written and every final line is re-scanned. If redaction fails in any way the event (or
  blob) is **not written**, :class:`RedactionError` is raised, and the log is *poisoned*: further ``emit`` and
  ``put_blob`` calls raise ``cap.log.poisoned``; :meth:`CaptureLog.close` then writes a constant ``error`` event
  (``where: "capture.redact"``, ``fatal: true``, no content of the failed event) followed by
  ``session.end`` with status ``errored`` whatever status was requested. Without a redactor nothing is scanned
  (tests only; live runs always pass one).
* **Pattern flags.** A key-shaped pattern found in content is not rewritten; the writer follows the referencing
  event with a ``note`` (``ns: "capture"``, ``kind: "secret_pattern"``, payload ``{event_seq, field, p, pattern}``
  or ``{blob, p, pattern}``; once per blob). These notes take sequence numbers of their own, so use ``emit``'s
  return value rather than counting.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

import rfc8785

from .errors import CaptureLogError, CaptureWriteError, RedactionError
from .events import (
    ACTOR_TAG_RE,
    APPENDED_BY,
    BLOB_DIGEST_RE,
    EVENT_TYPES,
    SESSION_STATUSES,
    BlobRef,
    data_problem,
    format_ts,
    is_blob_ref,
)
from .redact import Redactor
from .verify import DEFAULT_MAX_BYTES, line_hash, split_lines, strict_loads

__all__ = ["CaptureLog", "append_terminal"]

_FSYNC_TYPES: Final = frozenset({"pass.end", "session.end"})
#: Windows opens descriptors in text mode by default, so `os.write` would turn LF into CRLF and break every line
#: hash and blob size; 0 elsewhere.
_BINARY: Final = getattr(os, "O_BINARY", 0)
_tmp_counter = itertools.count()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _refuse_symlink(path: Path) -> None:
    """The log is created or extended in a staging directory the parent made; a symlink in its place is refused."""
    if path.is_symlink():
        raise CaptureLogError("capture log path is a symbolic link", code="cap.log.symlink")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _canonical_line(event: Mapping[str, Any]) -> bytes:
    try:
        return rfc8785.dumps(event) + b"\n"
    except Exception:  # noqa: BLE001 - rfc8785 raises its own error types for non-I-JSON values
        raise CaptureWriteError("event is not canonicalisable (I-JSON: str keys, finite floats, ints within 2^53)", code="cap.write.not_canonical") from None


def _blob_refs(node: Any, out: list[Mapping[str, Any]], depth: int = 0) -> None:
    if depth > 200:
        raise CaptureWriteError("event nesting is too deep", code="cap.write.invalid")
    if isinstance(node, dict):
        if is_blob_ref(node):
            out.append(node)
            return
        for value in node.values():
            _blob_refs(value, out, depth + 1)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _blob_refs(value, out, depth + 1)


class CaptureLog:
    """Writer of one capture session (see the module docstring for the rules).

    ``path``: the log file (must be absent or empty). ``session``: the session id (UUIDv7); ``session.start`` must
    carry the same value. ``blobs_dir``: the directory holding ``sha256/<hex[0:2]>/<hex>``. ``clock`` returns an aware
    ``datetime`` (default: now, UTC) and is called once per event; ``mono_ns`` returns monotonic nanoseconds (default
    ``time.monotonic_ns``) and is called once per event, its first call (at ``session.start``) being the origin.
    """

    def __init__(
        self,
        path: Path,
        session: str,
        *,
        blobs_dir: Path,
        clock: Callable[[], datetime] | None = None,
        mono_ns: Callable[[], int] | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        import time

        self.path = Path(path)
        self.session = session
        self.blobs_dir = Path(blobs_dir)
        self._clock = clock or _utcnow
        self._mono = mono_ns or time.monotonic_ns
        self._redactor = redactor
        self._lock = threading.RLock()
        self._seq = 0
        self._prev: str | None = None
        self._head: str | None = None
        self._origin: int | None = None
        self._actors: frozenset[str] = frozenset()
        self._closed = False
        self._poison: tuple[str, str] | None = None  # (reason, detail)
        self._poison_logged = False
        self._blob_redactions: dict[str, dict[tuple[str, str], None]] = {}
        self._blob_flags: dict[str, dict[tuple[str, str], None]] = {}
        self._flags_noted: set[tuple[str, str, str]] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _refuse_symlink(self.path)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | _BINARY, 0o600)
        try:
            if os.fstat(fd).st_size != 0:
                raise CaptureLogError("capture log exists and is not empty; it is append-only and never reopened", code="cap.log.exists")
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    # -- state ------------------------------------------------------------------------------------------------

    @property
    def head(self) -> str | None:
        """SHA-256 (hex) of the last line written, or ``None`` before the first event."""
        return self._head

    @property
    def n_events(self) -> int:
        return self._seq

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def poisoned(self) -> bool:
        """True after a redaction failure: nothing more can be emitted and :meth:`close` will seal ``errored``."""
        return self._poison is not None

    def _check_open(self) -> None:
        if self._closed:
            raise CaptureLogError("capture log is closed", code="cap.log.closed")
        if self._poison is not None:
            raise CaptureLogError(
                "capture log is poisoned by a failed redaction scan or write; close() it", code="cap.log.poisoned"
            )

    def _poison_now(self, reason: str, detail: str) -> None:
        if self._poison is None:
            self._poison = (reason, detail)

    # -- blobs ------------------------------------------------------------------------------------------------

    def put_blob(self, data: bytes, media: str, *, non_content: bool | None = None) -> BlobRef:
        """Store ``data`` (after redaction, if a redactor is set) and return its reference.

        Atomic (temporary file + rename) and idempotent. ``non_content`` marks a traceback or stderr dump (key
        patterns are then redacted, not just flagged); ``None`` decides by ``media``.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise CaptureWriteError("blob data must be bytes", code="cap.write.invalid")
        if not isinstance(media, str) or not media:
            raise CaptureWriteError("blob media must be a non-empty string", code="cap.write.invalid")
        payload = bytes(data)
        with self._lock:
            self._check_open()
            redactions: tuple[tuple[str, str], ...] = ()
            flags: tuple[tuple[str, str], ...] = ()
            if self._redactor is not None:
                try:
                    result = self._redactor.redact_blob(payload, media, non_content=non_content)
                except Exception as exc:  # noqa: BLE001 - fail closed on any scan problem
                    self._poison_now("redaction", type(exc).__name__)
                    raise RedactionError("blob redaction failed; the blob was not written", code="cap.redact.failed") from None
                payload, redactions, flags = result.data, result.redactions, result.flags
            digest = hashlib.sha256(payload).hexdigest()
            self._store_blob(digest, payload)
            if redactions:
                self._blob_redactions.setdefault(digest, {}).update(dict.fromkeys(redactions))
            if flags:
                self._blob_flags.setdefault(digest, {}).update(dict.fromkeys(flags))
            return {"$blob": f"sha256:{digest}", "bytes": len(payload), "media": media}

    def _store_blob(self, digest: str, payload: bytes) -> None:
        target = self.blobs_dir / "sha256" / digest[:2] / digest
        if target.exists():
            if target.stat().st_size != len(payload):
                raise CaptureWriteError("blob store holds different bytes under this digest", code="cap.blob.collision")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{digest}.{os.getpid()}.{next(_tmp_counter)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)  # O_EXCL refuses a symlink
        try:
            try:
                _write_all(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, target)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def _check_blob_refs(self, payload: Mapping[str, Any]) -> list[str]:
        refs: list[Mapping[str, Any]] = []
        _blob_refs(payload, refs)
        digests: list[str] = []
        for ref in refs:
            value = ref.get("$blob")
            size = ref.get("bytes")
            if (
                not isinstance(value, str)
                or BLOB_DIGEST_RE.fullmatch(value) is None
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size < 0
                or not set(ref) <= {"$blob", "bytes", "media"}
                or "bytes" not in ref
            ):
                raise CaptureWriteError("malformed blob reference", code="cap.write.invalid")
            hexdigest = value[len("sha256:") :]
            target = self.blobs_dir / "sha256" / hexdigest[:2] / hexdigest
            try:
                actual = target.stat().st_size
            except OSError:
                actual = -1
            if actual != size:
                raise CaptureWriteError("an event may only reference a blob already stored", code="cap.blob.missing")
            digests.append(hexdigest)
        return digests

    # -- events -----------------------------------------------------------------------------------------------

    def emit(
        self,
        type: str,  # noqa: A002 - the capture/0.1 field is called `type`
        data: dict[str, Any],
        *,
        pass_: int | None = None,
        actor: str | None = None,
        lex: dict[str, Any] | None = None,
    ) -> int:
        """Append one event and return its ``seq``.

        Raises ``CaptureWriteError`` (``cap.write.invalid``, ``cap.write.not_canonical``, ``cap.blob.missing``) before
        writing anything when the event violates the model, and ``RedactionError`` (poisoning the log) when a
        redactor is set and fails.
        """
        with self._lock:
            self._check_open()
            payload, flagged = self._prepare(type, data, pass_, actor)
            seq = self._write(type, payload, pass_, actor, lex)
            self._note_flags(seq, pass_, actor, flagged)
            return seq

    def _prepare(
        self, type_: str, data: Mapping[str, Any], pass_: int | None, actor: str | None
    ) -> tuple[dict[str, Any], list[tuple[str, dict[str, str]]]]:
        if type_ not in EVENT_TYPES:
            raise CaptureWriteError(f"unknown event type {type_!r}", code="cap.write.invalid")
        if type_ == "session.end":
            raise CaptureWriteError("session.end is written by close()", code="cap.write.invalid")
        if self._seq == 0 and type_ != "session.start":
            raise CaptureWriteError("the first event must be session.start", code="cap.write.invalid")
        if self._seq > 0 and type_ == "session.start":
            raise CaptureWriteError("session.start is only valid as the first event", code="cap.write.invalid")
        if self._seq == 1 and type_ != "instrumentation":
            raise CaptureWriteError("the second event must be instrumentation", code="cap.write.invalid")
        if self._seq > 1 and type_ == "instrumentation":
            raise CaptureWriteError("instrumentation is only valid as the second event", code="cap.write.invalid")
        if pass_ is not None and (isinstance(pass_, bool) or not isinstance(pass_, int) or pass_ < 0):
            raise CaptureWriteError("pass_ must be a non-negative integer or None", code="cap.write.invalid")
        if actor is not None and actor not in self._actors:
            raise CaptureWriteError(f"actor {actor!r} is not declared in session.start", code="cap.write.invalid")
        problem = data_problem(type_, data)
        if problem is not None:
            raise CaptureWriteError(problem, code="cap.write.invalid")
        payload = dict(data)
        if type_ == "session.start":
            actors = payload["actors"]
            if (
                payload["capture"] != "0.1"
                or payload["session"] != self.session
                or not isinstance(actors, Mapping)
                or not actors
                or not all(isinstance(t, str) and ACTOR_TAG_RE.fullmatch(t) for t in actors)
            ):
                raise CaptureWriteError(
                    "session.start needs capture 0.1, this log's session id and a non-empty actors table",
                    code="cap.write.invalid",
                )
            if actor is not None:
                raise CaptureWriteError("session.start has no actor", code="cap.write.invalid")
        digests = self._check_blob_refs(payload)
        flagged: list[tuple[str, dict[str, str]]] = []
        if self._redactor is not None:
            try:
                result = self._redactor.redact_event(type_, payload)
                payload = dict(result.data)
                entries = [dict(e) for e in result.redactions]
                for digest in dict.fromkeys(digests):
                    for p, rule in self._blob_redactions.get(digest, {}):
                        entries.append({"blob": f"sha256:{digest}", "p": p, "rule": rule})
                    for p, pattern in self._blob_flags.get(digest, {}):
                        key = (digest, p, pattern)
                        if key not in self._flags_noted:
                            self._flags_noted.add(key)
                            flagged.append(("blob", {"blob": f"sha256:{digest}", "p": p, "pattern": pattern}))
                for flag in result.flags:
                    flagged.append(("field", flag))
                existing = payload.get("redactions")
                merged = (list(existing) if isinstance(existing, list) else []) + entries
                unique = list({tuple(sorted(e.items())): e for e in merged}.values())
                if unique:
                    payload["redactions"] = unique
                else:
                    payload.pop("redactions", None)
            except Exception as exc:  # noqa: BLE001 - fail closed on any scan problem
                self._poison_now("redaction", type(exc).__name__)
                raise RedactionError("event redaction failed; the event was not written", code="cap.redact.failed") from None
        return payload, flagged

    def _write(
        self, type_: str, payload: dict[str, Any], pass_: int | None, actor: str | None, lex: Mapping[str, Any] | None
    ) -> int:
        """Build, scan and append one event line; commit state only after the write succeeded."""
        try:
            moment = self._clock()
            ts = format_ts(moment)
        except ValueError as exc:
            raise CaptureWriteError(str(exc), code="cap.write.invalid") from None
        now = self._mono()
        if isinstance(now, bool) or not isinstance(now, int):
            raise CaptureWriteError("mono_ns() must return an integer", code="cap.write.invalid")
        origin = now if self._origin is None else self._origin
        mono = now - origin
        if mono < 0:
            raise CaptureWriteError("mono_ns went backwards before the session origin", code="cap.write.invalid")
        seq = self._seq
        event: dict[str, Any] = {
            "seq": seq,
            "type": type_,
            "ts": ts,
            "mono_ns": mono,
            "pass": pass_,
            "actor": actor,
            "prev": self._prev,
            "data": payload,
        }
        if lex is not None:
            event["lex"] = lex
        line = _canonical_line(event)
        if self._redactor is not None:
            try:
                self._redactor.check_clean(line)
            except Exception as exc:  # noqa: BLE001 - fail closed
                self._poison_now("redaction", type(exc).__name__)
                raise RedactionError("final scan found a secret; the event was not written", code="cap.redact.residual") from None
        try:
            _write_all(self._fd, line)
            if type_ in _FSYNC_TYPES:
                os.fsync(self._fd)
        except OSError as exc:
            self._poison_now("io", type(exc).__name__)
            raise CaptureLogError(f"writing the capture log failed ({type(exc).__name__})", code="cap.log.io") from None
        self._seq = seq + 1
        self._prev = self._head = line_hash(line)
        self._origin = origin
        if type_ == "session.start":
            self._actors = frozenset(payload["actors"])
        return seq

    def _note_flags(self, seq: int, pass_: int | None, actor: str | None, flagged: list[tuple[str, dict[str, str]]]) -> None:
        for where, flag in flagged:
            if where == "field":
                payload = {"event_seq": seq, "field": flag["field"], "p": flag["p"], "pattern": flag["pattern"]}
            else:
                payload = dict(flag)
            self._write("note", {"kind": "secret_pattern", "ns": "capture", "payload": payload}, pass_, actor, None)

    # -- sealing ----------------------------------------------------------------------------------------------

    def close(self, status: str, *, appended_by: str = "worker") -> str:
        """Write ``session.end`` (``fsync``), close the file and return the chain head.

        ``status`` is ``complete``, ``incomplete``, ``errored`` or ``aborted``. After a failed redaction the status is
        forced to ``errored`` and a constant ``error`` event precedes ``session.end`` (see the module docstring).
        """
        if status not in SESSION_STATUSES:
            raise CaptureWriteError(f"unknown session status {status!r}", code="cap.write.invalid")
        if appended_by not in APPENDED_BY:
            raise CaptureWriteError(f"unknown appended_by {appended_by!r}", code="cap.write.invalid")
        with self._lock:
            if self._closed:
                raise CaptureLogError("capture log is already closed", code="cap.log.closed")
            if self._seq == 0:
                raise CaptureLogError("session.start was never written; nothing to seal", code="cap.log.not_started")
            if self._poison is not None:
                status = "errored"
                if not self._poison_logged:
                    reason, detail = self._poison
                    self._poison_logged = True
                    if reason == "redaction":
                        self._write(
                            "error",
                            {
                                "where": "capture.redact",
                                "exception": {"type": detail, "message": "redaction failed; the event or blob was not written"},
                                "fatal": True,
                            },
                            None,
                            None,
                            None,
                        )
            self._write(
                "session.end",
                {"status": status, "n_events": self._seq + 1, "appended_by": appended_by},
                None,
                None,
                None,
            )
            head = self._head
            assert head is not None
            self._closed = True
            os.close(self._fd)
            _fsync_dir(self.path.parent)
            return head

    def abandon(self) -> None:
        """Close the file handle without sealing (simulates a worker crash; the log stays unsealed)."""
        with self._lock:
            if not self._closed:
                self._closed = True
                os.close(self._fd)


def append_terminal(
    path: Path,
    status: Literal["aborted", "errored"],
    *,
    clock: Callable[[], datetime] | None = None,
) -> str | None:
    """Parent side (C.13.2): continue the chain of an unsealed log with ``session.end{status, n_events,
    appended_by: "parent"}`` and return the new chain head.

    Returns ``None`` and writes **nothing** when the log is empty, already sealed (its last event is ``session.end``),
    ends in a torn line (no LF), or its last line is not a strict-JSON event of the right shape. It checks only the last
    line (``verify_file`` checks the whole chain; a corrupt earlier chain stays reported by it). ``ts`` is the parent's
    clock; ``mono_ns`` repeats the last recorded value, because the parent has no access to the worker's monotonic
    origin and inventing one would fabricate a measurement. The caller must know the writer is dead.
    """
    if status not in ("aborted", "errored"):
        raise ValueError("a parent appends status aborted or errored")
    _refuse_symlink(Path(path))
    with open(path, "rb") as handle:
        data = handle.read(DEFAULT_MAX_BYTES + 1)
    if len(data) > DEFAULT_MAX_BYTES:
        raise CaptureLogError("capture log is too large to append to", code="cap.verify.too_large")
    if not data or not data.endswith(b"\n"):
        return None
    lines = split_lines(data)
    last = strict_loads(lines[-1][:-1])
    if (
        last is None
        or last.get("type") == "session.end"
        or last.get("seq") != len(lines) - 1
        or isinstance(last.get("mono_ns"), bool)
        or not isinstance(last.get("mono_ns"), int)
    ):
        return None
    moment = (clock or _utcnow)()
    event: dict[str, Any] = {
        "seq": len(lines),
        "type": "session.end",
        "ts": format_ts(moment),
        "mono_ns": last["mono_ns"],
        "pass": None,
        "actor": None,
        "prev": line_hash(lines[-1]),
        "data": {"status": status, "n_events": len(lines) + 1, "appended_by": "parent"},
    }
    line = _canonical_line(event)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | _BINARY)
    try:
        _write_all(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return line_hash(line)
