"""How a selection reads an index row's ``cell`` members and ``outcome`` facet (D-706). Pure, no imports beyond the
standard library: ``agentprov stats --select`` (:mod:`agentprov.stats.source`) and the GUI's Viewer columns use the same
two functions, so a Viewer filter and its CLI selector cannot disagree (D-700).

* :func:`cell_strings`: a known cell member as strings (a string; an integer as its decimal spelling; the string
  elements of an array); an absent, null or unknown (``$unk``) member gives nothing.
* :func:`outcome_states`: ``true`` / ``false`` for each ``outcome`` element whose SEM claim is ``claim`` and whose
  ``holds`` is a boolean, or ``["none"]`` when no element has one (the claim was not judged). For ``attack_succeeded``
  the AgentDojo SEM profile gives the claim only on an attacked cell and for a checker's result, so a benign cell is
  ``none``, whatever its raw ``security`` judgement says. A correction decides: when an element with the claim comes
  from a ``recomputed`` judgement (a ROPE correction, a DTap audit; C.3.10 ``revises``), only those elements count, so a
  corrected row matches its corrected value and never both (D-29 item 5, AU-MSR-1). The facet keeps every element.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["OUTCOME_STATES", "cell_strings", "outcome_states"]

OUTCOME_STATES: Final = ("true", "false", "none")


def cell_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, int) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def outcome_states(outcome: Any, claim: str) -> list[str]:
    judged = [e for e in (outcome if isinstance(outcome, list) else [])
              if isinstance(e, Mapping) and e.get("claim") == claim and isinstance(e.get("holds"), bool)]
    corrected = [e for e in judged if e.get("origin") == "recomputed"]
    states = sorted({"true" if e["holds"] else "false" for e in corrected or judged})
    return states or ["none"]
