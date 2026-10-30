"""Census functions of the DRIFT quirks (docs/architecture D.6.4, D.6.19; D-270..D-279; phase 10l).

The DRIFT rows are mapped by :mod:`agentprov.adapters.agentdojo.drift_mapper` itself, so these hooks carry no mapping
callback: they register the DRIFT quirk ids with the rules a profile must cite for them, and the per-file ``census``
functions that recompute each declared ``observed`` count from the sealed AER (:mod:`agentprov.adapters.agentdojo.census`).
The generic build never meets a DRIFT log (the dialect's mapper hands both DRIFT variants to the DRIFT build), so a
profile that declares these quirks for its ``drift.k18.*`` files is unaffected elsewhere.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from agentprov.adapters.agentdojo.quirks import CensusFile, QuirkHook
from agentprov.adapters.code_verification import reading_of

__all__ = ["HOOKS"]

R_ISOLATION: Final = "drift.tool_output_post_isolation@1"
R_RESERIALISED: Final = "drift.assistant_reserialised@1"
R_CALL_ERROR: Final = "drift.call_error_user_is_validator@1"
R_TEXT_CALLS: Final = "drift.calls_in_text_not_executed@1"
R_NO_SYSTEM: Final = "drift.no_system_message@1"
R_NO_INJECTIONS: Final = "drift.no_injection_map@1"
R_PLAN: Final = "drift.plan_fields_semantics@1"


def _cites(record: Mapping[str, Any], rule: str) -> bool:
    """``rule`` or its ``_unverified`` twin (D.5.4) is cited."""
    return any(reading_of(str(ref)) == rule for ref in record.get("rule", ()))


def _drift(record: Mapping[str, Any]) -> Mapping[str, Any]:
    ext = record.get("ext")
    value = ext.get("drift") if isinstance(ext, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def _isolations(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision") if r.get("subtype") == "drift.isolation_pass" and _cites(r, R_ISOLATION))


def _form(form: str) -> Any:
    return lambda cf: sum(1 for r in cf.of_kind("message") if r.get("role") == "assistant" and _drift(r).get("text_form") == form)


def _call_errors(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision") if r.get("verdict") == "deny" and _cites(r, R_CALL_ERROR))


def _check(check: str) -> Any:
    return lambda cf: sum(1 for r in cf.of_kind("decision")
                          if r.get("verdict") == "deny" and _cites(r, R_CALL_ERROR) and _drift(r).get("check") == check)


def _text_calls(detail: str | None = None) -> Any:
    return lambda cf: sum(1 for i in cf.issues if i.get("code") == "drift.calls_in_text_not_executed"
                          and (detail is None or i.get("detail") == detail))


def _plan(value: str) -> Any:
    return lambda cf: int(_drift(cf.header).get("plan_semantics") == value)


HOOKS: Final[tuple[QuirkHook, ...]] = (
    QuirkHook(
        quirk_id="agentdojo.drift_tool_output_post_isolation",
        rules=(R_ISOLATION,),
        census={"isolation_decisions": _isolations,
                "tool_messages": lambda cf: sum(1 for r in cf.of_kind("message") if r.get("role") == "tool")},
    ),
    QuirkHook(
        quirk_id="agentdojo.drift_assistant_reserialised",
        rules=(R_RESERIALISED,),
        census={"reserialised": _form("reserialised"), "raw": _form("raw")},
    ),
    QuirkHook(
        quirk_id="agentdojo.drift_call_error_as_user",
        rules=(R_CALL_ERROR,),
        census={"messages": _call_errors, "files": lambda cf: int(_call_errors(cf) > 0),
                "trajectory": _check("trajectory"), "checklist": _check("checklist")},
    ),
    QuirkHook(
        quirk_id="agentdojo.drift_calls_in_text_not_executed",
        rules=(R_TEXT_CALLS,),
        census={"final_turns": _text_calls(), "reserialised": _text_calls("reserialised"), "raw": _text_calls("raw")},
    ),
    QuirkHook(
        quirk_id="agentdojo.drift_no_system_no_injections",
        rules=(R_NO_SYSTEM, R_NO_INJECTIONS),
        census={"system_messages": lambda cf: sum(1 for r in cf.of_kind("message") if r.get("role") == "system"),
                "fixtures": lambda cf: len(cf.of_kind("fixture"))},
    ),
    QuirkHook(
        quirk_id="agentdojo.drift_plan_fields_by_commit",
        rules=(R_PLAN,),
        census={"initial_plan": _plan("initial_plan"), "final_plan_state": _plan("final_plan_state"),
                "contradicted": lambda cf: int(cf.has_issue("drift.plan_semantics_contradicted"))},
    ),
)
