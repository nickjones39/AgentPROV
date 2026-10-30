"""Quirk hook ``agentdojo.detector_abort`` (docs/architecture D.6.6 abort row; phase-10d routing R10; D-116).

Some defences are output detectors that run after the tools of a turn executed, check those outputs, and on a detection
raise AgentDojo's ``AbortAgentError``: the run ends there and the agent never answers (llm-lock's
``defense_utils.EnhancedPromptInjectionDetector``). AgentDojo logs the messages up to the checked outputs with ``error``
null, so without this hook the AER shows a run that simply stopped after an executed tool. With it, a log that ends at
executed tool messages, in a file defended by a declared aborting detector and with no recorded run error (``error`` null), gains a ``decision`` by that detector with
verdict ``terminate`` (``agentdojo.detector_abort_after_output@1``, class I):

* the last turn has one output: the subject is its ``tool_execution`` (its output as produced);
* it has several: the detector checked them last-first and stopped at the first it flagged, and the log does not record
  which, so the subject is the request message whose calls they answer, with the info issue
  ``agentdojo.detector_abort_output_unrecorded`` on it.

``params.defences`` lists globs over the file's defence actor names; exactly one actor must match (none: the file is not
defended by an aborting detector; several: ambiguous, nothing is added). The census counts ``aborts`` (terminate
decisions citing the rule) and ``aborts_output_unrecorded`` (the issue).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from typing import Any, Final

from agentprov.adapters.agentdojo.quirks import CensusFile, EndDecision, HookView, LogEnd, QuirkHook
from agentprov.adapters.code_verification import reading_of
from agentprov.errors import ProfileError

QUIRK_ID: Final = "agentdojo.detector_abort"
RULE: Final = "agentdojo.detector_abort_after_output@1"
ISSUE: Final = "agentdojo.detector_abort_output_unrecorded"


def defences(params: Mapping[str, Any]) -> tuple[str, ...]:
    """The quirk's defence globs (``ProfileError`` for malformed params: a packaging defect, never input data)."""
    globs = params.get("defences")
    if not isinstance(globs, list | tuple) or not globs or not all(isinstance(g, str) and g for g in globs):
        raise ProfileError(f"{QUIRK_ID}: params.defences must be a non-empty list of non-empty strings")
    return tuple(globs)


def _abort(view: HookView, end: LogEnd) -> EndDecision | None:
    if end.role != "tool" or not end.tool_executions or len(end.tool_executions) != len(end.tool_messages):
        return None  # not ending at executed tool outputs (a trailing denial or redaction is not an abort)
    if view.doc.get("error") is not None:
        return None  # AbortAgentError leaves error null: a recorded run error is another cause (regen item 43)
    globs = defences(view.params)
    found = [name for name in sorted(view.defence_ids) if any(fnmatch.fnmatchcase(name, g) for g in globs)]
    if len(found) != 1:
        return None
    if len(end.tool_executions) == 1:
        return EndDecision(defence=found[0], subject=end.tool_executions[0], rules=(RULE,), ev="I")
    if end.request is None:
        return None
    if view.issue is not None:
        view.issue(ISSUE, [end.request], RULE, severity="info",
                   detail=f"{len(end.tool_executions)} outputs in the last turn; the flagged one is not recorded")
    return EndDecision(defence=found[0], subject=end.request, rules=(RULE,), ev="I")


def _aborts(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision")
               if r.get("verdict") == "terminate" and any(reading_of(str(ref)) == RULE for ref in r.get("rule", ())))


def _unrecorded(cf: CensusFile) -> int:
    return len(cf.issue_ids(ISSUE))


HOOKS: Final = (
    QuirkHook(
        quirk_id=QUIRK_ID,
        rules=(RULE,),
        log_end=_abort,
        census={"aborts": _aborts, "aborts_output_unrecorded": _unrecorded},
    ),
)
