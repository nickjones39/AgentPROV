"""Quirk hook ``agentdojo.defence_denial_message`` (docs/architecture D.6.6 denial rows; phase-10d routing R1; D-113).

Several defences log their refusal of a tool call as a ``tool`` message whose ``error`` is the defence's own text, and do
not run the call (interbolt, glitch, UBAG, Progent, gate, the munim money gate, aiAuthZ). Without this hook the generic
D.6.6 rows map such a message as an executed call with status ``error``. The profile's quirk states, per defence, the text
of its denials; a tool message that matches becomes a defence decision (``agentdojo.defence_denial_message@1``, class I):
no ``tool_execution``, a ``decision`` (verdict ``deny``) by that defence actor whose subject is the refused ``tool_call``
part, ``reason`` = the logged error verbatim, and the message ``generated_by`` it. Other errors of the same defence stay
generic tool errors.

``params.denials`` is a list of matchers, tried in order; each is a table with

``defences``
    globs over the file's defence actor names (``fnmatchcase``); the matcher applies when exactly one actor of the file
    matches (none: the file is not defended by it; several: ambiguous, left to the generic rows);
``error_equals`` / ``error_prefix`` / ``error_regex``
    the denial text: one of the exact texts, a prefix, or a regular expression the whole error matches (``re.fullmatch``,
    ``re.DOTALL``); at least one is given;
``content_equals_error``
    optional, default false: the message's output text must equal the error too (the defence's own shape).

A hold (a call kept for review and not run) is a denial too: the verdict vocabulary has no hold, and the call was not
executed; the profile says which texts are holds. The census counts ``denials`` (decisions citing the rule).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from agentprov.adapters.agentdojo.quirks import CensusFile, HookView, QuirkHook, ToolDecision, ToolMessage
from agentprov.adapters.code_verification import reading_of
from agentprov.errors import ProfileError

QUIRK_ID: Final = "agentdojo.defence_denial_message"
RULE: Final = "agentdojo.defence_denial_message@1"
_KEYS: Final = frozenset({"defences", "error_equals", "error_prefix", "error_regex", "content_equals_error"})


@dataclass(frozen=True, slots=True)
class Matcher:
    """One entry of ``params.denials``."""

    defences: tuple[str, ...]
    equals: frozenset[str]
    prefixes: tuple[str, ...]
    regex: re.Pattern[str] | None
    content_equals_error: bool

    def text_matches(self, error: str) -> bool:
        return (error in self.equals or any(error.startswith(p) for p in self.prefixes)
                or (self.regex is not None and self.regex.fullmatch(error) is not None))

    def defence(self, names: list[str]) -> str | None:
        """The one defence actor of the file this matcher names (``None`` for none or several)."""
        found = [n for n in names if any(fnmatch.fnmatchcase(n, g) for g in self.defences)]
        return found[0] if len(found) == 1 else None


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(v, str) and v for v in value):
        raise ProfileError(f"{QUIRK_ID}: {where} must be a list of non-empty strings")
    return tuple(value)


def _matcher(entry: Any, i: int) -> Matcher:
    where = f"params.denials[{i}]"
    if not isinstance(entry, Mapping) or set(entry) - _KEYS:
        raise ProfileError(f"{QUIRK_ID}: {where} must be a table of {sorted(_KEYS)}")
    defences = _strings(entry.get("defences"), f"{where}.defences")
    equals = _strings(entry.get("error_equals", []), f"{where}.error_equals")
    prefixes = _strings(entry.get("error_prefix", []), f"{where}.error_prefix")
    pattern = entry.get("error_regex")
    if pattern is not None and (not isinstance(pattern, str) or not pattern):
        raise ProfileError(f"{QUIRK_ID}: {where}.error_regex must be a non-empty string")
    if not equals and not prefixes and pattern is None:
        raise ProfileError(f"{QUIRK_ID}: {where} states no denial text")
    content_eq = entry.get("content_equals_error", False)
    if not isinstance(content_eq, bool):
        raise ProfileError(f"{QUIRK_ID}: {where}.content_equals_error must be a boolean")
    try:
        regex = re.compile(pattern, re.DOTALL) if pattern is not None else None
    except re.error as exc:
        raise ProfileError(f"{QUIRK_ID}: {where}.error_regex: {exc}") from None
    return Matcher(defences, frozenset(equals), prefixes, regex, content_eq)


def matchers(params: Mapping[str, Any]) -> tuple[Matcher, ...]:
    """The quirk's matchers (``ProfileError`` for malformed params: a packaging defect, never input data). Parsed per
    call; ``re`` caches the compiled patterns."""
    denials = params.get("denials")
    if not isinstance(denials, list | tuple) or not denials:
        raise ProfileError(f"{QUIRK_ID}: params.denials must be a non-empty list of tables")
    return tuple(_matcher(entry, i) for i, entry in enumerate(denials))


def _denial(view: HookView, message: ToolMessage) -> ToolDecision | None:
    error = message.error
    if not isinstance(error, str):
        return None
    names = sorted(view.defence_ids)
    for m in matchers(view.params):
        if not m.text_matches(error) or (m.content_equals_error and message.text != error):
            continue
        defence = m.defence(names)
        if defence is not None:
            return ToolDecision(defence=defence, rules=(RULE,), ev="I", reason="error")
    return None


def _denials(cf: CensusFile) -> int:
    return sum(1 for r in cf.of_kind("decision") if any(reading_of(str(ref)) == RULE for ref in r.get("rule", ())))


HOOKS: Final = (
    QuirkHook(
        quirk_id=QUIRK_ID,
        rules=(RULE,),
        tool_message=_denial,
        census={"denials": _denials},
    ),
)
