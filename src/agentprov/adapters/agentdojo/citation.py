"""The AgentDojo family's D-rule citation policy (D.5.4 "Citation of D rules", D-24): which catalogues it governs and
which D rules hold whatever code wrote the log.

The resolution itself is :class:`agentprov.adapters.code_verification.Citations`: a D rule of these namespaces is cited
at D for a log only when its catalogue ``code`` list cites a commit of the profile's ``[harness] verified_code`` that
applies to the log, else through its ``_unverified`` twin.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agentprov.adapters.agentdojo.profile import FamilyTable
from agentprov.adapters.code_verification import Citations

__all__ = ["INDEPENDENT", "NAMESPACES", "citations"]

#: The family's rule catalogues (D.5.1 homes under ``adapters/agentdojo/rules/``).
NAMESPACES: Final = frozenset({"agentdojo", "agentdyn", "autodojo", "drift", "mandate", "rescont", "rope", "survey"})
#: D rules whose reading does not depend on the code that wrote the log, so they are D for every profile.
INDEPENDENT: Final = frozenset({
    # the logged system text has the SHA-256 the profile pins for a variant: a digest comparison against pinned bytes
    "agentdojo.system_prompt_variant_digest@1",
    # ROPE's released correction code (ported verbatim, its digests checked against the context artefacts) applied to the
    # logged messages: a computation over the log, beside the recorded value, never a reading of the harness
    "rope.security_correction@1",
    # the injection-marker normalisers: text computations over the logged output (the port of the AgentDojo-PROV v2.3
    # marker at 579a908, and two fallback readings with no harness code); the harness-dependent part, how the harness
    # rendered the output, is agentdojo.injection_marker_yaml@1's (D-86 addendum, user decision 2026-10-12)
    "agentdojo.yaml_norm@1", "agentdojo.pyrepr_norm@1", "agentdojo.json_norm@1",
    # regeneration-batch items 8, 6 and 4: the strict YAML reading, a payload's longest run in the output, and a logged
    # success with no payload visible in any message part: text computations over the AER, like the normalisers
    "agentdojo.yaml_norm@2", "agentdojo.partial_payload@1", "agentdojo.success_without_visible_payload@1",
})


def citations(fam: FamilyTable, facets: Mapping[str, str | None]) -> Citations:
    """The citation policy for one log of a profile, by its facets (``variant`` and the layout components)."""
    return Citations(fam.verified_code, facets, namespaces=NAMESPACES, independent=INDEPENDENT)
