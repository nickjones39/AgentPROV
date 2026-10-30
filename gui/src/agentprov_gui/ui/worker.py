"""Background work for the UI (design §2.3 "Threads"): a function runs in the global ``QThreadPool`` and its result
comes back to the UI thread through queued signals.

The signal object is created on the UI thread and parented to the requesting widget, not owned by the ``QRunnable``:
the pool deletes a runnable as soon as ``run`` returns, and a queued "done" event whose sender is already destroyed is
dropped by Qt. The signal object is deleted after it delivered its result.

Errors are reported by a closed code (``AgentProvError.code``) or an exception type name, never by message text, which
could carry data.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from agentprov.errors import AgentProvError
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

__all__ = ["JobSignals", "submit"]


class JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class _Runnable(QRunnable):
    def __init__(self, fn: Callable[[JobSignals], Any], signals: JobSignals) -> None:
        super().__init__()
        self.fn, self.signals = fn, signals

    def run(self) -> None:
        try:
            result = self.fn(self.signals)
        except AgentProvError as exc:
            self._emit(self.signals.failed, exc.code)
        except Exception as exc:
            self._emit(self.signals.failed, type(exc).__name__)
        else:
            self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal: Any, value: object) -> None:
        # The requesting widget (and so the signal object) may be gone, e.g. a closed Viewer tab (D-843): drop the result.
        with contextlib.suppress(RuntimeError):
            signal.emit(value)


def submit(
    owner: QObject,
    fn: Callable[[JobSignals], Any],
    done: Callable[[Any], None],
    failed: Callable[[str], None] | None = None,
    progress: Callable[[int], None] | None = None,
    pool: QThreadPool | None = None,
) -> JobSignals:
    """Run ``fn(signals)`` in the pool; ``done(result)`` or ``failed(code)`` runs on the UI thread."""
    signals = JobSignals(owner)

    def finish_done(result: Any) -> None:
        signals.deleteLater()
        done(result)

    def finish_failed(code: str) -> None:
        signals.deleteLater()
        if failed is not None:
            failed(code)

    signals.done.connect(finish_done)
    signals.failed.connect(finish_failed)
    if progress is not None:
        signals.progress.connect(progress)
    (pool or QThreadPool.globalInstance()).start(_Runnable(fn, signals))
    return signals
