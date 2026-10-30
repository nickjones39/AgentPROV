"""The process-wide drain request (D-394): library code checks it, the CLI's control-file watcher sets it.

A command that honours a drain calls :func:`drain_supported` once and :func:`draining` at its unit boundaries: when it is
set, it schedules no new unit, finishes the in-flight ones, flushes and returns normally (progress outcome ``drained``).
Library code never reads the control file itself; :mod:`agentprov.cli.control` does. Nothing here reaches any output.
"""

from __future__ import annotations

import threading

__all__ = ["drain_supported", "draining", "is_supported", "request", "reset"]

_drain = threading.Event()
_supported = threading.Event()


def drain_supported() -> None:
    """Called once by a command that checks :func:`draining` at its unit boundaries."""
    _supported.set()


def is_supported() -> bool:
    return _supported.is_set()


def draining() -> bool:
    """Whether an accepted drain asks the command to stop scheduling new units."""
    return _drain.is_set()


def request() -> None:
    """Accept a drain (the control-file watcher, only when :func:`is_supported`)."""
    _drain.set()


def reset() -> None:
    """Forget the drain state (one CLI invocation per process; tests run several)."""
    _drain.clear()
    _supported.clear()
