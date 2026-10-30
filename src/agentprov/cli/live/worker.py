"""The parent side of ``agentprov-backend/0.1`` (D.11.3; D.10.10 item 8; G.6.3; MN N.1.10(4), N.1.14).

The parent execs ``<env>/bin/python -I -B -m agentprov_backend.worker`` directly (no ``uv`` at run time, AD-01(c))
with an explicit environment (:func:`worker_environment`; G.6.3: ``PATH``, a redirected ``HOME``, ``LANG``, ``TZ``,
the selected endpoint's key variable only, ``AGENTPROV_BLOCK_NETWORK`` for scripted runs; never a ``UV_*`` variable,
never the real ``HOME``), its own process tree (killable with the D-7 tree kill), and stderr written to a staged file
that is never parsed.

A dedicated reader thread drains stdout continuously, so the pipe never fills (F2): every line is bounded (1 MiB) and
parsed with the core strict loader (duplicate keys, ``NaN``, lone surrogates and non-UTF-8 are violations); the
droppable ``step`` and ``progress`` messages go to the feedback callback; every other message is queued for the caller.
A violation, EOF or a ``fatal`` message ends the worker; the caller then treats the cell as a dead worker (N.1.10(4)).
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Final

from agentprov.errors import AgentProvError, BackendUnavailable

__all__ = [
    "MAX_LINE",
    "PROTOCOL",
    "BackendWorker",
    "WorkerDied",
    "WorkerTimeout",
    "make_private_dir",
    "worker_environment",
]

PROTOCOL: Final = "agentprov-backend/0.1"
MAX_LINE: Final = 1024 * 1024
_LOG = logging.getLogger(__name__)
_EOF: Final = object()


class WorkerDied(AgentProvError):
    """The worker exited, sent ``fatal``, or broke the protocol."""

    code = "backend.worker_died"
    exit_code = 1


class WorkerTimeout(AgentProvError):
    """No reply within the wall-clock budget."""

    code = "backend.worker_timeout"
    exit_code = 1


def make_private_dir(path: Path) -> Path:
    """Create ``path`` fresh, mode 0700 (it must not exist: a session directory is never reused)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.mkdir(path, 0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:  # pragma: no cover - hosts without POSIX permission bits (G.4.12(7))
        pass
    return path


def worker_environment(
    *, home: Path, key_variables: Mapping[str, str] | None = None, block_network: bool,
    parent_environ: Mapping[str, str] | None = None, nltk_data: str | None = None, egress_proxy: str | None = None,
    hf_cache: str | None = None,
) -> dict[str, str]:
    """The explicit T2 environment of G.6.3. Nothing else is inherited. ``nltk_data`` is the backend environment's
    verified NLTK directory (``envs.check_nltk``; AutoDojo, D.11.2), passed as ``NLTK_DATA``. ``egress_proxy`` is the
    URL of T0's egress proxy (D-664): ``AGENTPROV_EGRESS_PROXY`` for the recording transports, which take it
    explicitly, and ``HTTPS_PROXY``/``https_proxy`` for clients that read the environment. ``hf_cache`` is the
    environment's offline Hugging Face cache of a defence's pinned weights (D-672): passed as ``HF_HUB_CACHE`` with
    ``HF_HUB_OFFLINE=1``, ``TRANSFORMERS_OFFLINE=1`` and telemetry off, so loading them never reaches the network."""
    parent = os.environ if parent_environ is None else parent_environ
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8", "TZ": "UTC"}
    system_root = parent.get("SYSTEMROOT")
    if system_root:  # the Windows loader needs it (as for T1 workers, host.minimal_environment)
        env["SYSTEMROOT"] = system_root
        env["PATH"] = os.path.join(system_root, "System32")
    for name, value in (key_variables or {}).items():
        env[name] = value
    if block_network:
        env["AGENTPROV_BLOCK_NETWORK"] = "1"
    if nltk_data is not None:
        env["NLTK_DATA"] = nltk_data
    if egress_proxy is not None:
        env["AGENTPROV_EGRESS_PROXY"] = env["HTTPS_PROXY"] = env["https_proxy"] = egress_proxy
    if hf_cache is not None:
        env.update({"HF_HUB_CACHE": hf_cache, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                    "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false"})
    return env


@dataclass
class WorkerSpec:
    argv: Sequence[str]
    env: Mapping[str, str]
    cwd: Path
    stderr_path: Path


def _limits() -> Any:
    from agentprov.ingest.limits import IngestLimits

    return IngestLimits().replace(max_jsonl_line_bytes=MAX_LINE)


def encode(op: str, **fields: Any) -> bytes:
    """One protocol line (JCS, ASCII-safe UTF-8, LF)."""
    from agentprov.io.canonical import jcs_bytes

    data = jcs_bytes({"v": PROTOCOL, "op": op, **fields}) + b"\n"
    if len(data) > MAX_LINE:
        raise AgentProvError(f"{op} message exceeds 1 MiB", code="backend.protocol")
    return data


_RUNNING: set[BackendWorker] = set()
_RUNNING_LOCK = threading.Lock()


def kill_all_workers() -> int:
    """Kill the process tree of every started, unclosed worker without waiting; returns how many were killed.

    The second SIGINT/SIGTERM/SIGHUP ``os._exit``s at once (N.1.10(3)). A worker runs in its own session and ignores a
    closed pipe, so without this it would be orphaned and finish its cell, making paid calls (CC-27). Signal-safe enough
    for that path: no waiting, no locks held by the caller, every failure ignored."""
    with _RUNNING_LOCK:
        workers = list(_RUNNING)
    killed = 0
    for worker in workers:
        try:
            if worker._killer is not None:
                worker._killer.kill()
                killed += 1
        except Exception:  # noqa: BLE001, S110 - best effort on the way out
            pass
    return killed


class BackendWorker:
    """One running backend worker. Not thread-safe: one caller drives it; the reader thread only queues."""

    def __init__(self, spec: WorkerSpec, *, on_step: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        self.spec = spec
        self.id = uuid.uuid4().hex[:12]
        self._on_step = on_step
        self._replies: queue.Queue[Any] = queue.Queue()
        self._proc: subprocess.Popen[bytes] | None = None
        self._killer: Any = None
        self._stderr: IO[bytes] | None = None
        self._reader: threading.Thread | None = None
        self.violation: str | None = None
        self.steps = 0

    # -------------------------------------------------------------------------------------- lifecycle
    def start(self) -> None:
        from agentprov.host import attach_tree_killer, detect_host, spawn_kwargs

        profile = detect_host(probe=False)
        self.spec.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = open(self.spec.stderr_path, "ab")  # noqa: SIM115 - closed in close()
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - argv is the environment's interpreter, built by us
                list(self.spec.argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
                env=dict(self.spec.env), cwd=self.spec.cwd, close_fds=True, **spawn_kwargs(profile),
            )  # fmt: skip
        except OSError as exc:
            self._stderr.close()
            raise BackendUnavailable(f"the backend worker could not be started: {type(exc).__name__}") from None
        self._killer = attach_tree_killer(profile, self._proc)
        with _RUNNING_LOCK:
            _RUNNING.add(self)
        self._reader = threading.Thread(target=self._read, name=f"agentprov-backend-reader-{self.id}", daemon=True)
        self._reader.start()

    @property
    def pid(self) -> int | None:
        return None if self._proc is None else self._proc.pid

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and self.violation is None

    def _read(self) -> None:
        from agentprov.errors import IngestError
        from agentprov.ingest.loaders import strict_json_loads

        assert self._proc is not None and self._proc.stdout is not None
        stream = self._proc.stdout
        limits = _limits()
        try:
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    self.violation = "a protocol line exceeds 1 MiB or is not LF-terminated"
                    break
                try:
                    msg = strict_json_loads(line[:-1], limits, record=True)
                except IngestError as exc:
                    self.violation = f"a protocol line is not strict JSON ({exc.code})"
                    break
                if not isinstance(msg, dict) or msg.get("v") != PROTOCOL or not isinstance(msg.get("op"), str):
                    self.violation = f"a protocol line is not an {PROTOCOL} message"
                    break
                if msg["op"] in ("step", "progress"):
                    self.steps += 1
                    if self._on_step is not None:
                        try:
                            self._on_step(msg)
                        except Exception:  # noqa: BLE001 - feedback never breaks the run (F2)
                            pass
                    continue
                self._replies.put(msg)
        except (OSError, ValueError):
            pass
        finally:
            self._replies.put(_EOF)

    def send(self, op: str, **fields: Any) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise WorkerDied("the worker is not running")
        try:
            self._proc.stdin.write(encode(op, **fields))
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            raise WorkerDied("the worker closed its input") from None

    def receive(self, timeout: float) -> dict[str, Any]:
        """The next non-step message. Raises :class:`WorkerTimeout` or :class:`WorkerDied`."""
        try:
            msg = self._replies.get(timeout=max(0.0, timeout))
        except queue.Empty:
            raise WorkerTimeout(f"no reply within {timeout:g} s") from None
        if msg is _EOF:
            self._replies.put(_EOF)  # later receives see the end too
            raise WorkerDied(self.violation or "the worker exited")
        assert isinstance(msg, dict)
        if msg.get("op") == "fatal":
            error = msg.get("error")
            kind = error.get("type") if isinstance(error, dict) else None
            raise WorkerDied(f"the worker sent fatal ({kind if isinstance(kind, str) else 'unknown'})")
        return msg

    def request(self, op: str, replies: str | Sequence[str], timeout: float, **fields: Any) -> dict[str, Any]:
        """Send ``op`` and return the next reply, which must be one of ``replies``."""
        self.send(op, **fields)
        wanted = (replies,) if isinstance(replies, str) else tuple(replies)
        deadline = time.monotonic() + timeout
        msg = self.receive(deadline - time.monotonic())
        if msg.get("op") not in wanted:
            self.violation = f"unexpected reply {str(msg.get('op'))[:40]!r} to {op}"
            raise WorkerDied(self.violation)
        return msg

    def kill(self) -> None:
        """Kill the worker's process tree (N.1.10(4))."""
        if self._killer is not None:
            self._killer.kill()
        if self._proc is not None:
            try:
                self._proc.wait(timeout=30)
            except subprocess.TimeoutExpired:  # pragma: no cover - a kill that did not take
                self._proc.kill()

    def shutdown(self, timeout: float = 15.0) -> None:
        """``shutdown``, then wait; kill the tree if it does not exit."""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                self.send("shutdown")
            except WorkerDied:
                pass
            try:
                if self._proc.stdin is not None:
                    self._proc.stdin.close()
            except OSError:
                pass
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.kill()
        self.close()

    def close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self.kill()
        with _RUNNING_LOCK:
            _RUNNING.discard(self)
        if self._reader is not None:
            self._reader.join(timeout=10)
        if self._killer is not None:
            self._killer.close()
        for handle in (self._proc.stdin if self._proc else None, self._proc.stdout if self._proc else None):
            try:
                if handle is not None:
                    handle.close()
            except OSError:
                pass
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    @property
    def returncode(self) -> int | None:
        return None if self._proc is None else self._proc.poll()
