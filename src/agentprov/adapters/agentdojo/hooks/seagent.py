"""Quirk hook ``agentdojo.seagent_guard_block`` (pre-check PC-seagent-agentdojo-02; D-591).

In the seagent and seagent-RF arms of the SEAgent artefact (Zenodo 23218779), the guard blocks a tool call before
dispatch: it renames the call to ``<tool>BLOCKED_BY_SEAGENT``, answers it with an empty tool message, drops the batch's
other calls and adds a user-role warning. Without this hook the renamed call is an executed tool with status ok and an
empty result (960 calls). With it, a tool message answering a call whose logged name ends with that suffix is a ``deny``
decision by the file's SEAgent defence (``agentdojo.seagent_guard_block@1``, class I): no ``tool_execution``, the
decision's subject the renamed ``tool_call`` part (its name kept verbatim), the reason not recorded, the tool message
``generated_by`` the decision. The batch's other calls, which the guard dropped, are ``unexecuted_tool_call`` (warning) citing
the same rule wherever they stand in the batch, never a lost result (``unexecuted_calls``; D-592, after regeneration-batch
item 89, which makes every unlinked call of an id-linked batch pending).

``params.defences`` names the defence actors of the guard (``seagent-initial``, ``seagent-refined``); exactly one must be
the file's, else nothing is decided. ``params.suffix`` is the rename suffix. The census counts ``blocks`` (decisions
citing the rule) and ``dropped_calls`` (call ids of the ``unexecuted_tool_call`` issues citing it).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from agentprov.adapters.agentdojo.quirks import (
    BatchIntervention,
    CallBatch,
    CensusFile,
    HookView,
    QuirkHook,
    ToolDecision,
    ToolMessage,
)
from agentprov.adapters.code_verification import reading_of
from agentprov.errors import ProfileError

QUIRK_ID: Final = "agentdojo.seagent_guard_block"
RULE: Final = "agentdojo.seagent_guard_block@1"


def _params(params: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """``(suffix, defences)`` (``ProfileError`` for malformed params: a packaging defect, never input data)."""
    suffix, names = params.get("suffix"), params.get("defences")
    if not isinstance(suffix, str) or not suffix or not isinstance(names, list | tuple) or not names \
            or not all(isinstance(n, str) and n for n in names):
        raise ProfileError(f"{QUIRK_ID}: params need a non-empty suffix and a non-empty defences list")
    return suffix, tuple(names)


def _block(view: HookView, message: ToolMessage) -> ToolDecision | None:
    suffix, names = _params(view.params)
    found = [name for name in sorted(view.defence_ids) if name in names]
    name = message.call.get("function") if message.call is not None else None
    if len(found) != 1 or not isinstance(name, str) or not name.endswith(suffix) or len(name) == len(suffix):
        return None
    return ToolDecision(defence=found[0], rules=(RULE,), ev="I")


def _dropped(view: HookView, batch: CallBatch) -> BatchIntervention | None:
    suffix, names = _params(view.params)
    if len([n for n in view.defence_ids if n in names]) != 1:
        return None
    blocked = any(isinstance(c.get("function"), str) and c["function"].endswith(suffix) and c["function"] != suffix
                  for c in batch.calls)
    return BatchIntervention((RULE,)) if blocked else None


def _dropped_calls(cf: CensusFile) -> int:
    return sum(len(i.get("ids", ())) for i in cf.issues
               if i.get("code") == "unexecuted_tool_call" and reading_of(str(i.get("rule", ""))) == RULE)


def _blocks(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision")
               if r.get("verdict") == "deny" and any(reading_of(str(ref)) == RULE for ref in r.get("rule", ())))


HOOKS: Final = (
    QuirkHook(
        quirk_id=QUIRK_ID,
        rules=(RULE,),
        tool_message=_block,
        unexecuted_calls=_dropped,
        census={"blocks": _blocks, "dropped_calls": _dropped_calls},
    ),
)
