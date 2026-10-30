"""Ingesting one staged capture session (MN N.2.1 behaviour 3; D.10.0; D.11.3 rules 1-4; G.3.6; G.6.3; G.6.4).

T0 treats the session directory ``$AGENTPROV_HOME/staging/<session>/`` exactly like an ``--input`` tree written by an
untrusted party:

1. **Discovery** through :func:`agentprov.ingest.paths.discover`: no link is followed, special files and files with
   ``st_nlink != 1`` are rejected (``ingest.path.*``; ``--allow-hardlinks`` never applies to staging).
2. **Reported artefacts** (``cell_done.artefacts``) are *labels*: each passes :func:`~agentprov.ingest.names.logical_name`
   (a reported ``../x`` or absolute path is ``ingest.archive.traversal`` / ``ingest.name.invalid``), must lie under
   ``raw/``, and is opened only through :func:`~agentprov.ingest.paths.open_evidence` with ``staging=True`` (a symlink in
   any component, a special file or a hard link is rejected with its ``ingest.path.*`` code). Every reported file is
   re-hashed; a digest that differs from the report (or a blob whose content does not match its address) makes the cell
   ``errored`` and is ingested under its actual digest with the seal issue ``capture_error`` naming the label
   (D.11.3 rule 2). When the worker died before reporting, every regular file under ``raw/`` is the artefact set. A
   file's role follows its label (``raw/capture/<session>.capture.jsonl`` is the capture log), never the reported role,
   so a mislabelled report cannot keep the capture log from the checks of steps 4 and 5.
3. **Unreported files** are ignored (never stored) and reported. The parent's own files (the scripted-transport file)
   are not counted.
4. **Literal-value secret scan** (G.6.4, R-51) over *every* staged regular file and the worker's stderr file, with the
   values T0 read from ``.env`` and the secrets in its own environment: a hit quarantines the session (nothing from it
   is stored; the directory stays for the user to inspect; register ``capture.quarantined``). The value is never
   printed. A capture log the worker sealed after a **failed redaction scan** (its constant ``error`` event
   ``where: "capture.redact"``, C.13.10 item 6) quarantines the session the same way, whatever the literal scan finds
   (:func:`redaction_failed`; D-290): the log itself holds no content of the failed event, but the other staged files
   (the benchmark's native log in particular) are not written through the redactor.
5. **Identity** (D.11.3 rule 1): the capture log's ``identity`` event and its ``agentdojo/identity_digests`` note are
   compared with ``hello_ok``.

Nothing here maps: the verified files are handed back with their roles and digests, and the caller stores them with a
``capture {session}`` origin and maps them through the runner, like an import.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError, IdentityMismatch, IngestError

__all__ = ["ROLES", "SessionFiles", "StagedFile", "capture_identity", "collect_session", "redaction_failed",
           "scan_secrets"]

ROLES: Final = frozenset({"capture_log", "native_log", "blob", "supporting"})
_BLOB: Final = re.compile(r"raw/blobs/sha256/([0-9a-f]{2})/([0-9a-f]{64})")
_HEX64: Final = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class StagedFile:
    label: str
    sha256: str
    size: int
    role: str
    data: bytes = field(repr=False)


@dataclass
class SessionFiles:
    """The outcome of collecting one session directory."""

    session: str
    files: list[StagedFile] = field(default_factory=list)
    rejected: list[tuple[str, str, str]] = field(default_factory=list)  # (label, code, detail)
    unreported: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)  # labels whose digest did not verify (capture_error)
    reported: bool = True  # False: the worker died before cell_done, every raw/ file was taken

    @property
    def capture_log(self) -> StagedFile | None:
        logs = [f for f in self.files if f.role == "capture_log"]
        return logs[0] if len(logs) == 1 else None


def _role_for(label: str, session: str) -> str:
    if label == f"raw/capture/{session}.capture.jsonl":
        return "capture_log"
    if label == f"raw/capture/{session}.native.json":
        return "native_log"
    if label.startswith("raw/blobs/sha256/"):
        return "blob"
    return "supporting"


def collect_session(
    session_dir: Path,
    session: str,
    reported: Sequence[Mapping[str, Any]] | None,
    *,
    limits: Any = None,
    parent_files: Iterable[str] = (),
) -> SessionFiles:
    """Discover, check and read the session directory (steps 1-3 of the module docstring)."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.names import logical_name
    from agentprov.ingest.paths import discover, open_evidence, open_root

    limits = limits or IngestLimits()
    out = SessionFiles(session=session, reported=reported is not None)
    ignore = set(parent_files)
    with open_root(session_dir) as root:
        found = discover(root, limits)
        for rejection in found.rejected:
            out.rejected.append((rejection.label, rejection.code, rejection.detail))
        present = {f.label for f in found.files}
        wanted: dict[str, tuple[str | None, str]] = {}
        if reported is None:
            for label in sorted(present):
                if label.startswith("raw/"):
                    wanted[label] = (None, _role_for(label, session))
        else:
            for item in reported:
                label_raw, sha_raw, role_raw = item.get("label"), item.get("sha256"), item.get("role")
                if not isinstance(label_raw, str) or not isinstance(sha_raw, str) or not isinstance(role_raw, str):
                    out.rejected.append(("<malformed>", "ingest.name.invalid", "a reported artefact is not {label, sha256, role}"))
                    continue
                label, sha, role = label_raw, sha_raw, role_raw
                try:
                    name = logical_name(label, limits, portable=False)
                except IngestError as exc:
                    out.rejected.append((label[:200], exc.code, "reported label rejected"))
                    continue
                if not name.startswith("raw/") or role not in ROLES or not _HEX64.fullmatch(sha) or name in wanted:
                    out.rejected.append((name, "ingest.name.invalid", "reported artefact outside raw/, unknown role or bad digest"))
                    continue
                wanted[name] = (sha, _role_for(name, session))  # the label decides the role; the report only lists it
        for label, (expected, kind) in sorted(wanted.items()):
            try:
                with open_evidence(root, label, limits, staging=True) as stream:
                    data = stream.read()
            except IngestError as exc:
                if not any(r[0] == label for r in out.rejected):
                    out.rejected.append((label, exc.code, "reported artefact rejected"))
                continue
            except FileNotFoundError:
                out.mismatches.append(label)  # reported but absent: the report does not verify (D.11.3 rule 2)
                continue
            except OSError:
                out.rejected.append((label, "ingest.path.special", "reported artefact could not be opened"))
                continue
            actual = hashlib.sha256(data).hexdigest()
            if expected is not None and actual != expected:
                out.mismatches.append(label)
            blob = _BLOB.fullmatch(label)
            if blob and (blob.group(2) != actual or blob.group(1) != actual[:2]):
                if label not in out.mismatches:
                    out.mismatches.append(label)
            out.files.append(StagedFile(label, actual, len(data), kind, data))
        taken = set(wanted)
        rejected_labels = {r[0] for r in out.rejected}
        out.unreported = sorted(lbl for lbl in present if lbl not in taken and lbl not in ignore and lbl not in rejected_labels)
    return out


def scan_secrets(session_dir: Path, redactor: Any, *, extra_files: Iterable[Path] = (), limits: Any = None) -> list[str]:
    """Labels (or file names) of the staged files that hold a scanned secret value; ``[]`` when clean (G.6.4). Every
    regular file of the session directory is read through the no-follow opener; links are never followed (they are
    rejected anyway and never stored)."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.paths import discover, open_evidence, open_root

    if redactor is None:
        return []
    limits = limits or IngestLimits()
    hits: list[str] = []
    with open_root(session_dir) as root:
        for item in discover(root, limits).files:
            try:
                with open_evidence(root, item.label, limits, staging=True) as stream:
                    data = stream.read()
            except (IngestError, OSError):
                continue
            if redactor.contains_secret(data):
                hits.append(item.label)
    for path in extra_files:
        try:
            if path.is_file() and not path.is_symlink() and redactor.contains_secret(path.read_bytes()):
                hits.append(path.name)
        except OSError:
            continue
    return hits


#: The ``where`` of the constant ``error`` event ``CaptureLog.close`` writes after a failed redaction scan (C.13.10 item 6).
REDACTION_FAILED_WHERE: Final = "capture.redact"


def redaction_failed(log: bytes, limits: Any = None) -> bool:
    """True when the capture log holds the ``error`` event of a failed redaction scan (D-290). The log is untrusted:
    only lines that mention the marker are parsed (strict loader, bounded), and a line that does not parse is skipped
    (the mapper reports it)."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    marker = b'"' + REDACTION_FAILED_WHERE.encode() + b'"'
    if marker not in log:
        return False
    limits = limits or IngestLimits()
    for line in log.split(b"\n"):
        if marker not in line:
            continue
        try:
            event = strict_json_loads(line, limits, record=True)
        except IngestError:
            continue
        data = event.get("data") if isinstance(event, dict) and event.get("type") == "error" else None
        if isinstance(data, dict) and data.get("where") == REDACTION_FAILED_WHERE:
            return True
    return False


def capture_identity(log: bytes, limits: Any = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(identity event data, identity_digests note payload)`` from a capture log (strict loader, bounded; the log is
    untrusted). The note is ``agentdojo/identity_digests`` or, from an Inspect worker (D-663), ``inspect/identity_digests``.
    Either is ``None`` when absent or when a line before it does not parse."""
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    limits = limits or IngestLimits()
    identity: dict[str, Any] | None = None
    digests: dict[str, Any] | None = None
    for line in log.split(b"\n")[:64]:  # session.start, instrumentation, identity and the header notes come first
        if not line:
            continue
        try:
            event = strict_json_loads(line, limits, record=True)
        except IngestError:
            break
        if not isinstance(event, dict):
            break
        data = event.get("data")
        if event.get("type") == "identity" and isinstance(data, dict):
            identity = data
        elif event.get("type") == "note" and isinstance(data, dict) and data.get("ns") in _IDENTITY_NOTE_NS \
                and data.get("kind") == "identity_digests" and isinstance(data.get("payload"), dict):
            digests = data["payload"]
        if identity is not None and digests is not None:
            break
    return identity, digests


#: The namespaces of the identity_digests note: the AgentDojo-family workers and the Inspect worker (D-663).
_IDENTITY_NOTE_NS: Final = frozenset({"agentdojo", "inspect"})
#: The ``BenchmarkIdentity`` members compared between ``hello_ok`` and the capture note.
_IDENTITY_KEYS: Final = (
    "distribution", "version_reported", "source", "record_digest", "guarded_sources", "suite_set", "benchmark_version",
    "default_system_prompt_sha256", "tool_definitions_sha256", "python", "lock_sha256",
    # an Inspect worker's identity (D-663); absent on both sides for an AgentDojo-family session, so equal there
    "task_files_sha256", "dataset", "benchmark",
)  # fmt: skip


def check_capture_identity(log: bytes, hello_identity: Mapping[str, Any], limits: Any = None,
                           backend: str | None = None) -> None:
    """D.11.3 rule 1 at ingest: the session's identity must be the worker's ``hello_ok`` identity, and, with ``backend``,
    ``session.start.backend.id`` must name the backend T0 runs (D.11.9). A session that ended before it wrote its header
    (killed at start) has none and passes (there is nothing to contradict)."""
    from agentprov.io.canonical import jcs_bytes

    if backend is not None:
        _check_backend_id(log, backend, limits)

    event, note = capture_identity(log, limits)
    if event is None and note is None:
        return
    if note is None:
        raise IdentityMismatch("IdentityMismatch: the capture log has an identity event but no identity_digests note")
    for key in _IDENTITY_KEYS:
        if jcs_bytes(note.get(key)) != jcs_bytes(hello_identity.get(key)):
            raise IdentityMismatch(f"IdentityMismatch: the capture identity_digests note differs from hello_ok in {key}")
    benchmark = (event or {}).get("benchmark") if isinstance(event, dict) else None
    if isinstance(benchmark, dict):
        # AgentDojo family: the benchmark is the hello distribution; Inspect (D-663): hello names the harness
        # (inspect_ai) and reports the benchmark distribution separately, as ``benchmark``
        hello_bench = hello_identity.get("benchmark")
        version = hello_bench.get("version") if isinstance(hello_bench, Mapping) else hello_identity.get("version_reported")
        if benchmark.get("dist_version") != version or \
                benchmark.get("tool_definitions_sha256") != hello_identity.get("tool_definitions_sha256"):
            raise IdentityMismatch("IdentityMismatch: the capture identity event differs from hello_ok")


def _check_backend_id(log: bytes, backend: str, limits: Any) -> None:
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    first = log.split(b"\n", 1)[0]
    if not first:
        return
    try:
        event = strict_json_loads(first, limits or IngestLimits(), record=True)
    except IngestError:
        return  # the mapper reports a log without a verifiable session.start
    data = event.get("data") if isinstance(event, dict) and event.get("type") == "session.start" else None
    declared = data.get("backend") if isinstance(data, dict) else None
    if isinstance(declared, dict) and declared.get("id") != backend:
        raise IdentityMismatch(f"IdentityMismatch: the capture session was written by another backend, not {backend}")


class QuarantinedSession(AgentProvError):
    """T0's literal-value scan hit a staged file (G.6.4): nothing from the session is stored."""

    code = "capture.quarantined"
    exit_code = 1
