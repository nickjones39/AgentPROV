"""The GUI's side of ``agentprov settings`` (D-703; reverse CLI parity D-700). No Qt.

Every setting that affects a run, its data, the estimate or stored state is an ``agentprov settings`` key: the panes
read them with ``settings list --prefix P --format json`` and write only the keys that changed with ``settings set``
and ``settings unset`` (the CLI's schema is the check; a refused value comes back as a reason). The GUI's own
presentational settings (theme, palette, text size, the native toolbar, window geometry, viewer limits, corpus roots)
and the checkout whose CLI it runs stay in Qt's settings (D-700's exclusions).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agentprov_gui.jobs.manager import CliLocator
from agentprov_gui.live.cli import call, last_line

__all__ = ["NO_CLI", "Caller", "list_argv", "plan", "read", "read_or_reason", "text", "unavailable", "write"]

#: why a pane that runs ``agentprov`` cannot be used, and what to set (D-1030)
NO_CLI = ("No agentprov program to run: set the AgentPROV checkout, or the agentprov installed with pip install "
          "agentprov, in Settings › General, press OK and open Settings again.")

#: how an ``agentprov`` command is run: a CLI locator, or a callable such as :meth:`JobManager.call` (its home)
Caller = CliLocator | Callable[[Sequence[str]], tuple[int, bytes, bytes]]


def _run(cli: Caller, argv: list[str]) -> tuple[int, bytes, bytes]:
    return call(cli, argv) if isinstance(cli, CliLocator) else cli(argv)


def unavailable(command: str, code: int, err: bytes) -> str:
    """Why ``agentprov COMMAND`` gave nothing, in words that say what to set: no CLI (127, :data:`NO_CLI`), a CLI that
    cannot be started (124), else its exit code and its reason line (``last_line``; escaped where shown)."""
    if code == 127 and err == b"no CLI":
        return NO_CLI
    if code == 124:
        return (f"agentprov could not be run ({err.decode('ascii', 'replace')[:40]}): check the checkout or the "
                "agentprov program in Settings › General.")
    reason = last_line(err)
    return f"agentprov {command} ended with exit {code}" + (f": {reason}" if reason else "") + (
        "" if code else " (its answer was not a settings list: is the CLI older than this app?)")


def list_argv(prefix: str) -> list[str]:
    """``settings list`` for the keys under ``prefix`` (what a pane reads, and its terminal command)."""
    return ["settings", "list", "--prefix", prefix, "--format", "json"]


def read_or_reason(cli: Caller, prefix: str) -> dict[str, Any] | str:
    """The stored values under ``prefix`` (already checked by the schema), or why they cannot be read
    (:func:`unavailable`)."""
    code, out, err = _run(cli, list_argv(prefix))
    if code != 0:
        return unavailable("settings list", code, err)
    try:
        values = json.loads(out).get("values")
    except (ValueError, AttributeError):
        values = None
    return values if isinstance(values, dict) else unavailable("settings list", 0, err)


def read(cli: Caller, prefix: str) -> dict[str, Any] | None:
    """The stored values under ``prefix`` (already checked by the schema), or ``None`` when they cannot be read."""
    values = read_or_reason(cli, prefix)
    return values if isinstance(values, dict) else None


def text(value: Any) -> str:
    """A value as ``settings set`` reads it (lists comma separated, booleans true/false)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return ",".join(str(v) for v in value)
    return str(value)


def plan(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[list[str]]:
    """The commands that take the stored ``old`` to ``new``: ``settings unset`` for keys in ``old`` but not in ``new``,
    then ``settings set`` for new or changed keys. :func:`write` runs exactly these; Settings shows them as the
    terminal command of the pending changes."""
    out = [["settings", "unset", key] for key in sorted(set(old) - set(new))]
    out += [["settings", "set", key, text(value)] for key, value in sorted(new.items())
            if not (key in old and old[key] == value)]
    return out


def write(cli: Caller, old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """Run :func:`plan`'s commands, one CLI process per changed key; returns the refusals (``key: reason``)."""
    refused: list[str] = []
    for argv in plan(old, new):
        code, _out, err = _run(cli, argv)
        if code != 0:
            refused.append(f"{argv[2]}: {last_line(err)}")
    return refused
