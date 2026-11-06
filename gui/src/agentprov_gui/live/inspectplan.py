"""An Inspect backend's run options in Run Live (D-663, D-667, D-740, D-1120). No Qt.

An ``inspect-<benchmark>`` backend (the CLI's rule in ``cli/run.py``: the backend id starts with ``inspect-``) takes an
Inspect plan instead of AgentDojo's cells: ``--task``, ``--task-param KEY=VALUE`` for each declared parameter that
differs from its default, ``--samples limit:N`` or ``--samples ID,ID…``, the three per-sample limits (mandatory,
D-667), ``--epochs``, ``--max-connections``, ``--cell-size`` and one ``--judge ROLE=MODEL`` per judge role of the task's
scorer (every role is required). :class:`InspectChoice` holds what the form chose; :meth:`InspectChoice.extra` gives
the run fields (``RunSettings.extra``) that the one argv builder (:func:`jobs.commands.build_spec`) turns into those
options, for the command card, the estimate and Start alike.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov_gui.live.plan import InspectParam, InspectTask

__all__ = ["DEV_SAMPLES", "INSPECT_DEV_SCRIPT", "LIMIT_BOUNDS", "SCRIPTED_MODEL", "InspectChoice", "is_inspect",
           "missing", "param_arg"]

#: the CLI's scripted agent's model (``cli/run.py`` ``_scripted_agent``: ``args.model_id or "scripted-fake"``); a
#: scripted run's judges are given the same label (their replies come from the script's ``judges`` steps)
SCRIPTED_MODEL: Final = "scripted-fake"
#: a scripted Inspect run needs a combined script (``{"agent": [...], "judges": {ROLE: [...]}}``): the worker refuses
#: scripted judges from a plain one (``agentprov_backend_inspect.models.scripted_steps``)
INSPECT_DEV_SCRIPT: Final = Path(__file__).resolve().parent.parent / "data" / "scripted-dev-inspect.json"
#: the shipped Inspect dev script answers this many samples per cell (samples × epochs); each judge role has four times
#: as many steps
DEV_SAMPLES: Final = 100
#: the worker's ranges (``agentprov_backend_inspect.plan``): epochs, the three limits, max connections, cell size
LIMIT_BOUNDS: Final = {"epochs": (1, 10), "message_limit": (1, 500), "token_limit": (1, 10_000_000),
                       "time_limit": (1, 86_400), "max_connections": (1, 64), "cell_size": (1, 500)}
#: what the worker's sample ids look like (``plan._ID``)
_SAMPLE_ID: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:\-]{0,127}")


def is_inspect(backend: str) -> bool:
    """An Inspect backend, by the CLI's own rule (``backend.startswith("inspect-")``)."""
    return backend.startswith("inspect-")


def param_arg(name: str, value: str | int | bool) -> str:
    """``NAME=VALUE`` as ``--task-param`` reads it: the CLI parses VALUE as a TOML scalar and falls back to the bare
    text, so a string that would parse as something else (``true``, ``12``, a date) is written quoted."""
    if isinstance(value, bool):
        return f"{name}={'true' if value else 'false'}"
    if isinstance(value, int):
        return f"{name}={value}"
    try:
        tomllib.loads(f"v = {value}")
    except tomllib.TOMLDecodeError:
        return f"{name}={value}"  # read back as this very string
    return f"{name}={_basic_string(value)}"


def _basic_string(text: str) -> str:
    """``text`` as a TOML basic string that reads back as ``text``: a typed value (a free-text parameter) may hold
    quotes and backslashes; control characters and DEL are written as ``\\uXXXX``."""
    out = ['"']
    for char in text:
        if char in '"\\':
            out.append("\\" + char)
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


@dataclass(frozen=True, slots=True)
class InspectChoice:
    """What the Inspect rows chose. ``params``: only values the user changed (a parameter at its catalogue default is
    left out, as every option at its default is). ``limit`` or ``ids`` selects the samples; ``judges`` maps every role
    to its model (empty: the agent's model)."""

    task: str = ""
    params: dict[str, str | int | bool] = field(default_factory=dict)
    limit: int | None = None
    ids: tuple[str, ...] = ()
    message_limit: int | None = None
    token_limit: int | None = None
    time_limit: int | None = None
    epochs: int | None = None
    max_connections: int | None = None
    cell_size: int | None = None
    judges: dict[str, str] = field(default_factory=dict)

    def samples(self) -> str:
        if self.ids:
            return ",".join(self.ids)
        return f"limit:{self.limit}" if self.limit else ""

    def extra(self, *, agent_model: str) -> dict[str, Any]:
        """The run fields (``RunSettings.extra``); ``agent_model``: the model each judge without its own takes."""
        out: dict[str, Any] = {"task": self.task, "samples": self.samples(),
                               "task_param": [param_arg(k, v) for k, v in sorted(self.params.items())],
                               "judge": [f"{role}={model or agent_model}" for role, model in sorted(self.judges.items())
                                         if model or agent_model]}
        for key in ("message_limit", "token_limit", "time_limit", "epochs", "max_connections", "cell_size"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return {k: v for k, v in out.items() if v not in ("", [])}


def bad_ids(text: str) -> list[str]:
    """The entries of a typed id list that are not sample ids (shown escaped by the caller)."""
    return [x for x in (p.strip() for p in text.split(",")) if x and not _SAMPLE_ID.fullmatch(x)]


def missing(choice: InspectChoice, task: InspectTask | None, *, split_samples: int | None) -> str | None:
    """Why the Inspect rows cannot plan yet (None: they can). The worker checks again; this says it first, in words."""
    if task is None:
        return "Choose an Inspect task."
    if not choice.limit and not choice.ids:
        return "Choose the samples to run: the first N of the split, or their ids."
    if choice.limit and split_samples is not None and choice.limit > split_samples:
        return f"The split has {split_samples:,} samples: choose at most that many."
    if len(set(choice.ids)) != len(choice.ids):
        return "The sample ids repeat an id."
    unset = [label for key, label in (("message_limit", "message"), ("token_limit", "token"), ("time_limit", "time"))
             if getattr(choice, key) is None]
    if unset:
        return ("An Inspect run needs all three per-sample limits (D-667): set the " + ", ".join(unset)
                + " limit" + ("s" if len(unset) > 1 else "") + ".")
    return None


def default_text(p: InspectParam) -> str:
    """A parameter's default as the form says it."""
    if p.default is None:
        return "not set"
    if isinstance(p.default, bool):
        return "true" if p.default else "false"
    return str(p.default)
