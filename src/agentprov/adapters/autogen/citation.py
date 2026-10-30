"""The AutoGen family's D-rule citation policy (D.5.4 "Citation of D rules", D-24, D-303).

Three D rules of the ``autogen`` catalogue rest on AutoGen library behaviour and cite the code they were read from:
``microsoft/autogen`` at tag ``python-v0.7.5`` (``83afbf58``; ``_assistant_agent.py``, ``messages.py``,
``_static_workbench.py``, ``_base.py``). The mapper cites them at D for a run only when the profile's
``[family.autogen] verified_code`` names that commit; otherwise it cites their ``_unverified`` twins (class I). The rules
in :data:`INDEPENDENT` are deterministic functions of observed fields (an id join, a text or digest comparison, a key
join against pinned data) and hold whatever code wrote the log.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agentprov.adapters.code_verification import Citations, parse_verified_code

__all__ = ["INDEPENDENT", "NAMESPACES", "citations"]

NAMESPACES: Final = frozenset({"autogen"})
INDEPENDENT: Final = frozenset({
    "autogen.label_facets@1",
    "autogen.event_attempt@1",
    "autogen.request_seq@1",
    "autogen.response_text_equal@1",
    "autogen.thought_equal@1",
    "autogen.response_call_ids@1",
    "autogen.probe_join@1",
    "autogen.passage_in_document@1",
    "autogen.task_template_digest@1",
    "autogen.guard_text_digest@1",
    "autogen.guard_raw_join@1",
    "autogen.no_model_call@1",
    "autogen.acc.side_list@1",
})


def citations(family: Mapping[str, object], facets: Mapping[str, str | None], where: str) -> Citations:
    """The citation policy for one run of a profile, by its facets (``variant``)."""
    verified = parse_verified_code(family.get("verified_code", ()) or (), where)  # type: ignore[arg-type]
    return Citations(verified, facets, namespaces=NAMESPACES, independent=INDEPENDENT)
