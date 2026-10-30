"""Quirk hook ``agentdojo.mandate_decline`` (docs/architecture D.4.4 ``mandate-agentdojo-eval``, D.6.4, D.6.6, D.6.15).

Mandate (jwilliamsc/mandate-agentdojo-eval) replaces AgentDojo's tool executor with ``MandateToolsExecutor``, which gates the
consequential tools of the banking suite. A declined call is logged as a ``tool`` message whose ``content`` and ``error`` are
the same string beginning ``MANDATE_DECLINE:``, and the tool is **not run**. The two mapper hooks of this module:

``tool_message``
    a tool message with that shape (``mandate.decline_prefix@1``, class D) is a defence decision: no ``tool_execution``, a
    ``decision`` (verdict ``deny``) by the file's ``mandate_<mode>`` defence actor whose subject is the declined ``tool_call``
    part, ``reason`` = the logged error verbatim, and the tool message ``generated_by`` it (the baseline converter rendered
    such a call as an executed sink; verify/mandate-agentdojo-eval.md §3.7).
``tool_execution``
    a call of a tool the mode gates that **was executed** passed the gate: the allow decision is not logged, so
    ``ext.mandate.gate = "allow"`` is inferred (``mandate.allow_inferred@1``, class I) on its ``tool_execution``.

Both records name the harness (``agentdojo_mandate_eval.py``, a supporting context artefact of the import) as
``ext.mandate.harness`` when the import supplies it: the code of the gate is stored in the corpus and linked from the AER.

The gated sets are the quirk's ``params.gated`` (``MONEY_TOOLS`` for ``envelope``; ``MONEY_TOOLS`` plus ``ADMIN_TOOLS`` for
``scoped`` and ``intent``; agentdojo_mandate_eval.py l. 53-55 and 191). The mode is the suffix of the defence actor
(``mandate_<mode>``), which the profile identity read from the logged ``pipeline_name``. A pipeline without the suffix (the
undefended baseline of the same model) has no ``mandate_*`` defence and the hook does not apply.

The census counts ``declines`` (decisions citing ``mandate.decline_prefix@1``) and ``allowed_inferred`` (executions citing
``mandate.allow_inferred@1``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from agentprov.adapters.agentdojo.quirks import CensusFile, HookView, QuirkHook, ToolDecision, ToolMessage
from agentprov.adapters.code_verification import reading_of

QUIRK_ID: Final = "agentdojo.mandate_decline"
DECLINE_RULE: Final = "mandate.decline_prefix@1"
ALLOW_RULE: Final = "mandate.allow_inferred@1"
DEFAULT_PREFIX: Final = "MANDATE_DECLINE:"
DEFENCE_PREFIX: Final = "mandate_"
#: The context artefact (``[import] context_artefacts``, role supporting) holding the gate's code: the decisions and the
#: inferred allows cite it as ``ext.mandate.harness`` (its artefact id in the AER header) when the import supplies it.
HARNESS: Final = "agentdojo_mandate_eval.py"
NAMESPACES: Final = {"mandate": "https://w3id.org/agentprov/ns/mandate#"}


def _defence(view: HookView) -> str | None:
    """The file's ``mandate_<mode>`` defence (``None`` for a pipeline without the suffix)."""
    return next((name for name in sorted(view.defence_ids) if name.startswith(DEFENCE_PREFIX)), None)


def _gated(view: HookView, defence: str) -> frozenset[str]:
    """The tools the mode of ``defence`` gates (``params.gated[<mode>]``; empty for a mode the profile does not list)."""
    gated = view.params.get("gated", {})
    names = gated.get(defence.removeprefix(DEFENCE_PREFIX), ()) if isinstance(gated, Mapping) else ()
    return frozenset(str(n) for n in names)


def _harness(view: HookView) -> dict[str, str]:
    """``{"harness": <artefact id>}`` when the import supplied the harness as a context artefact, else nothing (a census run
    or a single-file import has no context)."""
    if view.cite_context is not None and HARNESS in view.context:
        return {"harness": view.cite_context(HARNESS)}
    return {}


def _decline(view: HookView, message: ToolMessage) -> ToolDecision | None:
    defence = _defence(view)
    error = message.error
    if defence is None or not isinstance(error, str) or not error.startswith(str(view.params.get("prefix", DEFAULT_PREFIX))):
        return None
    if view.params.get("content_equals_error", True) and message.text != error:
        return None  # not the executor's shape: left to the generic rows, never read as a decline
    ext = _harness(view)
    return ToolDecision(defence=defence, rules=(DECLINE_RULE,), ev="D", reason="error", ext={"mandate": ext} if ext else {})


def _allow(view: HookView, message: ToolMessage, record: dict[str, Any]) -> None:
    defence = _defence(view)
    if defence is None:
        return
    echo = message.message.get("tool_call")
    function = echo.get("function") if isinstance(echo, Mapping) else None
    if function not in _gated(view, defence):
        return
    record.setdefault("ext", {})["mandate"] = {"gate": "allow", **_harness(view)}
    record["evf"]["/ext/mandate/gate"] = "I"
    record["rule"].append(view.rule(ALLOW_RULE, "/ext/mandate/gate"))


def _declines(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision") if any(reading_of(str(ref)) == DECLINE_RULE for ref in r.get("rule", ())))


def _allowed(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("tool_execution") if any(reading_of(str(ref)) == ALLOW_RULE for ref in r.get("rule", ())))


HOOKS: Final = (
    QuirkHook(
        quirk_id=QUIRK_ID,
        rules=(DECLINE_RULE, ALLOW_RULE),
        namespaces=NAMESPACES,
        tool_message=_decline,
        tool_execution=_allow,
        census={"declines": _declines, "allowed_inferred": _allowed},
    ),
)
