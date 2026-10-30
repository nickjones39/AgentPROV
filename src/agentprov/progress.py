"""Library-side live-feedback interface (docs/architecture MN N.1.14(6); DECISIONS D-8).

Library code never prints and never configures output (N.1.12(1)). It reports how a long-running operation is
going through a :class:`Progress` sink: one method, :meth:`Progress.emit`, taking a :class:`ProgressEvent`. The
default is :data:`NULL_PROGRESS`, which does nothing. The CLI installs a sink (``agentprov.cli.feedback``) that turns
events into the status line, step lines, the end-of-run table and ``agentprov-progress/0.2`` JSON lines.

Contract for every sink (binding; DECISIONS D-8 guarantee F2, "no back-pressure"):

* ``emit`` returns quickly and never blocks on I/O: it does O(1) work, such as updating counters and enqueuing the
  event on a bounded queue that drops (and counts) when full;
* ``emit`` never raises into the caller (a producer ignores nothing it needs, so a failing display must not break a
  capture or an import);
* a sink never changes what the caller computes or writes (F1) and no decision may depend on which sink is installed
  or on its level (F4).

Events are **metadata only**. Strings that originate in a run or in imported data (unit ids, tool names, model ids,
issue details) are untrusted; the sink passes every one of them through ``escape_untrusted`` before display. The one
carrier of content is :attr:`ProgressEvent.content`: it is shown only when the user passes ``--show-content``, and
then only through ``quote_untrusted``, truncated.

Event kinds (``kind``), the level at which the CLI shows each, and the fields each uses:

``start`` (summary)
    The start banner. ``total`` is the number of units planned, when known. ``fields`` conventionally carry
    ``command``, ``source`` or ``backend``, ``plan``, ``workers`` and ``isolation`` (the isolation grade).
``unit_start`` (status)
    A unit began; ``unit`` names it. It sets the "current unit" of the status line.
``unit_done`` (status; a line at ``steps``)
    A unit finished. ``status`` is a short outcome word (for example ``sealed``, ``sealed_with_issues``, ``failed``,
    ``refused``, ``ok``), ``duration_s`` its wall time, ``codes`` its issue or register codes.
``step`` (steps)
    A stage of a unit finished (for imports and derivation: read, map, seal, SEM, PROV, validate; for live runs: a
    model call, a tool call, a defence decision). ``stage`` names it, ``unit`` is the unit, ``duration_s`` its time.
``trace`` (trace)
    Pipeline internals: sequence numbers, hash-chain head, bytes written, worker pid, peak RSS, per-stage timings.

``stage`` (status; ``agentprov-progress/0.2``, D-393)
    A corpus-level stage began or ended: ``stage`` names it, ``fields`` carry ``phase`` (``begin``/``end``) and, when
    known, ``done``, ``total`` and ``failed``; ``duration_s`` on ``end``.
``worker`` (status; 0.2)
    A T1/T2 worker or a ``dot`` process started or exited: ``fields`` carry ``pid``, ``tier`` (``t1``/``t2``/``dot``),
    ``phase`` (``spawn``/``exit``) and optionally ``slot``, ``exit_code``, ``rss_peak``.
``session`` (status; 0.2, live runs)
    A capture session started or ended: ``unit`` is the cell, ``fields`` carry ``session``, ``attempt``, ``staging``
    (relative to ``AGENTPROV_HOME``) and ``status`` on the end.
``control`` (summary; 0.2, D-394)
    A ``--control-file`` request was seen: ``fields`` carry ``request``, ``nonce``, ``accepted`` and ``effect``.

``fields`` values are scalars (``str | int | float | bool | None``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

__all__ = [
    "EVENT_KINDS",
    "NULL_PROGRESS",
    "FieldValue",
    "NullProgress",
    "Progress",
    "ProgressEvent",
]

EVENT_KINDS: Final[tuple[str, ...]] = ("start", "unit_start", "unit_done", "step", "trace", "stage", "worker", "session",
                                       "control")

FieldValue = str | int | float | bool | None

_NO_FIELDS: Final[Mapping[str, FieldValue]] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One progress event. Immutable; every string in it may be untrusted (see the module docstring)."""

    kind: str
    unit: str | None = None
    status: str | None = None
    stage: str | None = None
    duration_s: float | None = None
    total: int | None = None
    codes: tuple[str, ...] = ()
    fields: Mapping[str, FieldValue] = _NO_FIELDS
    content: str | None = None
    locator: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"unknown progress event kind: {self.kind!r}")


class Progress(Protocol):
    """A progress sink. ``emit`` must be non-blocking, O(1) and must not raise (see the module docstring)."""

    def emit(self, event: ProgressEvent) -> None: ...


class NullProgress:
    """The default sink: discards every event."""

    __slots__ = ()

    def emit(self, event: ProgressEvent) -> None:
        return None


NULL_PROGRESS: Final[Progress] = NullProgress()
