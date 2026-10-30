"""The OpenHands family's D-rule citation policy (D.5.4 "Citation of D rules", D-24, D-172).

A D rule of the ``openhands`` catalogue whose reading rests on OpenHands behaviour cites the code it was read from
(``code`` entries at the fork commit ``5a13eacf`` and at OpenHands 1.5.0, ``a77b0550``). The mapper cites it at D for a
run only when the profile's ``[family.openhands] verified_code`` names one of those commits; otherwise it cites the
``_unverified`` twin (class I). The rules listed in :data:`INDEPENDENT` are deterministic functions of observed fields
(a key join, a digest comparison, a renaming) and hold whatever code wrote the log.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agentprov.adapters.code_verification import Citations, parse_verified_code

__all__ = ["INDEPENDENT", "NAMESPACES", "citations"]

NAMESPACES: Final = frozenset({"openhands"})
INDEPENDENT: Final = frozenset({
    "openhands.response_message@1",
    "openhands.response_kept@1",
    "openhands.usage_fields@1",
    "openhands.arguments_decoded@1",
    "openhands.served_model@1",
    "openhands.finish_control_call@1",
    "openhands.filtered_events@1",
    "openhands.fixed_reply_digest@1",
    "openhands.content_not_inlined@1",
    "openhands.oas_eval_path_join@1",
    "openhands.oas_summary_join@1",
    "openhands.oas_task_dir_join@1",
    "openhands.task_text_seen@1",
    "openhands.state_repr_fields@1",
    "openhands.redcode_score_join@1",
    "openhands.redcode_prompt_join@1",
    "openhands.redcode_request_type@1",
    "openhands.value_redacted@1",  # D-606: a profile-specified transformation by AgentPROV
})


def citations(family: Mapping[str, object], facets: Mapping[str, str | None], where: str) -> Citations:
    """The citation policy for one run of a profile, by its facets (``variant``)."""
    verified = parse_verified_code(family.get("verified_code", ()) or (), where)  # type: ignore[arg-type]
    return Citations(verified, facets, namespaces=NAMESPACES, independent=INDEPENDENT)
