"""``adprov-v2.3-compat``: the frozen AgentDojo-PROV v2.3 provenance profile (docs/architecture EF E.8, J.3.3; R-31).

This package is a **regression oracle and migration bridge**, not the recommended semantics (D7). Its five modules
``build_prov``, ``prov_emit``, ``labeling``, ``validate`` and ``conformance`` are the baseline files at commit ``579a908``,
AST-equal to the originals with import statements as the only change (``PORT_MANIFEST.json`` records every change and the
digests). They MUST NOT be edited, reformatted or "fixed": the defects they keep on purpose (activity conflation, taint as
``prov:used``, time fallbacks, fail-open labels, incomplete IRI escaping) are part of the oracle. Everything else in this
directory is glue and is not part of the oracle: this ``__init__``, ``serialise.py``, ``yaml_shim.py`` and the byte copy
``adprov.ttl`` of the baseline's ``docs/ns/adprov.ttl``.

Quarantine (MN M.5.2(3)): import this package only from ``agentprov.prov.specs`` (lazily), ``agentprov.migration`` and tests.
The module is cheap to import and loads no oracle module until a :class:`CompatSpec` method is called.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

#: The spec id. It is never bumped: the oracle is frozen (E.8.1).
SPEC_ID: Final = "adprov-v2.3-compat"

#: The corpus-manifest and index flag of every compat output (R-55; K.5.8).
STATUS: Final = "apv:RegressionOracle"

#: The frozen ``adprov:`` namespace IRI (D7; ``prov_emit.ADPROV_NS``, ``prov_emit.py:17``).
NAMESPACE_IRI: Final = "https://nickjones39.github.io/agentdojo-prov/ns#"

#: Printed whenever compat output is written or loaded (R-55).
NOTICE: Final = (
    f"notice: {SPEC_ID} output is a regression oracle ({STATUS}), kept byte-identical to AgentDojo-PROV v2.3 at 579a908; "
    "it is not the recommended provenance semantics (use agentprov-prov/0.1)."
)


@dataclass(frozen=True, slots=True)
class CompatSpec:
    """The ``adprov-v2.3-compat`` provenance spec: identity, status and the three oracle entry points.

    Provisional shape. The ``ProvSpec`` protocol is defined with the engine in phase 5 (``prov/specs.py``); this object
    exposes exactly what that protocol will need from the oracle and adds nothing else. ``build`` always runs the oracle
    with its default flags (``emit_content``, ``emit_source_agents`` and ``emit_derived_edges`` all ``False``, E.8.1).
    """

    id: str = SPEC_ID
    status: str = STATUS
    namespace: str = NAMESPACE_IRI

    def build(self, transcript: dict[str, Any]) -> dict[str, Any]:
        """PROV-JSON of one transcript/v1 view (``build_prov.build_prov`` with default flags)."""
        from agentprov.prov.compat.adprov_v2_3.build_prov import build_prov

        return build_prov(transcript)

    def serialise(self, doc: dict[str, Any]) -> bytes:
        """The bytes the baseline stored for ``doc`` (``json.dumps(doc, indent=2)``, UTF-8, no trailing newline)."""
        from agentprov.prov.compat.adprov_v2_3.serialise import serialise

        return serialise(doc)

    def validate(self, doc: dict[str, Any]) -> Any:
        """The ported shape invariants I1-I11 (``validate.validate_prov_document``); returns its ``ValidationResult``."""
        from agentprov.prov.compat.adprov_v2_3.validate import validate_prov_document

        return validate_prov_document(doc)


#: The one spec object.
SPEC: Final = CompatSpec()

__all__ = ["NAMESPACE_IRI", "NOTICE", "SPEC", "SPEC_ID", "STATUS", "CompatSpec"]
