"""T1 worker pool: spawn, limits, protocol ``agentprov-job/0.1`` (docs/architecture G.4; A3; SEC-22).

Untrusted bytes are parsed only inside workers. A worker is ``python -I -B -m agentprov.worker`` started with
``subprocess.Popen`` (never ``fork`` or ``multiprocessing``), with a minimal explicit environment, its own process
group and its own empty home directory. Resource exhaustion and crashes therefore become a recorded failed unit
(a ``JobResult`` carrying a typed error), never a failure of the parent.

Layering. This module is L0 and starts the worker by module name only. Everything the worker process itself needs
(frame writer, closed job table, rlimits, audit hook, dispatch) also lives here, so that the ``--in-process``
debugging path (G.4.9) runs the *same* dispatch code and the *same* frame round trip as a real worker. The L6 entry
module ``agentprov.worker`` is a thin shell around this module.

Enforcement summary (G.4.3, G.4.4, G.4.11):

* kernel, set by the worker before it reads any job, for every rlimit that exists on the host (``agentprov.host``):
  ``RLIMIT_CORE=0``, ``RLIMIT_FSIZE=0``, ``RLIMIT_NOFILE``, ``RLIMIT_CPU`` (soft limit re-armed per job, hard limit
  fixed), and ``RLIMIT_AS`` only where a probe showed the kernel enforces it. Where there is no ``resource`` module a
  Job Object caps process memory instead;
* parent, polled by the sampler the host probe chose (procfs, libproc or psapi): RSS against ``cap - margin`` and the
  wall clock, then a process-tree kill (``killpg`` or ``TerminateJobObject``); output frame, JSON-per-job and DATA
  caps are checked as frames arrive;
* worker audit hook: Python-level network and subprocess events (defence in depth only; native code bypasses it).

Job dispatch is through the closed table :data:`JOB_KINDS` of ``agentprov.``-namespaced ``module:function``
strings. No callable, module name or path from a request is ever imported.
"""

from __future__ import annotations

import dataclasses
import errno
import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
import signal
import warnings
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import weakref
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import IO, Any, Final, Literal

from agentprov.errors import AgentProvError, IngestError
from agentprov.host import (
    Calibration,
    Footprint,
    HostConstants,
    HostProfile,
    TreeKiller,
    attach_tree_killer,
    available_rlimits,
    constants_for,
    detect_host,
    footprint_reader,
    host_rss_sampler,
    minimal_environment,
    spawn_kwargs,
)
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import STORED_OBJECT_LIMITS, open_evidence
from agentprov.io.canonical import jcs_bytes
from agentprov.progress import Progress, ProgressEvent

__all__ = [
    "AUDIT_BLOCKED_EVENTS",
    "JOB_KINDS",
    "KIND_RSS_BYTES",
    "RSS_CAP_CEILING",
    "RSS_CAP_FLOOR",
    "PROTOCOL",
    "AuditBlockedError",
    "InProcessRefusedError",
    "IsolationDegradedWarning",
    "IsolationInsufficientError",
    "Job",
    "JobContext",
    "JobResult",
    "MemberOutput",
    "WorkerCrashError",
    "WorkerError",
    "WorkerInputError",
    "WorkerJobError",
    "WorkerLimitError",
    "WorkerLimits",
    "WorkerPool",
    "WorkerProtocolError",
    "apply_start_rlimits",
    "build_worker_env",
    "get_calibration",
    "install_audit_hook",
    "resolve_worker_count",
    "result_fingerprint",
    "strict_loads",
]

_LOG = logging.getLogger("agentprov.io.workers")

PROTOCOL: Final = "agentprov-job/0.1"

TAG_JSON: Final = b"JSON"
TAG_DATA: Final = b"DATA"
TAG_DONE: Final = b"DONE"
TAG_FAIL: Final = b"FAIL"
_TAGS: Final = frozenset({TAG_JSON, TAG_DATA, TAG_DONE, TAG_FAIL})
_FRAME_HEAD: Final = struct.Struct(">4sQ")  # 4-byte ASCII tag, 8-byte big-endian length (G.4.6)
MEMBER_KEY: Final = "$member"  # a JSON frame {"$member": {...}} opens a member; DATA frames follow (G.4.6)
_DATA_CHUNK: Final = 1 << 20
#: Members of one job held in T0 memory, in all (ingest-formats-3 calibration): a member below the spool threshold stays
#: in memory until the job's result is consumed, so a job returning hundreds of 1-8 MiB members held them all (2.1 GB for
#: one real nested zip). Past this budget a returned member spools to disk from its first byte. The bound is **per
#: job**: ``WorkerPool.run`` returns a whole batch before the parent consumes any result, so a batch may still hold up to
#: its job count times this budget (a pool-wide budget is pipeline-perf's D-414).
SPOOL_MEMORY_PER_JOB: Final = 64 << 20
#: D-414: JSON payloads and members of **every** result of a pool not yet closed, held in T0 memory, in all. Past it a
#: payload or member goes to the batch's spool file (:class:`_BatchSpool`). Which one holds a given output depends on
#: arrival order and is never observable: both give the same bytes.
SPOOL_MEMORY_PER_POOL: Final = 256 << 20
#: The longest request line a worker reads (G.4.6), checked by the parent before it sends one, in both isolation modes,
#: so that T1 and ``--in-process`` agree (pre-round review D #11). It holds a container-mode map request at
#: ``max_members`` (about 320 bytes per selected member); it was 4 MiB, which a container of some 13,000 members passed.
MAX_REQUEST_BYTES: Final = 64 << 20
_MESSAGE_CAP: Final = 500

KIB: Final = 1 << 10
MIB: Final = 1 << 20
GIB: Final = 1 << 30

# The closed table of job kinds (G.4.2). Values are ``agentprov.`` dotted ``module:function`` paths. The real kinds
# (``expand``, ``map``, ``sem``, ``prov``, ``validate``) are added here by the phase that implements them; nothing
# outside this table can be dispatched. Test kinds live in ``agentprov.io.worker_testjobs`` and are enabled only by
# an explicit ``test_kinds`` pool argument (``--test-kinds`` on the worker command line).
JOB_KINDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "echo": "agentprov.io.workers:job_echo",
        "sha256": "agentprov.io.workers:job_sha256",
        "calibrate": "agentprov.io.workers:job_calibrate",
        "expand": "agentprov.raw.members:job_expand",
        "map": "agentprov.adapters.runner:job_map",
        "prov": "agentprov.adapters.runner.provjob:job_prov",
        "validate": "agentprov.corpus.validation_job:job_validate",
        "zip_local": "agentprov.corpus.zip_local:job_zip_local",  # D-453: the decoded scan's local-header read
    }
)
TEST_JOB_KINDS_MODULE: Final = "agentprov.io.worker_testjobs"

# Memory caps per job kind (G.4.3, D-55). A kind not listed here uses ``WorkerLimits.rss_bytes`` (2 GiB, sized for parsing
# untrusted bytes: 64 MiB x the worst JSON amplification of 24). ``prov`` jobs read an AER that is already sealed and
# validated; their memory grows with run length in tier 4 (about 80-90 MiB per MB of PROV-JSON on the longest DTap runs,
# docs/reports/hardening/prov-rss.md), so they get 4 GiB. Every cap lies in [RSS_CAP_FLOOR, RSS_CAP_CEILING]: an override
# can raise a cap, never make it unbounded.
KIND_RSS_BYTES: Final[Mapping[str, int]] = MappingProxyType({"prov": 4 << 30})
RSS_CAP_FLOOR: Final = 64 << 20
RSS_CAP_CEILING: Final = 16 << 30
#: A defaulted ``RLIMIT_AS`` (Linux) is at least the largest RSS cap plus this headroom, so a ``prov`` job is stopped by its
#: RSS cap rather than by an address-space limit sitting under it.
AS_ABOVE_RSS: Final = 1 << 30

# G.4.4: event list is data. SEC-22 tests one event of each group.
AUDIT_BLOCKED_EVENTS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "network": (
            "socket.connect",
            "socket.bind",
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyname_ex",
            "socket.gethostbyaddr",
            "socket.getnameinfo",
            "socket.sendto",
            "socket.sendmsg",
        ),
        "subprocess": (
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.spawn",
            "os.fork",
            "os.forkpty",
        ),
    }
)

# Environment allowlist of the worker (G.4.2). ``HOME`` and ``TMPDIR`` are filled with the per-worker directory.
# Hosts whose loader needs ``SYSTEMROOT`` (Windows) also get it, with ``TEMP``, ``TMP`` and ``USERPROFILE`` redirected.
ENV_ALLOWLIST: Final = frozenset({"PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR"})
ENV_ALLOWLIST_LOADER: Final = frozenset({"SYSTEMROOT", "TEMP", "TMP", "USERPROFILE"})

_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_KIND_RE: Final = re.compile(r"[a-z][a-z0-9_.]{0,63}")
_CODE_RE: Final = re.compile(r"[a-z][a-z0-9_.]{0,79}")


# --------------------------------------------------------------------------------------------------------------
# Errors (codes are stable; ``worker.limit.<cpu|rss|wall|output>`` is the register vocabulary of HL H.6.3)
# --------------------------------------------------------------------------------------------------------------


class WorkerError(AgentProvError):
    """Base of every worker-pool error. A failed job is a failed unit, so the CLI exit code is 1 (N.1.3)."""

    code = "worker.error"
    exit_code = 1


class WorkerLimitError(WorkerError):
    """A resource limit fired: ``worker.limit.<cpu|rss|wall|output>`` (G.4.3, G.4.6)."""

    LIMITS: Final = ("cpu", "rss", "wall", "output")

    def __init__(self, limit: str, message: str = "") -> None:
        if limit not in self.LIMITS:
            raise ValueError(f"unknown worker limit {limit!r}")
        super().__init__(message or f"worker exceeded the {limit} limit", code=f"worker.limit.{limit}")
        self.limit = limit


class WorkerProtocolError(WorkerError):
    """Malformed frame, unknown tag or kind, DATA without a member, bad request: a fatal protocol error."""

    code = "worker.protocol"


class WorkerRequestTooLargeError(WorkerError):
    """The request line is longer than :data:`MAX_REQUEST_BYTES`; it is never sent."""

    code = "worker.request.too_large"


class WorkerCrashError(WorkerError):
    """The worker exited or was killed without a limit being attributed to it."""

    code = "worker.crash"


class WorkerJobError(WorkerError):
    """The job reported ``FAIL``; ``code`` is the worker-reported code."""

    code = "worker.job.error"


class WorkerInputError(WorkerError):
    """A named input is missing, unreadable, or its digest differs from the one the job named (G.4.5)."""

    code = "worker.input.error"


class IsolationInsufficientError(WorkerError):
    """Release mode needs isolation grade ``watchdog`` or better; this host gives less (exit 3, environment)."""

    code = "worker.isolation.insufficient"
    exit_code = 3


class IsolationDegradedWarning(Warning):
    """Dev-mode warning: the host gives only ``degraded`` worker isolation (a recorded grade).

    Deliberately not a ``UserWarning``: the test configuration turns ``UserWarning`` from ``agentprov.*`` into errors.
    """


class AuditBlockedError(PermissionError):
    """Raised by the worker's audit hook for a blocked network or subprocess event (G.4.4)."""


class InProcessRefusedError(WorkerError):
    """``--in-process`` together with ``--release`` is refused: exit 4 (G.4.9, N.1.3)."""

    code = "worker.in_process.refused"
    exit_code = 4


# --------------------------------------------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerLimits:
    """Per-job limits; defaults are the values of G.4.3.

    ``kind_rss_bytes`` overrides ``rss_bytes`` for the job kinds it names (default :data:`KIND_RSS_BYTES`). ``as_bytes``
    ``None`` means derived: ``max(4 GiB, largest RSS cap + 1 GiB)``; an explicit value is used as given (0 disables).
    """

    cpu_s: int = 300  # per job; soft RLIMIT_CPU is re-armed to CPU-used-so-far + this
    cpu_s_max: int = 540  # largest possible job budget: fixes the hard RLIMIT_CPU of a worker
    wall_s: float = 600.0
    rss_bytes: int = 2 * GIB
    as_bytes: int | None = None  # RLIMIT_AS, Linux only; None derives it from the RSS caps; 0 disables
    nofile: int = 64
    max_frame_bytes: int = 16 * MIB
    max_json_job_bytes: int = 256 * MIB
    max_member_bytes: int = 256 * MIB  # G.3.2
    max_total_bytes: int = 4 * GIB  # G.3.2
    stderr_tail_bytes: int = 64 * KIB
    kind_rss_bytes: Mapping[str, int] = field(default_factory=lambda: KIND_RSS_BYTES)

    def __post_init__(self) -> None:
        caps = {"rss_bytes": self.rss_bytes, **{f"kind_rss_bytes[{k}]": v for k, v in self.kind_rss_bytes.items()}}
        for name, cap in caps.items():
            if isinstance(cap, bool) or not isinstance(cap, int) or not RSS_CAP_FLOOR <= cap <= RSS_CAP_CEILING:
                raise ValueError(f"{name} must be an integer in [{RSS_CAP_FLOOR}, {RSS_CAP_CEILING}] bytes")
        if not all(isinstance(k, str) and _KIND_RE.fullmatch(k) for k in self.kind_rss_bytes):
            raise ValueError("kind_rss_bytes keys are job kinds")
        if self.as_bytes is not None and (isinstance(self.as_bytes, bool) or self.as_bytes < 0):
            raise ValueError("as_bytes must be None or >= 0")
        object.__setattr__(self, "kind_rss_bytes", MappingProxyType(dict(sorted(self.kind_rss_bytes.items()))))

    @property
    def max_rss_bytes(self) -> int:
        """The largest RSS cap any job of this pool can get: the worker count is derived from it (G.4.3, D-55)."""
        return max([self.rss_bytes, *self.kind_rss_bytes.values()])

    @property
    def effective_as_bytes(self) -> int:
        """The requested ``RLIMIT_AS``: the explicit value, else ``max(4 GiB, max_rss_bytes + AS_ABOVE_RSS)``."""
        if self.as_bytes is not None:
            return self.as_bytes
        return max(4 * GIB, self.max_rss_bytes + AS_ABOVE_RSS)

    def for_kind(self, kind: str) -> WorkerLimits:
        """These limits with the RSS cap of ``kind`` (its ``kind_rss_bytes`` entry, else ``rss_bytes``)."""
        cap = self.kind_rss_bytes.get(kind)
        return self if cap is None or cap == self.rss_bytes else replace(self, rss_bytes=cap)

    def caps_record(self) -> dict[str, Any]:
        """The memory caps as data, for a run's recorded limits: default, per kind, ceiling, address space."""
        return {"rss_bytes": self.rss_bytes, "kind_rss_bytes": dict(self.kind_rss_bytes),
                "rss_cap_ceiling": RSS_CAP_CEILING, "as_bytes": self.effective_as_bytes}

    def with_expand_scaling(self, declared_total_bytes: int) -> WorkerLimits:
        """Expand-job budget (R-40, provisional): +60 s CPU and +120 s wall per GiB of declared total.

        The declared total is capped at ``max_total_bytes`` (so at most +240 s CPU and +480 s wall at defaults).
        """
        if declared_total_bytes < 0:
            raise ValueError("declared_total_bytes must be >= 0")
        gib = min(declared_total_bytes, self.max_total_bytes) / GIB
        return replace(
            self,
            cpu_s=self.cpu_s + math.ceil(60 * gib),
            wall_s=self.wall_s + math.ceil(120 * gib),
        )

    def for_request(self) -> dict[str, int | float]:
        """The ``limits`` object of a job request (everything the worker may need)."""
        return {
            "cpu_s": self.cpu_s,
            "wall_s": self.wall_s,
            "max_frame_bytes": self.max_frame_bytes,
            "max_json_job_bytes": self.max_json_job_bytes,
            "max_member_bytes": self.max_member_bytes,
            "max_total_bytes": self.max_total_bytes,
        }


@dataclass(frozen=True)
class Job:
    """One unit of work. ``key`` orders results (G.4.8); ``kind`` must be in the closed table."""

    key: str
    kind: str
    inputs: tuple[Mapping[str, str], ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    limits: WorkerLimits | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("job key must be a non-empty string")
        if not isinstance(self.kind, str) or not _KIND_RE.fullmatch(self.kind):
            raise ValueError(f"invalid job kind {self.kind!r}")
        normalised = []
        for item in self.inputs:
            sha, role = item.get("sha256"), item.get("role")
            if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha) or not isinstance(role, str):
                raise ValueError("each input needs a lowercase hex 'sha256' and a string 'role'")
            normalised.append({"sha256": sha, "role": role})
        object.__setattr__(self, "inputs", tuple(normalised))


# --------------------------------------------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------------------------------------------


def jcs(obj: Any) -> bytes:
    """RFC 8785 canonical bytes (private helper; ``io.canonical`` owns the public one and the only ``rfc8785`` import)."""
    return jcs_bytes(obj)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_text(value: object, cap: int = _MESSAGE_CAP) -> str:
    """Escape non-printable characters and truncate: messages derive from untrusted input."""
    text = ascii(str(value))[1:-1]
    return text if len(text) <= cap else text[: cap - 3] + "..."


class FrameWriter:
    """Writes frames ``tag(4) || length(8, big endian) || payload`` and enforces a per-frame cap."""

    def __init__(self, stream: IO[bytes], *, max_frame_bytes: int = 16 * MIB) -> None:
        self._stream = stream
        self.max_frame_bytes = max_frame_bytes

    def write(self, tag: bytes, payload: bytes) -> None:
        if tag not in _TAGS:
            raise ValueError(f"unknown frame tag {tag!r}")
        if len(payload) > self.max_frame_bytes:
            raise WorkerLimitError("output", f"frame of {len(payload)} bytes exceeds {self.max_frame_bytes}")
        self._stream.write(_FRAME_HEAD.pack(tag, len(payload)))
        self._stream.write(payload)

    def flush(self) -> None:
        self._stream.flush()


class _StreamEnded(Exception):
    """EOF in the middle of a job's frames (internal)."""


# --------------------------------------------------------------------------------------------------------------
# Parent side: strict JSON for worker frames, frame collection and result types
# --------------------------------------------------------------------------------------------------------------


def strict_loads(data: bytes) -> object:
    """Strict JSON for worker frames and requests (G.4.6): ``agentprov.ingest.loaders.strict_json_loads`` with the
    record-size bound, with every ingest violation reported as a protocol error.
    """
    try:
        return strict_json_loads(data, record=True)
    except IngestError as exc:
        raise WorkerProtocolError(f"invalid JSON frame: {exc.code}") from None


class MemberOutput:
    """An archive member streamed back as DATA frames; bytes sit in a spooled temporary file in T0.

    Above ``spool_max`` the spool is an unnamed temporary file in ``spool_dir`` (the pool's, else the system default): a
    crash leaves no file behind, and a pool that stores into a raw store spools beside it (D-383). ``spool_max`` 0
    spools to disk from the first byte (a job past :data:`SPOOL_MEMORY_PER_JOB`).
    """

    SPOOL_MAX: Final = 1 * MIB  # D-414 (was 8 MiB): a member above it, or past a budget, goes to the batch spool

    def __init__(self, header: Mapping[str, Any], spool_max: int = SPOOL_MAX, spool_dir: str | None = None) -> None:
        self.header = header
        self.size = 0
        self._batch: _BatchSpool | None = None
        self._ranges: list[tuple[int, int]] = []
        self._spool: Any = tempfile.SpooledTemporaryFile(max_size=spool_max, dir=spool_dir)  # noqa: SIM115 - closed explicitly
        if spool_max <= 0:  # SpooledTemporaryFile's 0 means "never roll over"; here it means "disk from the start"
            self._spool.rollover()

    @classmethod
    def _on_batch(cls, header: Mapping[str, Any], batch: _BatchSpool) -> MemberOutput:
        """A member whose bytes are ranges of the batch's spool file (D-414): no descriptor of its own."""
        self = cls.__new__(cls)
        self.header, self.size, self._batch, self._ranges, self._spool = header, 0, batch, [], None
        return self

    def _append(self, chunk: bytes) -> None:
        if self._batch is not None:
            self._ranges.append(self._batch.append(chunk))
        else:
            self._spool.write(chunk)
        self.size += len(chunk)

    def read_bytes(self) -> bytes:
        if self._batch is not None:
            return b"".join(self._batch.pread(offset, length) for offset, length in self._ranges)
        self._spool.seek(0)
        return self._spool.read()

    def iter_chunks(self, chunk_size: int = MIB) -> Iterator[bytes]:
        if self._batch is not None:  # pread only: no shared position, so readers of one batch can interleave
            for offset, length in self._ranges:
                for start in range(0, length, chunk_size):
                    yield self._batch.pread(offset + start, min(chunk_size, length - start))
            return
        self._spool.seek(0)
        while chunk := self._spool.read(chunk_size):
            yield chunk

    def close(self) -> None:
        if self._spool is not None:
            self._spool.close()
        self._ranges = []


class _BatchSpool:
    """One unnamed spool file for the outputs of one :meth:`WorkerPool.run` call that do not fit a memory budget (D-414).

    Writes happen only in ``_collect``, before ``run`` returns, and append at the end under a lock. Reads use
    ``os.pread`` only, so no reader moves a shared file position and readers of one batch may interleave. The file is
    unlinked at creation (``tempfile.TemporaryFile``) and closed when its last holder releases it, or when it is
    collected; a crash leaves nothing behind. It holds at most the batch's spilled outputs: per job at most
    ``max_json_job_bytes`` of JSON and ``max_total_bytes`` of members (G.4.3)."""

    def __init__(self, directory: Callable[[], str]) -> None:
        self._directory = directory
        self._file: Any = None  # opened on the first append: a batch that spills nothing touches no disk
        self._fd = -1
        self._lock = threading.Lock()
        self._size = 0
        self._holders = 1  # the run that creates it
        self._finalizer: weakref.finalize[Any, Any] | None = None

    def _open(self) -> None:
        try:
            directory: str | None = self._directory()
        except OSError:
            directory = None  # the system temporary directory; the file is unlinked at creation either way
        self._file = tempfile.TemporaryFile(dir=directory)  # noqa: SIM115 - closed by release or the finalizer
        self._fd = self._file.fileno()
        self._finalizer = weakref.finalize(self, self._file.close)

    def append(self, data: bytes) -> tuple[int, int]:
        with self._lock:
            if self._file is None:
                self._open()
            offset = self._size
            view = memoryview(data)
            while view:
                written = os.pwrite(self._fd, view, offset + (len(data) - len(view)))
                view = view[written:]
            self._size += len(data)
        return offset, len(data)

    def pread(self, offset: int, length: int) -> bytes:
        parts: list[bytes] = []
        while length > 0:
            chunk = os.pread(self._fd, length, offset)
            if not chunk:
                raise OSError("the batch spool file is shorter than a recorded range")
            parts.append(chunk)
            offset += len(chunk)
            length -= len(chunk)
        return b"".join(parts)

    def acquire(self) -> None:
        with self._lock:
            self._holders += 1

    def release(self) -> None:
        with self._lock:
            self._holders -= 1
            last = self._holders == 0
        if last and self._finalizer is not None:
            self._finalizer()

    @property
    def closed(self) -> bool:
        return self._finalizer is None or not self._finalizer.alive


class _Budget:
    """A byte budget shared by the results of one pool (D-414): taken when an output is kept in memory, given back when
    its result is closed or collected."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self, n: int) -> bool:
        with self._lock:
            if self.used + n > self.limit:
                return False
            self.used += n
            return True

    def give(self, n: int) -> None:
        with self._lock:
            self.used -= n


class _Payload(Mapping[str, Any]):
    """One ``JSON`` frame of a result, kept as the bytes the worker sent (D-414): in memory, or a range of the batch spool.
    As a mapping it decodes on first use and keeps the value (what ``outputs`` and ``json`` always did);
    :meth:`decode` returns a fresh value and keeps nothing, for the streaming passes. The bytes were checked by
    :func:`strict_loads` on arrival; decoding them again gives the same object."""

    __slots__ = ("_cache", "_data", "_range", "_spool")

    def __init__(self, data: bytes | None, spool: _BatchSpool | None = None, rng: tuple[int, int] = (0, 0)) -> None:
        self._data, self._spool, self._range = data, spool, rng
        self._cache: dict[str, Any] | None = None

    def raw(self) -> bytes:
        if self._data is not None:
            return self._data
        assert self._spool is not None
        return self._spool.pread(*self._range)

    def decode(self) -> dict[str, Any]:
        value = strict_loads(self.raw())
        assert isinstance(value, dict)
        return value

    def _value(self) -> dict[str, Any]:
        if self._cache is None:
            self._cache = self.decode()
        return self._cache

    def __getitem__(self, key: str) -> Any:
        return self._value()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._value())

    def __len__(self) -> int:
        return len(self._value())

    def __contains__(self, key: object) -> bool:
        return key in self._value()

    def __repr__(self) -> str:
        return f"_Payload({self._value()!r})"


class _ResultHold:
    """What one result holds (D-414): its members, the memory budget it took and its batch spool. Released exactly once,
    by :meth:`JobResult.close` or when the result is collected (a consumer that raises mid-batch leaks nothing)."""

    def __init__(self, members: list[MemberOutput], budget: _Budget | None, held: int, batch: _BatchSpool | None) -> None:
        self.json_memo: tuple[Mapping[str, Any], ...] | None = None
        if batch is not None:
            batch.acquire()
        self._finalizer = weakref.finalize(self, _ResultHold._release, members, budget, held, batch)

    @staticmethod
    def _release(members: list[MemberOutput], budget: _Budget | None, held: int, batch: _BatchSpool | None) -> None:
        for member in members:
            member.close()
        if budget is not None and held:
            budget.give(held)
        if batch is not None:
            batch.release()

    def close(self) -> None:
        self._finalizer()


@dataclass
class _Collected:
    outputs: list[Mapping[str, Any] | MemberOutput]
    counters: Mapping[str, Any]
    hold: _ResultHold | None = None


class _Failed(Exception):
    """A ``FAIL`` frame (internal)."""

    def __init__(self, code: str, message: str, exc_type: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.exc_type = exc_type


def _read_exact(stream: IO[bytes], n: int) -> bytes:
    data = stream.read(n)
    if data is None or len(data) != n:
        raise _StreamEnded
    return data


def _collect(stream: IO[bytes], job_no: int, limits: WorkerLimits, spool_dir: str | None = None, *,
             batch: _BatchSpool | None = None, budget: _Budget | None = None) -> _Collected:
    """Read frames up to ``DONE`` or ``FAIL``, enforcing the G.4.3 / G.4.6 caps as they arrive.

    With ``batch`` (D-414) every ``JSON`` frame is kept as its bytes (a :class:`_Payload`), in memory while this job's
    :data:`SPOOL_MEMORY_PER_JOB` and the pool's ``budget`` allow, else in the batch spool; a member is kept in memory on
    the same terms when it is at most ``MemberOutput.SPOOL_MAX``, else in the batch spool. Every frame is still parsed and
    checked here as it arrives. Without ``batch``, frames are kept decoded and members in their own spools, as before."""
    outputs: list[Mapping[str, Any] | MemberOutput] = []
    json_total = 0
    data_total = 0
    member: MemberOutput | None = None
    declared = 0
    in_memory = 0  # bytes this job may still hold in memory (members; with a batch, payloads too)
    held = 0  # bytes taken from the pool budget (released with the result)

    def keep_in_memory(n: int) -> bool:
        nonlocal in_memory, held
        if in_memory + n > SPOOL_MEMORY_PER_JOB or (budget is not None and not budget.take(n)):
            return False
        in_memory += n
        held += n if budget is not None else 0
        return True

    ok = False
    try:
        while True:
            tag, length = _FRAME_HEAD.unpack(_read_exact(stream, _FRAME_HEAD.size))
            if tag not in _TAGS:
                raise WorkerProtocolError(f"unknown frame tag {_safe_text(tag)}")
            if length > limits.max_frame_bytes:
                raise WorkerLimitError("output", f"frame of {length} bytes exceeds {limits.max_frame_bytes}")
            payload = _read_exact(stream, length)
            if tag == TAG_DATA:
                if member is None:
                    raise WorkerProtocolError("DATA frame without an open member")
                if member.size + length > declared:
                    raise WorkerProtocolError(f"DATA bytes exceed the declared member size {declared}")
                if member.size + length > limits.max_member_bytes:
                    raise WorkerLimitError("output", f"member exceeds {limits.max_member_bytes} bytes")
                data_total += length
                if data_total > limits.max_total_bytes:
                    raise WorkerLimitError("output", f"DATA bytes exceed {limits.max_total_bytes} per job")
                member._append(payload)
                continue
            member = None  # any other frame closes the open member
            if tag == TAG_JSON:
                json_total += length
                if json_total > limits.max_json_job_bytes:
                    raise WorkerLimitError("output", f"JSON output exceeds {limits.max_json_job_bytes} bytes")
                obj = strict_loads(payload)
                if not isinstance(obj, dict):
                    raise WorkerProtocolError("JSON frame is not an object")
                if MEMBER_KEY in obj:
                    header = obj[MEMBER_KEY]
                    size = header.get("size") if isinstance(header, dict) else None
                    if len(obj) != 1 or not isinstance(size, int) or isinstance(size, bool) or size < 0:
                        raise WorkerProtocolError("malformed member header")
                    if size > limits.max_member_bytes:
                        raise WorkerLimitError("output", f"member declares {size} bytes")
                    if batch is None:
                        spool_max = MemberOutput.SPOOL_MAX if in_memory < SPOOL_MEMORY_PER_JOB else 0
                        member = MemberOutput(header, spool_max=spool_max, spool_dir=spool_dir)
                        in_memory += min(size, spool_max)
                    elif size <= MemberOutput.SPOOL_MAX and keep_in_memory(size):
                        member = MemberOutput(header, spool_max=MemberOutput.SPOOL_MAX, spool_dir=spool_dir)
                    else:
                        member = MemberOutput._on_batch(header, batch)
                    declared = size
                    outputs.append(member)
                elif batch is None:
                    outputs.append(obj)
                elif keep_in_memory(length):
                    outputs.append(_Payload(payload))
                else:
                    outputs.append(_Payload(None, batch, batch.append(payload)))
                continue
            obj = strict_loads(payload)
            if tag == TAG_FAIL and isinstance(obj, dict) and obj.get("job") == -1:
                # the worker could not read the request at all (no job number): keep its own reason (D #11)
                raise WorkerProtocolError(f"the worker refused the request: {_safe_text(obj.get('message', ''))}")
            if not isinstance(obj, dict) or obj.get("job") != job_no:
                raise WorkerProtocolError("DONE/FAIL frame does not match the running job")
            if tag == TAG_FAIL:
                raise _Failed(
                    str(obj.get("code", "worker.job.error")),
                    _safe_text(obj.get("message", "")),
                    _safe_text(obj.get("type", ""), 80),
                )
            counters = obj.get("counters", {})
            if not isinstance(counters, dict):
                raise WorkerProtocolError("DONE counters is not an object")
            ok = True
            hold = None
            if batch is not None:
                hold = _ResultHold([o for o in outputs if isinstance(o, MemberOutput)], budget, held, batch)
            return _Collected(outputs, counters, hold)
    finally:
        if not ok:
            for item in outputs:
                if isinstance(item, MemberOutput):
                    item.close()
            if budget is not None and held:
                budget.give(held)


@dataclass
class JobResult:
    """Outcome of one job. ``outputs`` keeps frame order: JSON objects and :class:`MemberOutput` entries."""

    key: str
    kind: str
    job: int
    outputs: tuple[Mapping[str, Any] | MemberOutput, ...] = ()
    counters: Mapping[str, Any] = field(default_factory=dict)
    error: AgentProvError | None = None
    isolation: str = "worker"
    elapsed_s: float = 0.0
    peak_rss_bytes: int | None = None
    stderr_tail: bytes = b""
    worker_pid: int | None = None
    #: D-414: what a pool result holds (members, memory budget, batch spool); released once by :meth:`close` or when the
    #: result is collected. ``None`` for a result built by hand.
    _hold: _ResultHold | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def json(self) -> tuple[Mapping[str, Any], ...]:
        """The ``JSON`` frames in order (memoised for a pool result; a frame decodes on first use)."""
        if self._hold is None:
            return tuple(o for o in self.outputs if not isinstance(o, MemberOutput))
        if self._hold.json_memo is None:
            self._hold.json_memo = tuple(o for o in self.outputs if not isinstance(o, MemberOutput))
        return self._hold.json_memo

    @property
    def members(self) -> tuple[MemberOutput, ...]:
        return tuple(o for o in self.outputs if isinstance(o, MemberOutput))

    def iter_outputs(self) -> Iterator[Mapping[str, Any] | MemberOutput]:
        """Every output in frame order, members and ``JSON`` frames interleaved (D-414). A frame is decoded afresh and not
        kept, so a pass over a large result holds one frame at a time."""
        for o in self.outputs:
            yield o.decode() if isinstance(o, _Payload) else o

    def iter_json(self) -> Iterator[Mapping[str, Any]]:
        """The ``JSON`` frames in order, each decoded afresh and not kept (D-414)."""
        for o in self.outputs:
            if not isinstance(o, MemberOutput):
                yield o.decode() if isinstance(o, _Payload) else o

    def close(self) -> None:
        if self._hold is not None:
            self._hold.close()
        else:
            for member in self.members:
                member.close()


def result_fingerprint(results: Iterable[JobResult]) -> str:
    """sha256 over the JCS form of everything deterministic in ``results`` (in the given order).

    Excludes timing, pid, RSS and stderr. Used by the determinism tests (G.4.8, RPR-6, RPR-8).
    """
    digest = hashlib.sha256()
    for r in results:
        body: dict[str, Any] = {
            "key": r.key,
            "kind": r.kind,
            "ok": r.ok,
            "code": None if r.error is None else r.error.code,
            "counters": dict(r.counters),
            "outputs": [
                {"member": dict(o.header), "sha256": sha256_hex(o.read_bytes()), "size": o.size}
                if isinstance(o, MemberOutput)
                else dict(o)
                for o in r.outputs
            ],
        }
        line = jcs(body)
        digest.update(struct.pack(">Q", len(line)))
        digest.update(line)
    return digest.hexdigest()


# --------------------------------------------------------------------------------------------------------------
# Worker side: context, dispatch, rlimits, audit hook
# --------------------------------------------------------------------------------------------------------------


class JobContext:
    """What a job function receives. All output goes through the frame writer (stdout is not used)."""

    def __init__(
        self,
        request: Mapping[str, Any],
        writer: FrameWriter,
        *,
        store_root: Path | None = None,
    ) -> None:
        self.job: int = request["job"]
        self.kind: str = request["kind"]
        self.inputs: tuple[Mapping[str, str], ...] = tuple(request["inputs"])
        self.params: Mapping[str, Any] = request["params"]
        self.limits: Mapping[str, Any] = request["limits"]
        self._writer = writer
        self._store_root = store_root

    def emit(self, obj: Mapping[str, Any]) -> None:
        """One ``JSON`` frame (a JCS object)."""
        if MEMBER_KEY in obj:
            raise ValueError(f"{MEMBER_KEY!r} is reserved for member headers")
        self._writer.write(TAG_JSON, jcs(obj))

    def member(self, header: Mapping[str, Any]) -> None:
        """Open a member: ``header`` holds at least an integer ``size``; ``data`` calls follow."""
        self._writer.write(TAG_JSON, jcs({MEMBER_KEY: dict(header)}))

    def data(self, chunk: bytes) -> None:
        """``DATA`` frames for the open member, split into chunks of at most 1 MiB."""
        view = memoryview(chunk)
        step = min(_DATA_CHUNK, self._writer.max_frame_bytes)
        for start in range(0, len(view), step):
            self._writer.write(TAG_DATA, bytes(view[start : start + step]))

    def read_input(self, index: int) -> bytes:
        """Read input ``index`` by digest from the store, re-hash, and fail on mismatch (G.4.5).

        Store layout (HL H.1.3): ``<root>/<h0h1>/<sha256>.<ext>``; the extension is not known from the digest,
        so the unique entry with that digest stem is opened read-only through the one no-follow opener
        (:func:`agentprov.ingest.paths.open_evidence`, whose mechanism the host probe selected).
        """
        with self.open_input(index) as handle:
            return handle.read()

    def open_input(self, index: int) -> IO[bytes]:
        """Open input ``index`` as a seekable read-only handle whose digest was checked first (G.4.5; HL.R7, D-58).

        The object is opened as :meth:`read_input` does, hashed in 1 MiB chunks (never held whole), and the handle is
        rewound to 0 before it is returned; a mismatch fails the job like :meth:`read_input`. The caller closes it. Store
        objects are 0444 and the worker cannot write files (``RLIMIT_FSIZE = 0``), so the bytes read after the check
        are the bytes that were hashed.
        """
        if self._store_root is None:
            raise WorkerInputError("no store root was given to this worker", code="worker.input.no_store")
        item = self.inputs[index]
        sha = item["sha256"]
        directory = self._store_root / sha[:2]
        try:
            names = sorted(
                e.name for e in os.scandir(directory) if e.name == sha or e.name.startswith(sha + ".")
            )
        except OSError as exc:
            _raise_if_nofile(exc, sha)
            names = []
        if len(names) != 1:
            raise WorkerInputError(f"input {sha} not found in the store", code="worker.input.missing")
        try:
            handle = open_evidence(self._store_root, f"{sha[:2]}/{names[0]}", STORED_OBJECT_LIMITS, allow_hardlinks=True)
        except IngestError as exc:
            if exc.code == "ingest.path.unsupported_platform":
                raise  # the host cannot open store objects safely: not "missing"
            raise WorkerInputError(f"input {sha} unreadable: {exc.code}", code="worker.input.missing") from None
        except OSError as exc:
            _raise_if_nofile(exc, sha)
            raise WorkerInputError(f"input {sha} unreadable: {exc.strerror}", code="worker.input.missing") from None
        try:
            digest = hashlib.sha256()
            while chunk := handle.read(_DATA_CHUNK):
                digest.update(chunk)
            if digest.hexdigest() != sha:
                raise WorkerInputError(f"input {sha} failed its digest check", code="worker.input.digest_mismatch")
            handle.seek(0)
        except OSError as exc:
            handle.close()
            raise WorkerInputError(f"input {sha} unreadable: {exc.strerror}", code="worker.input.missing") from None
        except BaseException:
            handle.close()
            raise
        return handle


def _raise_if_nofile(exc: OSError, sha: str) -> None:
    """The worker's ``RLIMIT_NOFILE`` was reached while opening an input: say so (BF-15, D-461), never "missing"."""
    if exc.errno in (errno.EMFILE, errno.ENFILE):
        raise WorkerInputError(f"input {sha} not opened: the worker's open-file limit is reached",
                               code="worker.input.nofile") from None


def job_echo(ctx: JobContext) -> dict[str, Any]:
    """Built-in test job: echoes params; ``params["members"]`` (``[{"label", "text"}]``) become members."""
    ctx.emit({"echo": dict(ctx.params), "inputs": len(ctx.inputs)})
    for item in ctx.params.get("members", []):
        data = str(item["text"]).encode("utf-8")
        ctx.member({"label": str(item["label"]), "size": len(data)})
        ctx.data(data)
    return {"inputs": len(ctx.inputs)}


def job_sha256(ctx: JobContext) -> dict[str, Any]:
    """Built-in test job: sha256 of ``params["text"]`` and of every named input (read and verified from the store)."""
    count = 0
    if "text" in ctx.params:
        data = str(ctx.params["text"]).encode("utf-8")
        ctx.emit({"sha256": sha256_hex(data), "size": len(data), "source": "text"})
        count += 1
    for index in range(len(ctx.inputs)):
        data = ctx.read_input(index)
        ctx.emit({"index": index, "sha256": sha256_hex(data), "size": len(data), "source": "input"})
        count += 1
    return {"digests": count}


def job_calibrate(ctx: JobContext) -> dict[str, Any]:
    """Allocation-rate probe (host calibration): touch fresh memory for a short, bounded time and report bytes/s.

    Bounded by ``params["budget_s"]`` (default 80 ms) and ``params["max_bytes"]`` (default 256 MiB); at least one
    8 MiB block is always allocated. Pages are written, so the figure includes page-fault cost.
    """
    budget = min(float(ctx.params.get("budget_s", 0.08)), 1.0)
    max_bytes = min(int(ctx.params.get("max_bytes", 256 * MIB)), 512 * MIB)
    chunk = 8 * MIB
    held: list[bytes] = []
    total = 0
    start = time.perf_counter()
    while True:
        held.append(b"\x01" * chunk)
        total += chunk
        if total >= max_bytes or time.perf_counter() - start >= budget:
            break
    elapsed = max(time.perf_counter() - start, 1e-6)
    ctx.emit({"alloc_rate_bytes_per_s": total / elapsed, "bytes": total, "duration_s": elapsed})
    return {"blocks": len(held)}


def kind_table(*, test_kinds: bool) -> dict[str, str]:
    """The effective closed table. Test kinds are merged only when explicitly enabled."""
    table = dict(JOB_KINDS)
    if test_kinds:
        table.update(import_module(TEST_JOB_KINDS_MODULE).TEST_JOB_KINDS)
    return table


def preload_job_kinds(table: Mapping[str, str]) -> dict[str, Callable[[JobContext], Any]]:
    """Import every module the table names (before the audit hook is installed, G.4.4)."""
    functions: dict[str, Callable[[JobContext], Any]] = {}
    for kind, target in table.items():
        module_name, _, attr = target.partition(":")
        if not module_name.startswith("agentprov.") or not attr:
            raise WorkerProtocolError(f"job kind {kind!r} maps outside the agentprov namespace")
        functions[kind] = getattr(import_module(module_name), attr)
    return functions


def validate_request(obj: object, functions: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a parent request line; unknown kinds and malformed fields are fatal protocol errors."""
    if not isinstance(obj, dict):
        raise WorkerProtocolError("request is not an object")
    if obj.get("v") != PROTOCOL:
        raise WorkerProtocolError(f"unsupported protocol version {_safe_text(obj.get('v'))}")
    job = obj.get("job")
    if not isinstance(job, int) or isinstance(job, bool) or job < 0:
        raise WorkerProtocolError("job number must be a non-negative integer")
    kind = obj.get("kind")
    if not isinstance(kind, str) or kind not in functions:
        raise WorkerProtocolError(f"unknown job kind {_safe_text(kind)}")
    inputs, params, limits = obj.get("inputs"), obj.get("params"), obj.get("limits")
    if not isinstance(inputs, list) or not all(
        isinstance(i, dict) and isinstance(i.get("sha256"), str) and _SHA256_RE.fullmatch(i["sha256"])
        for i in inputs
    ):
        raise WorkerProtocolError("inputs must be a list of {sha256, role} objects")
    if not isinstance(params, dict) or not isinstance(limits, dict):
        raise WorkerProtocolError("params and limits must be objects")
    return obj


def _failure_for(exc: BaseException) -> tuple[str, str]:
    """Map an exception raised by a job to a stable code (G.4.6; HL H.6.3)."""
    if isinstance(exc, WorkerError):
        return exc.code, str(exc)
    if isinstance(exc, AuditBlockedError):
        return "worker.audit.blocked", str(exc)
    if isinstance(exc, MemoryError):
        return "worker.limit.rss", "allocation failed under the address-space limit"
    if isinstance(exc, AgentProvError):
        return exc.code, str(exc)
    return "worker.job.error", str(exc)


def run_job_request(
    request: Mapping[str, Any],
    functions: Mapping[str, Callable[[JobContext], Any]],
    writer: FrameWriter,
    *,
    store_root: Path | None = None,
) -> bool:
    """Run one validated request and write ``DONE`` or ``FAIL``. Returns False if the worker must be replaced."""
    job_no = request["job"]
    ctx = JobContext(request, writer, store_root=store_root)
    try:
        counters = functions[request["kind"]](ctx) or {}
        writer.write(TAG_DONE, jcs({"job": job_no, "counters": dict(counters)}))
        writer.flush()
        return True
    except (Exception, SystemExit) as exc:
        if isinstance(exc, MemoryError):
            # The traceback keeps every frame's locals alive (a job's big buffers), so under an address-space limit the
            # reply below could not even import or allocate. Drop them first (G.4.12).
            traceback.clear_frames(exc.__traceback__)
        code, message = _failure_for(exc)
        # A FAIL frame always fits: it is small, and written without the job's frame cap.
        raw = FrameWriter(writer._stream, max_frame_bytes=MIB)  # noqa: SLF001 - same stream, own cap
        raw.write(
            TAG_FAIL,
            jcs({"job": job_no, "code": code, "message": _safe_text(message), "type": type(exc).__name__}),
        )
        raw.flush()
        return False


def apply_start_rlimits(*, cpu_hard_s: int, nofile: int, as_bytes: int) -> dict[str, tuple[int, int]]:
    """Kernel limits set by the worker before it reads any job (G.4.3). Returns what was applied.

    Only rlimits that exist on this host are applied (``agentprov.host.available_rlimits``); the parent passes a
    non-zero ``as_bytes`` only when its probe showed that the kernel enforces ``RLIMIT_AS``.
    """
    available = available_rlimits()
    if not available:
        return {}
    import resource  # noqa: PLC0415 - only exists where ``available`` is non-empty

    applied: dict[str, tuple[int, int]] = {}

    def lower(name: str, soft: int, hard: int) -> None:
        if name in available:
            resource.setrlimit(getattr(resource, f"RLIMIT_{name.upper()}"), (soft, hard))
            applied[name] = (soft, hard)

    lower("core", 0, 0)
    lower("fsize", 0, 0)  # writes fail with EFBIG; pipes unaffected (obs-G5)
    if "nofile" in available:
        _soft, current_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        cap = nofile if current_hard == resource.RLIM_INFINITY else min(nofile, current_hard)
        lower("nofile", cap, cap)
    if as_bytes:
        lower("as", as_bytes, as_bytes)
    lower("cpu", cpu_hard_s, cpu_hard_s)
    return applied


def arm_job_cpu_budget(budget_s: int, hard_s: int) -> int:
    """Set the soft ``RLIMIT_CPU`` to CPU used so far + ``budget_s`` (never above the hard limit). 0 if unavailable."""
    if "cpu" not in available_rlimits():
        return 0
    import resource  # noqa: PLC0415

    usage = resource.getrusage(resource.RUSAGE_SELF)
    soft = min(math.ceil(usage.ru_utime + usage.ru_stime) + max(1, int(budget_s)), hard_s)
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard_s))
    return soft


def install_audit_hook() -> None:
    """Install the PEP 578 hook of G.4.4 (network and subprocess only). Irreversible for the process."""
    blocked = frozenset(e for group in AUDIT_BLOCKED_EVENTS.values() for e in group)

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event in blocked:
            raise AuditBlockedError(f"audit event {event} is blocked in a T1 worker")
        if event == "import" and args and args[0] == "_posixsubprocess":
            # V-4: a fresh import (after the module was dropped from sys.modules) restores the real fork_exec
            raise AuditBlockedError("a fresh import of _posixsubprocess is blocked in a T1 worker")

    sys.addaudithook(hook)
    # _posixsubprocess.fork_exec starts a process without raising any audit event; multiprocessing's spawn and
    # forkserver paths call it from pure Python (pre-round review D #13). No job kind needs it, so the worker replaces
    # it after preload, and the copy `subprocess` bound when it was imported (V-4). Outside the hook remain native code
    # calling the C function and the import internals that rebuild the module without an audit event
    # (`importlib.util.module_from_spec` on its spec, `_imp.create_builtin`), as G.4.4 says.
    try:
        import _posixsubprocess
    except ImportError:  # no POSIX subprocess helper on this platform
        return

    def fork_exec_blocked(*_args: Any, **_kwargs: Any) -> Any:
        raise AuditBlockedError("_posixsubprocess.fork_exec is blocked in a T1 worker")

    _posixsubprocess.fork_exec = fork_exec_blocked  # type: ignore[attr-defined,assignment,unused-ignore]
    bound = sys.modules.get("subprocess")
    if bound is not None and hasattr(bound, "_fork_exec"):
        bound._fork_exec = fork_exec_blocked  # type: ignore[attr-defined]  # noqa: SLF001


# --------------------------------------------------------------------------------------------------------------
# Parent side: environment, process supervision, pool
# --------------------------------------------------------------------------------------------------------------


def build_worker_env(job_dir: str | os.PathLike[str]) -> dict[str, str]:
    """The complete worker environment (G.4.2). Nothing is inherited from the parent."""
    return minimal_environment(os.fspath(job_dir))


# --------------------------------------------------------------------------------------------------------------
# D-554: memory admission for pools with a charge policy
# --------------------------------------------------------------------------------------------------------------

#: A worker whose lifetime peak passed this is retired after its job, before its slot waits again: CPython rarely gives
#: heap back to the host, and an idle worker holding it would block admissions (deferrals review, item 2).
ADMISSION_RETIRE_PEAK: Final = 512 << 20
#: The share of physical memory the controller may hand out (G.4.3's 0.75), unless ``suite_queue`` granted less.
ADMISSION_RAM_SHARE: Final = 0.75
#: The default slot count of a pool with a charge policy (``workers=0``): ``"cpus"`` is the host's logical CPU count, an
#: int a fixed count, ``None`` the unchanged ``resolve_worker_count(0)``. D-415 (user-approved 2026-10-21): on the M2 Max
#: (8P+4E, 32 GB) all 12 CPUs gave the best wall (ROPE 1,500: 193 s against 263 s at the old default 6) with the worst
#: job at 3.1% of its time cap (blocker 1 of the deferrals review asked for at most a third) and byte-identical output
#: at 3, 6, 8, 10 and 12 workers. Memory still gates admission; only the count of idle slots changes.
ADMISSION_DEFAULT_SLOTS: int | Literal["cpus"] | None = "cpus"
#: Set by ``tools/suite_queue.py`` for a ``--class import`` job: the memory it granted, in bytes (D-427).
ADMISSION_BUDGET_ENV: Final = "AGENTPROV_MEMORY_BUDGET_BYTES"


def admission_default_slots(profile: HostProfile | None = None) -> int:
    """The worker count of a pool with a charge policy and ``workers=0`` (D-415): see :data:`ADMISSION_DEFAULT_SLOTS`."""
    if ADMISSION_DEFAULT_SLOTS == "cpus":
        return max(1, (profile or detect_host(probe=False)).cpu_count or 1)
    assert isinstance(ADMISSION_DEFAULT_SLOTS, int)
    return max(1, ADMISSION_DEFAULT_SLOTS)


def admission_budget(profile: HostProfile | None = None) -> int:
    """``min(0.75 x physical memory, the budget suite_queue granted)``; at least 1 GiB."""
    profile = profile or detect_host(probe=False)
    ram = profile.memory_bytes or (16 << 30)
    budget = int(ram * ADMISSION_RAM_SHARE)
    granted = os.environ.get(ADMISSION_BUDGET_ENV, "")
    if granted.isdigit():
        budget = min(budget, int(granted))
    return max(budget, 1 << 30)


@dataclass
class _Ticket:
    id: int
    charge: int
    kind: str
    pid: int | None = None
    peak: int = 0


class _Admission:
    """The memory admission controller of one parent process (D-554), shared by every pool that has a charge policy.

    A slot takes a ticket for its next job and waits until the job fits: ``in use + charge <= budget``, where *in use*
    is the parent's footprint, every live worker's ``max(charge of its running job or 0, current footprint)`` (idle
    workers included) and the charges of admitted jobs whose worker is not yet up. Tickets are served in one FIFO
    across every pool, with head-of-line blocking. The head is always admitted when no job is running anywhere (a job
    larger than the budget runs alone). The controller only ever delays a job: the per-job caps of G.4.3 stay the only
    limits that stop one."""

    def __init__(self, budget: int, footprint: Callable[[int], Footprint | None] | None) -> None:
        self.budget = budget
        self._footprint = footprint
        self._cond = threading.Condition()
        self._queue: deque[_Ticket] = deque()
        self._running: dict[int, _Ticket] = {}
        self._live: dict[int, int | None] = {}  # worker pid -> ticket id of its running job, or None when idle
        self._ids = 0
        self.stats: dict[str, Any] = {"admitted": 0, "waited": 0, "peak_in_use": 0, "overshoot": {}}

    def _memory(self, pid: int) -> int:
        fp = self._footprint(pid) if self._footprint is not None else None
        return fp.current if fp is not None else 0

    def in_use(self) -> int:
        total = self._memory(os.getpid())
        for pid, tid in self._live.items():
            charge = self._running[tid].charge if tid is not None and tid in self._running else 0
            total += max(charge, self._memory(pid))
        total += sum(t.charge for t in self._running.values() if t.pid is None)
        return total

    def acquire(self, charge: int, kind: str, abort: threading.Event) -> _Ticket | None:
        """Block until the job fits (or ``abort`` is set: ``None``)."""
        with self._cond:
            self._ids += 1
            ticket = _Ticket(self._ids, charge, kind)
            self._queue.append(ticket)
            waited = False
            while True:
                if abort.is_set():
                    self._queue.remove(ticket)
                    self._cond.notify_all()
                    return None
                if self._queue[0] is ticket:
                    used = self.in_use()
                    if not self._running or used + charge <= self.budget:
                        self._queue.popleft()
                        self._running[ticket.id] = ticket
                        self.stats["admitted"] += 1
                        self.stats["waited"] += int(waited)
                        self.stats["peak_in_use"] = max(self.stats["peak_in_use"], used + charge)
                        self._cond.notify_all()
                        return ticket
                waited = True
                self._cond.wait(timeout=0.25)  # footprints change without notice: re-sample

    def bind(self, ticket: _Ticket, pid: int) -> None:
        with self._cond:
            ticket.pid = pid
            self._live[pid] = ticket.id

    def observe(self, ticket: _Ticket, pid: int) -> None:
        """A watchdog tick: the job's footprint so far (for the overshoot record)."""
        ticket.peak = max(ticket.peak, self._memory(pid))

    def release(self, ticket: _Ticket) -> None:
        with self._cond:
            self._running.pop(ticket.id, None)
            if ticket.pid is not None and self._live.get(ticket.pid) == ticket.id:
                self._live[ticket.pid] = None
            if ticket.charge > 0 and ticket.peak:
                ratio = round(ticket.peak / ticket.charge, 3)
                worst = self.stats["overshoot"].get(ticket.kind, 0.0)
                self.stats["overshoot"][ticket.kind] = max(worst, ratio)
            self._cond.notify_all()

    def register(self, pid: int) -> None:
        with self._cond:
            self._live.setdefault(pid, None)

    def unregister(self, pid: int) -> None:
        with self._cond:
            self._live.pop(pid, None)
            self._cond.notify_all()

    def lifetime_peak(self, pid: int) -> int:
        fp = self._footprint(pid) if self._footprint is not None else None
        return (fp.lifetime_max or fp.current) if fp is not None else 0

    def wake(self) -> None:
        with self._cond:
            self._cond.notify_all()


_ADMISSION: _Admission | None = None
_ADMISSION_LOCK = threading.Lock()
#: The charge policy of pools built without one (set by the CLI for ``import --size-hints``; D-554). ``None``: no
#: admission, today's behaviour.
_DEFAULT_CHARGE: Callable[[Job, Path | None], int] | None = None


def set_default_charge_policy(policy: Callable[[Job, Path | None], int] | None) -> None:
    """Install (or clear) the charge policy of pools built without one (D-554). Charges affect timing, never outputs."""
    global _DEFAULT_CHARGE
    _DEFAULT_CHARGE = policy


def _admission(profile: HostProfile | None) -> _Admission:
    global _ADMISSION
    with _ADMISSION_LOCK:
        if _ADMISSION is None:
            _ADMISSION = _Admission(admission_budget(profile), footprint_reader(profile))
        return _ADMISSION


def prov_charge(prov_bytes: int, *, hit: str | None = None, cap: int | None = None) -> int:
    """The D-554 charge of a ``prov``/``validate`` job over ``prov_bytes`` of PROV-JSON: ``1.25 x (47 MiB + 3.6 MiB +
    80.2 x PROV MiB)`` (prov-perf's fit, R^2 0.997, confirmed under ``phys_footprint``). ``hit`` is ``"validate"`` or
    ``"prov"`` for a job whose D-550 tier-4 cache hint was staged (8 and 16 MiB per PROV MiB). At most ``cap``."""
    mib = prov_bytes / MIB
    slope = {"validate": 8.0, "prov": 16.0}.get(hit or "", 80.2)
    extra = 0.0 if hit else 3.6
    charge = int(1.25 * (47.0 + extra + slope * mib) * MIB)
    return charge if cap is None else min(charge, cap)


def resolve_worker_count(
    requested: int, limits: WorkerLimits | None = None, *, profile: HostProfile | None = None
) -> int:
    """``0`` means the host's default (``agentprov.host.constants_for``): ``min(CPUs, floor(0.75 * RAM / RSS cap))``,
    at least 1 (G.4.3, SHOULD), with the largest cap any job kind can get (``max_rss_bytes``, D-55), so that N caps
    cannot together exhaust the host. Any other value is returned unchanged.
    """
    if requested < 0:
        raise ValueError("worker count must be >= 0")
    if requested:
        return requested
    limits = limits or WorkerLimits()
    profile = profile or detect_host(probe=False)
    return constants_for(profile, rss_cap_bytes=limits.max_rss_bytes).default_workers


class _Tail:
    """Thread-safe ring of the last ``cap`` bytes of a stream (stderr is kept, never parsed: G.4.3)."""

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._chunks: deque[bytes] = deque()
        self._size = 0
        self._lock = threading.Lock()

    def add(self, chunk: bytes) -> None:
        with self._lock:
            self._chunks.append(chunk)
            self._size += len(chunk)
            while self._size - len(self._chunks[0]) >= self._cap:
                self._size -= len(self._chunks.popleft())

    def value(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)[-self._cap :]


class _Worker:
    """One live T1 process and its supervision state. Created and torn down by one slot thread."""

    def __init__(self, pool: WorkerPool) -> None:
        self.pool = pool
        limits = pool.limits
        self.job_dir = tempfile.mkdtemp(prefix="agentprov-job-", dir=pool.work_dir)
        os.chmod(self.job_dir, 0o700)
        # The address-space cap never goes below the host's measured start-up footprint plus headroom (G.4.12).
        as_bytes = pool.constants.as_limit_for(limits.effective_as_bytes)
        self.as_enforced = pool.profile.caps.hard_memory_cap.value == "rlimit_as" and as_bytes > 0
        argv = [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "agentprov.worker",
            "--protocol",
            PROTOCOL,
            "--cpu-hard",
            str(limits.cpu_s_max * pool.jobs_per_worker + 60),
            "--nofile",
            str(limits.nofile),
            "--as-bytes",
            str(as_bytes if pool.profile.caps.hard_memory_cap.value == "rlimit_as" else 0),
        ]
        if pool.store_root is not None:
            argv += ["--store-root", os.fspath(pool.store_root)]
        if pool.test_kinds:
            argv.append("--test-kinds")
        try:
            self.proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=build_worker_env(self.job_dir),
                cwd=self.job_dir,
                close_fds=True,
                **spawn_kwargs(pool.profile),
            )
            self.killer: TreeKiller = attach_tree_killer(
                pool.profile, self.proc, memory_limit_bytes=as_bytes
            )
        except BaseException:
            proc = getattr(self, "proc", None)
            if proc is not None:
                proc.kill()
                proc.wait()
            shutil.rmtree(self.job_dir, ignore_errors=True)
            raise
        assert self.proc.stdin is not None and self.proc.stdout is not None and self.proc.stderr is not None
        self.stdin: IO[bytes] = self.proc.stdin
        self.stdout: IO[bytes] = self.proc.stdout
        self._stderr: Any = self.proc.stderr  # BufferedReader (read1)
        self.tail = _Tail(limits.stderr_tail_bytes)
        self._drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._drain.start()
        self.lock = threading.Lock()
        self.job_active = False
        self.deadline = math.inf
        self.rss_trigger = pool.constants.trigger_for(limits.rss_bytes)
        self.kill_reason: str | None = None
        self.peak_rss = 0
        self.jobs_done = 0
        self.ticket: _Ticket | None = None  # D-554: the admission ticket of the running job

    def _drain_stderr(self) -> None:
        try:
            while chunk := self._stderr.read1(8192):
                self.tail.add(chunk)
        except OSError, ValueError:
            pass

    # -- supervision (called from the watchdog thread and the slot thread) --

    def begin(self, limits: WorkerLimits) -> None:
        with self.lock:
            self.kill_reason = None
            self.peak_rss = 0
            self.rss_trigger = self.pool.constants.trigger_for(limits.rss_bytes)
            self.deadline = time.monotonic() + limits.wall_s
            self.job_active = True

    def end(self) -> str | None:
        """Stop watching. After this returns the watchdog can no longer kill this process."""
        with self.lock:
            self.job_active = False
            return self.kill_reason

    def kill_for(self, reason: str) -> None:
        with self.lock:
            if not self.job_active or self.kill_reason is not None:
                return
            self.kill_reason = reason
            self.killer.kill()

    def hard_kill(self) -> None:
        """Slot-thread kill: only valid while the process has not been reaped."""
        with self.lock:
            if self.proc.returncode is None:
                self.killer.kill()

    def poll_limits(self) -> None:
        """One watchdog tick for this worker (G.4.3)."""
        with self.lock:
            if not self.job_active or self.kill_reason is not None:
                return
            expired = time.monotonic() > self.deadline
        if expired:
            self.kill_for("wall")
            return
        sample = self.pool.rss_sampler
        rss = sample(self.proc.pid) if sample is not None else None
        if rss is None:
            return
        with self.lock:
            self.peak_rss = max(self.peak_rss, rss)
            trigger = self.rss_trigger
        if rss > trigger:
            self.kill_for("rss")

    def exit_signal_reason(self) -> tuple[str, int | None]:
        """Classify an unexpected end of stream after the watchdog is off: ``('cpu'|'crash', returncode)``."""
        try:
            code = self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.hard_kill()
            code = self.proc.wait()
        self._drain.join(timeout=5)  # the stderr tail is complete once the process has ended
        xcpu = getattr(signal, "SIGXCPU", None)
        return ("cpu" if xcpu is not None and code == -xcpu else "crash"), code

    def ran_out_of_address_space(self, code: int | None) -> bool:
        """A worker that exited non-zero under an enforced ``RLIMIT_AS`` with ``MemoryError`` in its stderr tail died of the
        limit (for example while importing before it could reply), which is a memory limit, not a crash."""
        return self.as_enforced and code not in (0, None) and b"MemoryError" in self.tail.value()

    def teardown(self, *, graceful: bool) -> bytes:
        """Stop the process, join stderr, remove the directory. Returns the stderr tail."""
        if graceful:
            try:
                self.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.hard_kill()
        else:
            self.hard_kill()
        self.proc.wait()
        self.killer.close()
        self._drain.join(timeout=5)
        for stream in (self.stdout, self._stderr):
            try:
                stream.close()
            except OSError:
                pass
        try:
            self.stdin.close()
        except OSError:
            pass
        shutil.rmtree(self.job_dir, ignore_errors=True)
        return self.tail.value()


class WorkerPool:
    """Runs jobs in T1 workers (or in-process for debugging) and returns results ordered by job key.

    ``workers=0`` means the host default (:func:`resolve_worker_count`). ``in_process=True`` runs the same dispatch
    and the same frame round trip in the calling process, with no isolation, limits or audit hook (G.4.9); it is
    refused together with ``release=True`` (exit 4).

    :meth:`prepare` (called by :meth:`run` and by :attr:`isolation`) detects the host, runs the allocation-rate
    calibration once per process where no hard memory cap exists, derives the constants and grades the isolation.
    In release mode a grade below ``watchdog`` raises :class:`IsolationInsufficientError` (exit 3); in dev mode it
    warns (:class:`IsolationDegradedWarning`) and the grade is recorded. ``host`` and ``calibration`` may be injected
    (tests, replay); injected values are used as given.
    """

    def __init__(
        self,
        *,
        workers: int = 1,
        limits: WorkerLimits | None = None,
        jobs_per_worker: int = 64,
        in_process: bool = False,
        release: bool = False,
        store_root: str | os.PathLike[str] | None = None,
        work_dir: str | os.PathLike[str] | None = None,
        spool_dir: str | os.PathLike[str] | None = None,
        watchdog_interval: float | None = None,
        test_kinds: bool = False,
        host: HostProfile | None = None,
        calibration: Calibration | None = None,
        _internal: bool = False,
        charge: Callable[[Job, Path | None], int] | None = None,
    ) -> None:
        if in_process and release:
            raise InProcessRefusedError("--in-process is refused together with --release")
        if jobs_per_worker < 1:
            raise ValueError("jobs_per_worker must be >= 1")
        if watchdog_interval is not None and watchdog_interval <= 0:
            raise ValueError("watchdog_interval must be > 0")
        self.limits = limits or WorkerLimits()
        self.release = release
        self._host_arg = host
        self._calibration_arg = calibration
        self._internal = _internal
        self._interval_override = watchdog_interval
        #: D-554: ``charge(job, store_root)``, a job's memory charge in bytes (affects timing only, never outputs). The store
        #: root lets a policy read the job's staged inputs (the parent's own sealed AERs). ``None``: no admission control
        self.charge = charge if charge is not None else _DEFAULT_CHARGE
        if self.charge is not None and workers == 0 and not in_process and ADMISSION_DEFAULT_SLOTS is not None:
            workers = admission_default_slots(host)  # memory gates admission; the count is the calibrated one (D-415)
        self.workers = resolve_worker_count(workers, self.limits, profile=host)
        self.jobs_per_worker = jobs_per_worker
        self.in_process = in_process
        self.store_root = None if store_root is None else Path(store_root)
        self.work_dir = None if work_dir is None else os.fspath(work_dir)
        #: where returned outputs spool (unnamed files; D-383, D-414); ``None``: ``$AGENTPROV_HOME/tmp/spool`` (0700)
        self.spool_dir = None if spool_dir is None else os.fspath(spool_dir)
        #: D-414: the memory budget of every result of this pool not yet closed
        self._budget = _Budget(SPOOL_MEMORY_PER_POOL)
        self.test_kinds = test_kinds
        self._table = kind_table(test_kinds=test_kinds)
        self._abort = threading.Event()
        self._active: set[_Worker] = set()
        self._active_lock = threading.Lock()
        self._prepare_lock = threading.Lock()
        self._prepared = False
        self.profile: HostProfile
        self.calibration: Calibration
        self.constants: HostConstants
        self.rss_sampler: Callable[[int], int | None] | None = None

    def prepare(self) -> None:
        """Detect the host, calibrate if needed, derive constants and enforce the isolation grade (idempotent)."""
        if self._prepared or self.in_process:
            return
        with self._prepare_lock:
            if self._prepared:
                return
            profile = self._host_arg or detect_host()
            caps = profile.caps
            calibration = self._calibration_arg
            if calibration is None:
                if caps.hard_memory_cap.value != "none":
                    calibration = Calibration.skipped("a hard memory cap is enforced")
                elif caps.rss_sampler.value == "none":
                    calibration = Calibration.skipped("no RSS sampler")
                else:
                    calibration = get_calibration(profile)
            constants = constants_for(profile, calibration, rss_cap_bytes=self.limits.rss_bytes)
            if self._interval_override is not None:
                constants = dataclasses.replace(constants, watchdog_interval_s=self._interval_override)
            if not self._internal and constants.grade == "degraded":
                detail = "; ".join(constants.grade_reasons)
                if self.release:
                    raise IsolationInsufficientError(
                        f"release mode needs isolation grade 'watchdog' or better; this host gives 'degraded': {detail}"
                    )
                warnings.warn(
                    f"worker isolation is degraded: {detail}", IsolationDegradedWarning, stacklevel=3
                )
            self.profile, self.calibration, self.constants = profile, calibration, constants
            self.rss_sampler = host_rss_sampler(profile)
            self._prepared = True

    @property
    def isolation(self) -> dict[str, Any]:
        """JSON-able record for the corpus ``producer`` block (G.4.9): mode, grade, host, constants, calibration.

        For worker mode this calls :meth:`prepare`, which may spawn the calibration worker once per process.
        """
        if self.in_process:
            return {"mode": "in-process", "grade": None, "note": "no process isolation, limits or audit hook"}
        self.prepare()
        return {
            "mode": "worker",
            "release": self.release,
            "grade": self.constants.grade,
            "grade_reasons": list(self.constants.grade_reasons),
            "host": self.profile.to_record(),
            "constants": self.constants.to_record(),
            "calibration": self.calibration.to_record(),
            "memory_caps": self.limits.caps_record(),
        }

    # -- public API --

    def run(self, jobs: Iterable[Job], progress: Progress | None = None) -> list[JobResult]:
        """Run every job; results are sorted by ``Job.key`` whatever the worker count or completion order.

        ``progress`` (MN N.1.14(6)) receives one ``unit_done`` event per finished job (key, status, duration, peak RSS,
        error code), emitted from the collecting slot thread right after the result is stored. The sink must not
        block (the pool never waits on it beyond an O(1) call) and an exception it raises is ignored; it never changes
        a result.
        """
        self.prepare()
        batch = list(jobs)
        keys = [j.key for j in batch]
        if len(set(keys)) != len(keys):
            raise ValueError("job keys must be unique")
        for job in batch:
            if job.kind not in self._table:
                raise WorkerProtocolError(
                    f"unknown job kind {_safe_text(job.kind)}", code="worker.protocol.unknown_kind"
                )
        numbered = list(enumerate(batch))
        results: dict[str, JobResult] = {}
        spool = _BatchSpool(self._spool_directory) if numbered else None  # D-414: one spool file per batch, if needed
        try:
            if self.in_process:
                for number, job in numbered:
                    results[job.key] = self._run_in_process(number, job, spool)
                    _report_job(progress, results[job.key])
            elif numbered:
                self._run_pool(numbered, results, progress, spool)
        finally:
            if spool is not None:
                spool.release()  # the results that hold it keep it open; closed with the last of them
        return [results[k] for k in sorted(results)]

    def _spool_directory(self) -> str:
        """The pool's spool directory, else ``$AGENTPROV_HOME/tmp/spool`` (default ``~/.agentprov``), created 0700."""
        if self.spool_dir is not None:
            return self.spool_dir
        home = os.environ.get("AGENTPROV_HOME") or os.path.join(os.path.expanduser("~"), ".agentprov")
        directory = os.path.join(home, "tmp", "spool")
        os.makedirs(directory, mode=0o700, exist_ok=True)
        return directory

    def run_one(self, job: Job) -> JobResult:
        return self.run([job])[0]

    # -- in-process (G.4.9) --

    def _run_in_process(self, number: int, job: Job, spool: _BatchSpool | None = None) -> JobResult:
        limits = (job.limits or self.limits).for_kind(job.kind)
        functions = preload_job_kinds(self._table)
        request = self._request(number, job, limits)
        buffer = io.BytesIO()
        started = time.monotonic()
        try:
            _request_line(request)  # the T1 limit, so that in-process and worker runs agree (D #11)
            run_job_request(
                validate_request(request, functions),
                functions,
                FrameWriter(buffer, max_frame_bytes=limits.max_frame_bytes),
                store_root=self.store_root,
            )
            buffer.seek(0)
            collected = _collect(buffer, number, limits, self.spool_dir, batch=spool,
                                 budget=self._budget if spool is not None else None)
            return JobResult(
                job.key,
                job.kind,
                number,
                tuple(collected.outputs),
                collected.counters,
                isolation="in-process",
                elapsed_s=time.monotonic() - started,
                _hold=collected.hold,
            )
        except _Failed as failed:
            error = _error_from_failed(failed)
        except WorkerError as exc:
            error = exc
        return JobResult(
            job.key,
            job.kind,
            number,
            error=error,
            isolation="in-process",
            elapsed_s=time.monotonic() - started,
        )

    # -- pool --

    @staticmethod
    def _request(number: int, job: Job, limits: WorkerLimits) -> dict[str, Any]:
        return {
            "v": PROTOCOL,
            "job": number,
            "kind": job.kind,
            "inputs": [dict(i) for i in job.inputs],
            "params": dict(job.params),
            "limits": limits.for_request(),
        }

    def _run_pool(
        self, numbered: list[tuple[int, Job]], results: dict[str, JobResult], progress: Progress | None = None,
        spool: _BatchSpool | None = None,
    ) -> None:
        queue = deque(numbered)
        queue_lock = threading.Lock()
        errors: list[BaseException] = []
        stop = threading.Event()
        self._abort.clear()

        admission = _admission(self.profile) if self.charge is not None else None
        self._admission = admission

        def take() -> tuple[int, Job, _Ticket | None] | None:
            """The next job, admitted (D-554: the wait is here, before any request is written)."""
            with queue_lock:
                item = queue.popleft() if queue and not self._abort.is_set() else None
            if item is None:
                return None
            number, job = item
            if admission is None:
                return number, job, None
            assert self.charge is not None
            ticket = admission.acquire(int(self.charge(job, self.store_root)), job.kind, self._abort)
            return None if ticket is None else (number, job, ticket)

        def slot() -> None:
            worker: _Worker | None = None
            last: JobResult | None = None  # the worker's latest result: it gets the complete stderr tail on retirement
            try:
                while (item := take()) is not None:
                    number, job, ticket = item
                    try:  # the ticket is released whatever happens after admission, a failed spawn included (D #12)
                        if worker is None:
                            worker = _Worker(self)
                            with self._active_lock:
                                self._active.add(worker)
                            if admission is not None:
                                admission.register(worker.proc.pid)
                        if ticket is not None and admission is not None:
                            admission.bind(ticket, worker.proc.pid)
                            worker.ticket = ticket
                        result, keep = self._execute(worker, number, job, spool)
                    finally:
                        if ticket is not None and admission is not None:
                            if worker is not None:
                                worker.ticket = None
                            admission.release(ticket)  # collected, killed or never started: the charge goes back now
                    results[job.key] = result  # distinct keys: no two slots write the same entry
                    _report_job(progress, result)
                    last = result
                    if keep and admission is not None and admission.lifetime_peak(worker.proc.pid) > ADMISSION_RETIRE_PEAK:
                        self._retire(worker, graceful=True, result=result, final=True)  # D-554: give its heap back
                        worker = None
                        continue
                    if not keep:
                        self._retire(worker, graceful=False, result=result)
                        worker = None
                if worker is not None:
                    self._retire(worker, graceful=True, result=last, final=True)
                    worker = None
            except BaseException as exc:  # noqa: BLE001 - surfaced after join
                errors.append(exc)
                self._abort.set()
                if admission is not None:
                    admission.wake()  # slots waiting for admission see the abort
            finally:
                if worker is not None:
                    self._retire(worker, graceful=False)

        def watchdog() -> None:
            while not stop.wait(self.constants.watchdog_interval_s):
                with self._active_lock:
                    live = list(self._active)
                for w in live:
                    w.poll_limits()
                    held = w.ticket
                    if admission is not None and held is not None:
                        admission.observe(held, w.proc.pid)

        threads = [
            threading.Thread(target=slot, name=f"agentprov-slot-{i}")
            for i in range(min(self.workers, len(numbered)))
        ]
        dog = threading.Thread(target=watchdog, name="agentprov-watchdog", daemon=True)
        dog.start()
        for t in threads:
            t.start()
        try:
            for t in threads:
                t.join()
        except BaseException:
            self._abort.set()
            if admission is not None:
                admission.wake()
            with self._active_lock:
                live = list(self._active)
            for w in live:
                w.hard_kill()
            for t in threads:
                t.join()
            raise
        finally:
            stop.set()
            dog.join(timeout=5)
            if admission is not None:  # D-554: the controller's numbers go to the log (counts and ratios only)
                _LOG.info("admission budget=%d stats=%s", admission.budget, jcs(admission.stats).decode("ascii"))
        if errors:
            raise errors[0]

    def _retire(self, worker: _Worker, *, graceful: bool, result: JobResult | None = None, final: bool = False) -> None:
        """Tear ``worker`` down; ``result`` (its latest) gets the stderr tail read after the drain thread is joined. A
        result's tail is otherwise the snapshot taken when its ``DONE`` arrived, which can precede the drain thread's read
        of the job's last stderr bytes (stdout and stderr are separate pipes); ``final`` replaces it with the complete
        tail."""
        with self._active_lock:
            self._active.discard(worker)
        tail = worker.teardown(graceful=graceful)
        admission = getattr(self, "_admission", None)
        if admission is not None:
            admission.unregister(worker.proc.pid)
        if result is not None and (final or not result.stderr_tail):
            result.stderr_tail = tail

    def _execute(self, worker: _Worker, number: int, job: Job, spool: _BatchSpool | None = None) -> tuple[JobResult, bool]:
        """Run one job in ``worker``. Returns the result and whether the worker may be reused."""
        limits = (job.limits or self.limits).for_kind(job.kind)
        try:
            line = _request_line(self._request(number, job, limits))
        except WorkerRequestTooLargeError as exc:  # never sent: the worker is untouched and stays usable
            return JobResult(job.key, job.kind, number, error=exc, isolation="worker", worker_pid=worker.proc.pid), True
        worker.begin(limits)
        started = time.monotonic()
        error: AgentProvError | None = None
        collected: _Collected | None = None
        kill_now = False
        try:
            try:
                worker.stdin.write(line)
                worker.stdin.flush()
            except BrokenPipeError, OSError:
                pass  # the read below sees EOF and classifies the exit
            try:
                collected = _collect(worker.stdout, number, limits, self.spool_dir, batch=spool,
                                     budget=self._budget if spool is not None else None)
            except _StreamEnded:
                reason = worker.end()
                if reason is not None:
                    error = WorkerLimitError(reason, f"worker killed by the watchdog: {reason} limit")
                else:
                    kind, code = worker.exit_signal_reason()
                    if kind == "cpu":
                        error = WorkerLimitError("cpu", "worker killed by SIGXCPU (CPU limit)")
                    elif worker.ran_out_of_address_space(code):
                        error = WorkerLimitError(
                            "rss", f"worker ran out of address space under the limit (return code {code})"
                        )
                    else:
                        error = WorkerCrashError(f"worker ended unexpectedly (return code {code})")
            except _Failed as failed:
                error = _error_from_failed(failed)
            except WorkerError as exc:
                error = exc
                kill_now = True
        finally:
            reason = worker.end()
        if error is None and reason is not None:
            error = WorkerLimitError(reason, f"worker killed by the watchdog: {reason} limit")
        if error is not None and collected is not None:
            if collected.hold is not None:
                collected.hold.close()  # members, budget and batch spool (D-414)
            else:
                for item in collected.outputs:
                    if isinstance(item, MemberOutput):
                        item.close()
            collected = None
        worker.jobs_done += 1
        result = JobResult(
            job.key,
            job.kind,
            number,
            tuple(collected.outputs) if collected else (),
            collected.counters if collected else {},
            error,
            "worker",
            time.monotonic() - started,
            worker.peak_rss or None,
            worker.tail.value(),
            worker.proc.pid,
            _hold=collected.hold if collected else None,
        )
        keep = error is None and not kill_now and worker.jobs_done < self.jobs_per_worker
        return result, keep


def _request_line(request: Mapping[str, Any]) -> bytes:
    """The request as the line a worker reads; :class:`WorkerRequestTooLargeError` above :data:`MAX_REQUEST_BYTES`."""
    line = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    if len(line) > MAX_REQUEST_BYTES:
        raise WorkerRequestTooLargeError(
            f"the request is {len(line)} bytes, above the {MAX_REQUEST_BYTES}-byte request limit (G.4.6)"
        )
    return line


def _report_job(progress: Progress | None, result: JobResult) -> None:
    """Report one finished job to the feedback sink (MN N.1.14(6)); never raises, never blocks beyond the sink's O(1)."""
    if progress is None:
        return
    fields: dict[str, str | int | float | bool | None] = {"kind": result.kind, "isolation": result.isolation}
    if result.peak_rss_bytes is not None:
        fields["peak_rss_bytes"] = result.peak_rss_bytes
    if result.worker_pid is not None:
        fields["worker_pid"] = result.worker_pid
    error = result.error
    try:
        progress.emit(
            ProgressEvent(
                "unit_done",
                unit=result.key,
                status="ok" if error is None else "failed",
                duration_s=result.elapsed_s,
                codes=() if error is None else (error.code,),
                fields=fields,
            )
        )
    except Exception:  # noqa: BLE001 - a failing display must never break the pool
        pass


def _error_from_failed(failed: _Failed) -> WorkerError:
    """Map a worker-reported ``FAIL`` to a typed error."""
    prefix = "worker.limit."
    if not _CODE_RE.fullmatch(failed.code):
        return WorkerJobError(f"{failed.exc_type}: {failed.message}")
    if failed.code.startswith(prefix) and failed.code[len(prefix) :] in WorkerLimitError.LIMITS:
        return WorkerLimitError(failed.code[len(prefix) :], failed.message)
    return WorkerJobError(f"{failed.exc_type}: {failed.message}", code=failed.code)


_CALIBRATION_LOCK = threading.Lock()
_CALIBRATION: Calibration | None = None


def get_calibration(profile: HostProfile, *, refresh: bool = False) -> Calibration:
    """The allocation-rate calibration, run once per process in a T1 worker (cached; no disk cache).

    Retried once. A failure is recorded as ``failed`` (and then grades the host ``degraded``), never hidden.
    """
    global _CALIBRATION
    with _CALIBRATION_LOCK:
        if _CALIBRATION is not None and not refresh:
            return _CALIBRATION
        pool = WorkerPool(
            workers=1,
            limits=WorkerLimits(cpu_s=30, cpu_s_max=30, wall_s=60),
            jobs_per_worker=1,
            host=profile,
            calibration=Calibration.skipped("calibrating"),
            _internal=True,
        )
        detail = "no attempt"
        result: Calibration | None = None
        for _ in range(2):
            outcome = pool.run_one(Job("calibrate", "calibrate"))
            if outcome.ok and outcome.json and outcome.json[0].get("alloc_rate_bytes_per_s"):
                data = outcome.json[0]
                result = Calibration(
                    "ok",
                    alloc_rate_bytes_per_s=float(data["alloc_rate_bytes_per_s"]),
                    duration_s=float(data["duration_s"]),
                    bytes_touched=int(data["bytes"]),
                    detail="allocation-rate probe in a T1 worker",
                )
                break
            detail = outcome.error.code if outcome.error else "no result"
        _CALIBRATION = result or Calibration("failed", detail=detail)
        return _CALIBRATION
