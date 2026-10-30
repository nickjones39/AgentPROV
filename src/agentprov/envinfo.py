"""Interpreter guard (AD-16 as ruled in Addendum B; docs/architecture G.3.8, SEC-26).

Two parser fixes landed only in CPython 3.14.8: CVE-2026-15310 (pre-allocation while decompressing bzip2, LZMA
or Zstandard zip members) and CVE-2026-19672. Below that floor:

* release mode refuses to open any archive or compressed stream (error ``ingest.interpreter.unpatched``, exit 3);
* dev mode warns and returns the advisory record so the caller can store it in ``corpus.json`` and
  ``register.jsonl``;
* ``package`` refuses a corpus whose manifest records an advisory (exit 4).

There is one floor constant, no advisory table and no override. The floor moves only by a reviewed commit.
``capture_environment()`` (L.2.2) is not implemented here: its field list is not fully specified in L.2.2 and
depends on modules that do not exist yet.
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import AgentProvError, IngestError

INTERPRETER_FLOOR: Final[tuple[int, int, int]] = (3, 14, 8)
MISSING_CVES: Final[tuple[str, ...]] = ("CVE-2026-15310", "CVE-2026-19672")
UNPATCHED_CODE: Final = "ingest.interpreter.unpatched"

EXIT_ENVIRONMENT: Final = 3  # N.1.3 `environment`
EXIT_REFUSED: Final = 4  # N.1.3 `refused`

_FLOOR_TEXT: Final = ".".join(map(str, INTERPRETER_FLOOR))


class InterpreterUnpatchedWarning(Warning):
    """Dev-mode warning (code ``ingest.interpreter.unpatched``).

    Deliberately not a ``UserWarning``: the test configuration turns ``UserWarning`` from ``agentprov.*`` into errors.
    """


class InterpreterUnpatchedError(IngestError):
    """Release mode: archive or compressed-stream ingestion below the floor. Exit 3 (environment).

    An :class:`IngestError`, so every tier-1 refusal shares one type (K.11.1 F-1).
    """

    def __init__(self, message: str) -> None:
        super().__init__(UNPATCHED_CODE, message, exit_code=EXIT_ENVIRONMENT)


class InterpreterAdvisoryRefusedError(AgentProvError):
    """``package`` or the release builder was given a corpus that records an advisory. Exit 4 (refused).

    Reuses the register code of the advisory itself: the spec assigns no separate code to this refusal.
    """

    code = UNPATCHED_CODE
    exit_code = EXIT_REFUSED


@dataclass(frozen=True, slots=True)
class InterpreterAdvisory:
    """The fixed advisory record (HL H.2.7 ``interpreter_advisory``)."""

    python_version: str
    floor: str = _FLOOR_TEXT
    missing: tuple[str, ...] = MISSING_CVES

    def to_json(self) -> dict[str, Any]:
        return {"floor": self.floor, "python_version": self.python_version, "missing": list(self.missing)}


def _running_version() -> tuple[int, int, int]:
    info = sys.version_info
    return (int(info[0]), int(info[1]), int(info[2]))


def interpreter_advisory() -> InterpreterAdvisory | None:
    """Return ``None`` at or above the floor, else the fixed advisory record. Reads ``sys.version_info`` at call time."""
    version = _running_version()
    if version >= INTERPRETER_FLOOR:
        return None
    return InterpreterAdvisory(python_version=".".join(map(str, version)))


def require_patched_for_archive(*, release: bool) -> InterpreterAdvisory | None:
    """Call before opening any archive or compressed stream.

    At or above the floor: return ``None``, silently. Below it: in release mode raise
    :class:`InterpreterUnpatchedError`; otherwise emit :class:`InterpreterUnpatchedWarning` and return the advisory
    for the caller to record. There is no override.
    """
    advisory = interpreter_advisory()
    if advisory is None:
        return None
    cves = ", ".join(advisory.missing)
    if release:
        raise InterpreterUnpatchedError(
            f"release mode refuses archive and compressed-stream ingestion on Python "
            f"{advisory.python_version}, below the floor {advisory.floor} (missing fixes for {cves}). "
            f"Install Python {advisory.floor} (uv >= 0.12.22 can install it) and re-run."
        )
    warnings.warn(
        f"{UNPATCHED_CODE}: Python {advisory.python_version} is below {advisory.floor}; archive and "
        f"compressed-stream ingestion lacks the fixes for {cves}. Continuing in dev mode; the corpus will "
        "record an interpreter_advisory and cannot be packaged for release.",
        InterpreterUnpatchedWarning,
        stacklevel=2,
    )
    return advisory


def refuse_advisory_manifest(manifest: Mapping[str, Any]) -> None:
    """Used by ``package`` and the release builder: refuse a manifest whose producer records an advisory."""
    producer = manifest.get("producer")
    advisory = producer.get("interpreter_advisory") if isinstance(producer, Mapping) else None
    if advisory is not None:
        raise InterpreterAdvisoryRefusedError(
            f"{UNPATCHED_CODE}: refusing to package a corpus built on an interpreter below {_FLOOR_TEXT} "
            "(corpus.json records an interpreter_advisory). Re-import it on a patched interpreter "
            f"(Python {_FLOOR_TEXT}; uv >= 0.12.22 can install it)."
        )
