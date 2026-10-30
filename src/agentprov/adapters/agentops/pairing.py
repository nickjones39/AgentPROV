"""Call-to-result pairing of AgentOps-Bench steps (docs/architecture D.18.4; DECISIONS D-193; layer L4).

A step holds two parallel arrays, ``tool_calls`` and ``tool_results``, and no call ids (the provider's ``tool_use_id`` and
``tool_call_id`` are used in the harness's conversation but never written). The harness's agent adapters run the calls of
one response in order and append call *i* and then its result (snapshot ``9153772``; the producing code is not
recorded, so the rule ``agentops.pair_by_index_unverified@1`` is class I). Position alone is not the evidence: a link is
made only where both arrays have the same length and the result at index *i* names the tool the call at index *i*
named. Otherwise the whole step links nothing (**conflict**; the mapper raises ``call_result_link_conflict``). A step
whose calls repeat a tool name is linked and disclosed (``repeated_names``), because only the index tells the pairs
apart there.

Pure: a function of one step's two arrays. Standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

__all__ = ["RULE", "StepPairing", "pair_step"]

RULE: Final = "agentops.pair_by_index_unverified@1"


@dataclass(frozen=True, slots=True)
class StepPairing:
    """The pairing of one step: ``links[i]`` is the result index answering call ``i`` (identity, or nothing)."""

    links: Mapping[int, int]
    conflict: str | None  # None | "length" | "names"
    repeated_names: bool

    @property
    def linked(self) -> bool:
        return self.conflict is None


def pair_step(calls: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]]) -> StepPairing:
    """Pair the calls and results of one step by index, guarded by length and tool-name equality."""
    names = [c.get("tool_name") for c in calls]
    repeated = len(set(map(str, names))) < len(names)
    if len(calls) != len(results):
        return StepPairing({}, "length", repeated)
    if any(c.get("tool_name") != r.get("tool_name") for c, r in zip(calls, results, strict=True)):
        return StepPairing({}, "names", repeated)
    return StepPairing({i: i for i in range(len(calls))}, None, repeated)
