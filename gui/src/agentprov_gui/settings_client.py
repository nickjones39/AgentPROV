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

__all__ = ["Caller", "read", "text", "write"]

#: how an ``agentprov`` command is run: a CLI locator, or a callable such as :meth:`JobManager.call` (its home)
Caller = CliLocator | Callable[[Sequence[str]], tuple[int, bytes, bytes]]


def _run(cli: Caller, argv: list[str]) -> tuple[int, bytes, bytes]:
    return call(cli, argv) if isinstance(cli, CliLocator) else cli(argv)


def read(cli: Caller, prefix: str) -> dict[str, Any] | None:
    """The stored values under ``prefix`` (already checked by the schema), or ``None`` when they cannot be read."""
    code, out, _err = _run(cli, ["settings", "list", "--prefix", prefix, "--format", "json"])
    if code != 0:
        return None
    try:
        values = json.loads(out).get("values")
    except (ValueError, AttributeError):
        return None
    return values if isinstance(values, dict) else None


def text(value: Any) -> str:
    """A value as ``settings set`` reads it (lists comma separated, booleans true/false)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | tuple):
        return ",".join(str(v) for v in value)
    return str(value)


def write(cli: Caller, old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """``settings unset`` for keys in ``old`` but not in ``new`` and ``settings set`` for new or changed keys;
    returns the refusals (``key: reason``)."""
    refused: list[str] = []
    for key in sorted(set(old) - set(new)):
        code, _out, err = _run(cli, ["settings", "unset", key])
        if code != 0:
            refused.append(f"{key}: {last_line(err)}")
    for key, value in sorted(new.items()):
        if key in old and old[key] == value:
            continue
        code, _out, err = _run(cli, ["settings", "set", key, text(value)])
        if code != 0:
            refused.append(f"{key}: {last_line(err)}")
    return refused
