"""``--control-file``: a cross-platform drain or stop request for a running command (D-394; design.md §4.6).

A job manager (the GUI) cannot stop a job gracefully on Windows (``TerminateProcess`` is not graceful) and must not tie
the job to itself with a pipe. So it writes ``{"format":"agentprov-control/0.1","request":"drain"|"stop","issued":
"<RFC 3339>","nonce":"<16 hex>"}`` atomically to the file named by ``--control-file``, and the CLI polls it.

* **Polling.** A daemon thread ``stat``s the file at most once per ``poll_s`` (1 s): a few microseconds per poll. Only a
  changed file (size, mtime or inode) is read, at most 4 KiB, with the strict loader. A request already in the file
  when the command starts belongs to an earlier invocation (a drain is resumed by re-running the same argv) and is
  ignored, as is a nonce seen before.
* **``stop``** behaves like the first SIGTERM on every OS: the watcher simulates that signal in the main thread
  (``_thread.interrupt_main``), so the command takes the clean interrupt path (seal or roll back, release the lock,
  exit 130, N.1.10(2)).
* **``drain``** asks the command to finish its in-flight units, flush and exit with outcome ``drained`` (exit 0). A
  command honours it by calling :func:`drain_supported` once and :func:`draining` at its unit boundaries. A command that
  does not (today: all of them; ``import`` until its importer piece lands) degrades the drain to a stop, and says so.
* **Acknowledgement.** Every request seen is echoed as a ``control`` progress event ``{request, nonce, accepted,
  effect}``. An invalid or unknown request is logged and acknowledged as not accepted; it never stops anything.

Nothing here reaches a corpus, a summary's bytes or a stage digest.
"""

from __future__ import annotations

import _thread
import logging
import os
import re
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agentprov import drain as _drain_state
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent

__all__ = [
    "CONTROL_FORMAT",
    "REQUESTS",
    "ControlRequest",
    "ControlWatcher",
    "drain_supported",
    "draining",
    "reset",
]

CONTROL_FORMAT: Final = "agentprov-control/0.1"
REQUESTS: Final = ("drain", "stop")
POLL_S: Final = 1.0
_MAX_BYTES: Final = 4096
_NONCE = re.compile(r"[0-9a-f]{16}")
_LOG = logging.getLogger(__name__)

#: The drain state lives in the core (:mod:`agentprov.drain`), so library code can check it without importing the CLI.
drain_supported = _drain_state.drain_supported
draining = _drain_state.draining
reset = _drain_state.reset


@dataclass(frozen=True)
class ControlRequest:
    request: str
    nonce: str
    issued: str


def parse_request(data: bytes) -> ControlRequest | str:
    """The request in ``data``, or the reason it is refused (never echoing the file's text)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    if len(data) > _MAX_BYTES:
        return "larger than 4 KiB"
    try:
        doc = strict_json_loads(data.strip())
    except IngestError as exc:
        return f"not strict JSON ({exc.code})"
    if not isinstance(doc, dict) or doc.get("format") != CONTROL_FORMAT:
        return f"not an {CONTROL_FORMAT} object"
    request, nonce, issued = doc.get("request"), doc.get("nonce"), doc.get("issued")
    if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
        return "the nonce is not 16 lower-case hex digits"
    if not isinstance(issued, str) or not 0 < len(issued) <= 40:
        return "issued is not a timestamp"
    if request not in REQUESTS:
        return "unknown request"
    return ControlRequest(str(request), nonce, issued)


class ControlWatcher:
    """Polls one ``--control-file`` in a daemon thread; see the module docstring. ``interrupt`` stands in for the
    simulated SIGTERM (tests)."""

    def __init__(self, path: str | os.PathLike[str], *, command: str, progress: Progress = NULL_PROGRESS,
                 poll_s: float = POLL_S, interrupt: Callable[[], None] | None = None) -> None:
        self.path = Path(path)
        self.command = command
        self._progress = progress
        self._poll_s = poll_s
        self._interrupt = interrupt or _interrupt_main
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._identity: tuple[int, int, int] | None = None
        self._seen: set[str] = set()
        #: What the last accepted request did (``stop``, ``drain``, or ``stop (drain not supported ...)``).
        self.effect: str | None = None
        self.accepted: ControlRequest | None = None

    def _stat(self) -> tuple[int, int, int] | None:
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_size, st.st_mtime_ns, st.st_ino)

    def _read(self) -> bytes | None:
        try:
            with open(self.path, "rb") as handle:
                return handle.read(_MAX_BYTES + 1)
        except OSError:
            return None

    def start(self) -> None:
        reset()
        self._identity = self._stat()
        if self._identity is not None:  # a request left by an earlier invocation is never acted on again
            data = self._read()
            found = parse_request(data) if data is not None else None
            if isinstance(found, ControlRequest):
                self._seen.add(found.nonce)
        self._thread = threading.Thread(target=self._run, name="agentprov-control", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.wait(self._poll_s):
            try:
                self.poll()
            except Exception:  # noqa: BLE001 - a broken control file never breaks the command
                _LOG.warning("control file: poll failed", exc_info=True)

    def poll(self) -> None:
        """One poll: act on a new request (called by the thread; tests call it directly)."""
        identity = self._stat()
        if identity is None or identity == self._identity:
            return
        self._identity = identity
        data = self._read()
        if data is None:
            return
        found = parse_request(data)
        if isinstance(found, str):
            _LOG.warning("control file: request ignored: %s", found)
            self._ack("?", "?", accepted=False, effect=f"ignored: {found}")
            return
        if found.nonce in self._seen:
            return
        self._seen.add(found.nonce)
        if self.accepted is not None and self.accepted.request == "stop":
            self._ack(found.request, found.nonce, accepted=False, effect="ignored: a stop is already under way")
            return
        if found.request == "drain" and _drain_state.is_supported():
            self.accepted, self.effect = found, "drain"
            _drain_state.request()
            self._ack(found.request, found.nonce, accepted=True, effect="drain")
            return
        effect = "stop" if found.request == "stop" else f"stop (drain is not supported by {self.command} yet)"
        self.accepted, self.effect = found, effect
        self._ack(found.request, found.nonce, accepted=True, effect=effect)
        self._interrupt()

    def _ack(self, request: str, nonce: str, *, accepted: bool, effect: str) -> None:
        self._progress.emit(ProgressEvent("control", fields={"request": request, "nonce": nonce, "accepted": accepted,
                                                             "effect": effect}))

    def notice(self) -> str | None:
        """The summary notice for an accepted request (the nonce, never the file's other text)."""
        if self.accepted is None:
            return None
        return f"control file: {self.accepted.request} (nonce {self.accepted.nonce}): {self.effect}"


def _interrupt_main() -> None:
    """The first SIGTERM, simulated in the main thread (Windows included): the clean interrupt path."""
    _thread.interrupt_main(getattr(signal, "SIGTERM", signal.SIGINT))
