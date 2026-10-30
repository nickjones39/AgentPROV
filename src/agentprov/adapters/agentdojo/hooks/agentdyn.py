"""Quirk hooks of the AgentDyn source (docs/architecture D.4.4 ``agentdyn``, D.6.4, D.6.6, D.6.14).

AgentDyn's variant A logs are AgentDojo 0.1.35 TraceLogger output, so the generic mapper already covers most of its
quirks, driven by the profile: ``run_error_imposes_outcome`` (the quirk's first rule is the origin rule,
``agentdyn.json_decode_error_imposed@1``), ``incomplete_run``, ``provider_call_id_anomalies`` and
``pi_detector_redaction`` (its ``params.defences`` list the three detector defences). The three behaviours below have no
generic row, so each is a :class:`~agentprov.adapters.agentdojo.quirks.QuirkHook`:

``agentdojo.progent_denial``
    a tool message whose ``error`` matches ``^ValidationError: The tool '...' is not allowed..`` is a **denial**: a
    ``decision`` by the ``progent`` defence actor, no ``tool_execution`` (D.6.6 row; ``agentdyn.progent_denial_pattern@1``,
    class I). The denial reason is not logged.
``agentdojo.drift_integrated_user_error_key``
    a ``user`` message with an ``error`` key (the integrated DRIFT defence's validator feedback) is authored by the
    ``drift`` defence actor: a ``deny`` decision on the refused output, and the message ``generated_by`` it
    (``agentdyn.drift_user_error_key@1``, class D).
``agentdojo.camel_orphan_tool_results``
    a tool message that no assistant call answers, in a CaMeL pipeline, is an execution requested by the ``camel`` defence
    actor (the interpreter), not an ambiguous one (``agentdyn.camel_orphan_tool_result@1``, class I).

The hooks read only the view they are given (pure). The profile's quirk selectors decide which files they see.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from agentprov.adapters.agentdojo.quirks import (
    CensusFile,
    HookView,
    InputNotLogged,
    OrphanRequest,
    QuirkHook,
    ToolDecision,
    ToolMessage,
    UserAuthor,
    UserMessage,
)
from agentprov.adapters.code_verification import reading_of

__all__ = ["HOOKS"]

PROGENT_RULE: Final = "agentdyn.progent_denial_pattern@1"
DRIFT_RULE: Final = "agentdyn.drift_user_error_key@1"
CAMEL_RULE: Final = "agentdyn.camel_orphan_tool_result@1"
FEEDBACK_RULE: Final = "agentdyn.camel_interpreter_feedback@1"
PLANNER_RULE: Final = "agentdyn.camel_planner_input_not_logged@1"
#: ``make_error_messages`` (CaMeL ``privileged_llm.py`` l. 124-125 at 5353cf76): the feedback's first line.
_DEFAULT_FEEDBACK: Final = "Running the code gave the following error:"
_DEFAULT_PROGENT: Final = r"^ValidationError: The tool '[^']*' is not allowed\.\."


# ------------------------------------------------------------------------------------------------ progent denial
def _progent_tool_message(view: HookView, message: ToolMessage) -> ToolDecision | None:
    error = message.error
    if "progent" not in view.defence_ids or not isinstance(error, str):
        return None
    pattern = str(view.params.get("regex", _DEFAULT_PROGENT))
    if re.search(pattern, error) is None:
        return None
    return ToolDecision(defence="progent", rules=(PROGENT_RULE,), ev="I", reason=None)


def _progent_denials(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision") if r.get("verdict") == "deny" and _cites(r, PROGENT_RULE))


# ------------------------------------------------------------------------------------------------ DRIFT user error key
def _drift_user_message(view: HookView, message: UserMessage) -> ToolDecision | None:
    if "drift" not in view.defence_ids or not isinstance(message.error, str):
        return None
    return ToolDecision(defence="drift", rules=(DRIFT_RULE,), ev="D", reason="error")


def _drift_user_messages(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("message") if r.get("role") == "user" and _cites(r, DRIFT_RULE))


# ------------------------------------------------------------------------------------------------ CaMeL orphan results
def _camel_orphan(view: HookView, message: ToolMessage) -> OrphanRequest | None:
    if "camel" not in view.defence_ids:
        return None
    return OrphanRequest(requester="camel", rules=(CAMEL_RULE,), severity="info")


def _is_camel(cf: CensusFile) -> bool:
    task = cf.header.get("task")
    return isinstance(task, Mapping) and task.get("defense_id") == "camel"


def _camel_tool_messages(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("message") if r.get("role") == "tool") if _is_camel(cf) else 0


def _camel_assistant_calls(cf: CensusFile) -> int:
    if not _is_camel(cf):
        return 0
    return sum(1 for r in cf.of_kind("message") if r.get("role") == "assistant"
               for p in r.get("parts", ()) if p.get("t") == "tool_call")


def _camel_orphan_executions(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("tool_execution") if "requested_by" in r and _cites(r, CAMEL_RULE))


# ------------------------------------------------------------------------------------------------ CaMeL feedback, planner input
def _camel_feedback(view: HookView, message: UserMessage) -> UserAuthor | None:
    """Regeneration-batch item 2 (B3, D-376): the interpreter's error feedback, appended by CaMeL's element as a user
    message, is written by the camel defence, not the simulated user."""
    text = message.text
    if "camel" not in view.defence_ids or text is None:
        return None
    if not text.startswith(str(view.params.get("prefix", _DEFAULT_FEEDBACK))):
        return None
    return UserAuthor(defence="camel", rules=(FEEDBACK_RULE,))


def _camel_planner_input(view: HookView) -> InputNotLogged | None:
    """The privileged planner is sent its own list (system prompt, query, earlier code/feedback pairs; never tool
    results), which the log does not hold (D-376)."""
    return InputNotLogged(rules=(PLANNER_RULE,)) if "camel" in view.defence_ids else None


def _camel_feedback_messages(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("message") if r.get("role") == "user" and _cites(r, FEEDBACK_RULE))


def _camel_planner_calls(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("model_call") if r.get("role") == "agent" and _cites(r, PLANNER_RULE))


def _cites(record: Mapping[str, Any], rule: str) -> bool:
    """``rule`` or its ``_unverified`` twin (D.5.4) is cited."""
    return any(reading_of(str(ref)) == rule for ref in record.get("rule", ()))


HOOKS: Final[tuple[QuirkHook, ...]] = (
    QuirkHook(
        quirk_id="agentdojo.progent_denial",
        rules=(PROGENT_RULE,),
        tool_message=_progent_tool_message,
        census={"denials": _progent_denials},
    ),
    QuirkHook(
        quirk_id="agentdojo.drift_integrated_user_error_key",
        rules=(DRIFT_RULE,),
        user_message=_drift_user_message,
        census={"user_messages": _drift_user_messages},
    ),
    QuirkHook(
        quirk_id="agentdojo.camel_orphan_tool_results",
        rules=(CAMEL_RULE,),
        orphan_tool_result=_camel_orphan,
        census={
            "tool_messages": _camel_tool_messages,
            "assistant_calls": _camel_assistant_calls,
            "orphan_executions": _camel_orphan_executions,
        },
    ),
    QuirkHook(
        quirk_id="agentdojo.camel_interpreter_feedback",
        rules=(FEEDBACK_RULE, PLANNER_RULE),
        later_user_message=_camel_feedback,
        agent_input=_camel_planner_input,
        census={"feedback_messages": _camel_feedback_messages, "planner_calls": _camel_planner_calls},
    ),
)
