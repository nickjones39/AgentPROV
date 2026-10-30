"""AER: the AgentPROV Execution Record, ``aer/0.2`` (docs/architecture section C); ``aer/0.1`` stays readable.

"AER" is always expanded as "AgentPROV Execution Record" (user decision U-15); it is unrelated to the
"Agent Execution Record" of Vispute & Kadam (arXiv 2603.21692).

This package is import-light: it exports the format constants only. Import the submodules you need
(``types``, ``canon``, ``ids``, ``evidence``, ``rules``, ``writer``, ``reader``, ``locators``, ``accounting``,
``validate``).
"""

from __future__ import annotations

from typing import Final

#: The ``execution.aer`` header member the writer seals (C.2.4, C.3.1; D-210..D-212). ``aer/0.2`` relaxes two ``aer/0.1``
#: limits: a live header may omit ``instrumentation`` when it declares it ``not_captured``, and a part's ``text``,
#: ``args`` or ``value`` may be absent when declared ``withheld`` or ``not_captured``. Nothing else changes.
AER_VERSION: Final = "0.2"
AER_FORMAT_ID: Final = "aer/0.2"
#: Every ``execution.aer`` value this build reads and validates, each under its own rules (``aer/0.1`` is frozen, D-14).
READABLE_VERSIONS: Final = ("0.1", "0.2")

#: The 13 record kinds of ``aer/0.1`` and ``aer/0.2`` (Addendum B, B-1).
RECORD_KINDS: Final = frozenset(
    {
        "execution",
        "actor",
        "scope",
        "message",
        "model_call",
        "tool_execution",
        "decision",
        "state_change",
        "fixture",
        "judgement",
        "activity",
        "artefact",
        "seal",
    }
)

__all__ = ["AER_FORMAT_ID", "AER_VERSION", "READABLE_VERSIONS", "RECORD_KINDS"]
