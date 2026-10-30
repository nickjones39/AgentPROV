"""Call-to-result pairing of DTap step logs (docs/architecture D.16.7; D-28 c; layer L4).

There are no call ids: ``step_id`` is the only id on a step, so pairing is by position. A **batch** is a maximal run of
the step array in which calls are outstanding; ``send_message_to_user`` steps are ignored when batches are formed.
Meta-steps (``List MCP Tools``) are paired like any call (the mapper then maps the pair as a harness activity). Each
harness has one rule, and every rule is class I (no harness code is verified, D-24):

=============  ==================================  ===============================================================
Harness        Rule                                Batch shape / name check
=============  ==================================  ===============================================================
``openaisdk``  ``dtap.pair_strict_alternation@1``  one call per batch; the result ``tool_name`` equals the call's
``openclaw``   ``dtap.pair_strict_alternation@1``  as above (the ``error`` steps are not calls)
``googleadk``  ``dtap.pair_contiguous_batch_fifo@1`` ``A^k T^k``; result *i* answers call *i*; the result names reproduce
                                                   the call order
``claudesdk``  ``dtap.pair_interleaved_fifo@1``    each tool step answers the oldest outstanding call; names ignored
=============  ==================================  ===============================================================

A batch whose shape or names contradict its harness rule links nothing (**conflict**; the mapper raises
``call_result_link_conflict``). A multi-call batch that is not in conflict is linked and disclosed (``dtap.
pairing_ambiguous_batch`` with detail ``contiguous``, ``interleaved`` or ``repeated_names``). A call that no later tool
step answers is *unanswered*; a tool step with no outstanding call is an *orphan*.

Pure: a function of the step list and the harness name. Standard library only.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "META_TOOL",
    "RULES",
    "Batch",
    "Pairing",
    "pair",
    "step_kind",
]

#: The meta-step tool name of the SDK harnesses (D.16.3).
META_TOOL: Final = "List MCP Tools"
MESSAGE_ACTION: Final = "send_message_to_user"
#: Pairing rule per harness (D.16.7; the profile's ``[family.dtap] pairing`` table names the same rules).
RULES: Final[Mapping[str, str]] = {
    "openaisdk": "dtap.pair_strict_alternation@1",
    "openclaw": "dtap.pair_strict_alternation@1",
    "googleadk": "dtap.pair_contiguous_batch_fifo@1",
    "claudesdk": "dtap.pair_interleaved_fifo@1",
}


def step_kind(step: Mapping[str, Any]) -> str:
    """``user``, ``tool``, ``call``, ``meta`` (a ``List MCP Tools`` agent step without parameters), ``message``
    (``send_message_to_user``), ``error`` (an agent step ``action: "error"`` with ``metadata.error``) or ``unknown``."""
    role = step.get("role")
    metadata = step.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    if role == "user":
        return "user"
    if role == "tool":
        return "tool"
    if role != "agent":
        return "unknown"
    action = step.get("action")
    if action == MESSAGE_ACTION and "tool_name" not in meta:
        return "message"
    if action == "error" and "error" in meta and "tool_name" not in meta:
        return "error"
    if isinstance(meta.get("tool_name"), str):
        if meta["tool_name"] == META_TOOL and "tool_params" not in meta:
            return "meta"
        return "call"
    return "unknown"


@dataclass
class Batch:
    """One batch: its call and result step indices and the order in which they occurred (``A``/``T`` events)."""

    index: int
    calls: list[int] = field(default_factory=list)
    results: list[int] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    conflict: str | None = None  # why the harness rule does not hold for this batch
    detail: str | None = None  # contiguous | interleaved | repeated_names (multi-call batches)

    @property
    def multi(self) -> bool:
        return len(self.calls) > 1

    @property
    def contiguous(self) -> bool:
        k = len(self.calls)
        return self.events == ["A"] * k + ["T"] * len(self.results)


@dataclass
class Pairing:
    """The pairing of one step log."""

    rule: str | None
    links: dict[int, int] = field(default_factory=dict)  # tool step index -> call step index (non-conflict batches)
    batches: list[Batch] = field(default_factory=list)
    batch_of: dict[int, int] = field(default_factory=dict)  # call or tool step index -> batch index
    unanswered: list[int] = field(default_factory=list)  # call step indices never answered
    orphans: list[int] = field(default_factory=list)  # tool step indices without an outstanding call
    conflicted: dict[int, int] = field(default_factory=dict)  # tool step -> the call FIFO would give (conflict batches)


def _name(step: Mapping[str, Any]) -> object:
    metadata = step.get("metadata")
    return metadata.get("tool_name") if isinstance(metadata, dict) else None


def pair(steps: Sequence[Mapping[str, Any]], harness: str) -> Pairing:
    """Pair the calls and results of ``steps`` under the rule of ``harness`` (module docstring)."""
    out = Pairing(RULES.get(harness))
    queue: deque[int] = deque()
    current: Batch | None = None
    fifo: dict[int, int] = {}
    for i, step in enumerate(steps):
        kind = step_kind(step)
        if kind in ("call", "meta"):
            if current is None:
                current = Batch(len(out.batches))
                out.batches.append(current)
            current.calls.append(i)
            current.events.append("A")
            out.batch_of[i] = current.index
            queue.append(i)
        elif kind == "tool":
            if not queue or current is None:
                out.orphans.append(i)
                continue
            call = queue.popleft()
            fifo[i] = call
            current.results.append(i)
            current.events.append("T")
            out.batch_of[i] = current.index
            if not queue:
                current = None
    out.unanswered = list(queue)
    for batch in out.batches:
        _judge_batch(batch, steps, fifo, harness)
        for result in batch.results:
            if batch.conflict is None:
                out.links[result] = fifo[result]
            else:
                out.conflicted[result] = fifo[result]
    return out


def _judge_batch(batch: Batch, steps: Sequence[Mapping[str, Any]], fifo: Mapping[int, int], harness: str) -> None:
    names = [_name(steps[c]) for c in batch.calls]
    pairs = [(fifo[r], r) for r in batch.results]
    if harness in ("openaisdk", "openclaw"):
        if batch.multi:
            batch.conflict = "shape"
        elif any(_name(steps[c]) != _name(steps[r]) for c, r in pairs):
            batch.conflict = "name"
    elif harness == "googleadk":
        if batch.multi and not batch.contiguous:
            batch.conflict = "shape"
        elif any(_name(steps[c]) != _name(steps[r]) for c, r in pairs):
            batch.conflict = "name"
    elif harness != "claudesdk":
        batch.conflict = "harness"
    if batch.multi and batch.conflict is None:
        if harness == "googleadk" and len(set(map(str, names))) != len(names):
            batch.detail = "repeated_names"
        else:
            batch.detail = "contiguous" if batch.contiguous else "interleaved"
