"""One short R0/R1 call of the configured ``agentprov`` CLI (no Qt): ``prices``, ``settings`` and the other
application commands the GUI's panes use (reverse CLI parity, D-700). The child gets the allowlisted environment
only; its stdout is bounded."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from typing import Final

from agentprov_gui.jobs.manager import CliLocator, allowlisted_env

__all__ = ["call", "last_line"]

MAX_STDOUT: Final = 64 * 1024 * 1024


def call(cli: CliLocator, argv: Sequence[str], *, timeout: float | None = 120,
         stdin: bytes | None = None) -> tuple[int, bytes, bytes]:
    """``(exit code, stdout, stderr tail)`` of ``agentprov ARGV``; 127 without a CLI, 124 when it cannot run.
    ``stdin`` is the child's whole standard input (``assist`` reads its conversation there); else it has none."""
    if not cli.available:
        return 127, b"", b"no CLI"
    try:
        done = subprocess.run(  # noqa: S603 - the configured CLI and a fixed argv
            [*cli.program, *argv, "--progress", "off", "--no-colour"], capture_output=True, timeout=timeout,
            check=False, env=allowlisted_env(), input=stdin,
            stdin=None if stdin is not None else subprocess.DEVNULL, cwd=cli.cwd_for(argv))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, b"", type(exc).__name__.encode()
    return done.returncode, done.stdout[:MAX_STDOUT], done.stderr[-4096:]


#: The CLI's own INFO/DEBUG log lines (``LEVEL agentprov...: message``, N.1.12(2)): the closing ``end command=...`` line
#: is always last on stderr, so it is skipped to reach the reason (review UC-15).
_LOG_LINE: Final = re.compile(r"(?:INFO|DEBUG) agentprov[\w.]*: ")


def last_line(err: bytes) -> str:
    """The last stderr line that is not an INFO/DEBUG log line (the CLI's reason), for a message box."""
    lines = [x for x in err.decode("utf-8", "replace").splitlines() if x.strip() and not _LOG_LINE.match(x)]
    return lines[-1] if lines else ""
