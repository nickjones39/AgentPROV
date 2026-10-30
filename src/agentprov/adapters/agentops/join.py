"""Task-definition join of an AgentOps-Bench run (docs/architecture D.18.5; DECISIONS D-194; layer L4).

**Rule** (``agentops.task_join@1``, D): a run's task is the ``tasks`` pin member that ``tables/task_files.toml`` lists
for the run's in-record ``task_id``; the join holds when the member's bytes have the table's digest and size and the
document's ``id`` equals the ``task_id`` (a comparison of observed strings). The label's domain and number name the
same task (checked separately by ``agentops.label_facets@1``).

**Allowlist.** A task document is parsed with :func:`agentprov.ingest.yamlsafe.safe_load` and immediately reduced to
:data:`ALLOWED`; any other member is dropped before other code sees it. YAML 1.1 implicit types (dates) would become
their ISO text; none occurs in the 100 pinned files.

**Prompt** (``agentops.prompt_composition_unverified@1``, I): the adapters send ``description`` followed by
``"\\n\\nContext:\\n" + context`` when ``context`` is set (snapshot ``9153772``, the agent adapters' ``run``); the
composition is the harness's, so a composed prompt is class I. A prompt without context is the ``description`` verbatim.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

__all__ = ["ALLOWED", "CONTEXT_SEPARATOR", "TaskJoin", "allowlisted", "prompt_of"]

ALLOWED: Final = ("id", "domain", "description", "context", "tools_available", "expected_output", "optimal_steps",
                  "difficulty", "tags")
CONTEXT_SEPARATOR: Final = "\n\nContext:\n"


@dataclass(frozen=True, slots=True)
class TaskJoin:
    """The outcome of the join for one run (``ext.agentops.join``)."""

    task_id: object
    label: str | None
    status: str  # joined | not_listed | missing | digest_mismatch | unparseable | id_differs
    task: Mapping[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status}
        if self.label is not None:
            out["label"] = self.label
        return out


def _text(value: object) -> object:
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()
    if isinstance(value, list):
        return [_text(v) for v in value]
    return value


def allowlisted(document: object) -> dict[str, Any] | None:
    """The allowlisted members of a task document, or ``None`` when it is not a mapping."""
    if not isinstance(document, Mapping):
        return None
    return {k: _text(document[k]) for k in ALLOWED if k in document}


def prompt_of(task: Mapping[str, Any]) -> tuple[object, bool]:
    """``(prompt, composed)``: the description, plus the context section when the task has one."""
    description = task.get("description")
    context = task.get("context")
    if isinstance(description, str) and isinstance(context, str) and context:
        return description + CONTEXT_SEPARATOR + context, True
    return description, False
