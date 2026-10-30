"""D8 tier 4 for ``agentprov-prov/0.1`` output: one entry point over every tier-4 validator (MN M.1.2; J.3.5 gate D).

``validate_prov(prov_json, aer)`` parses the canonical PROV-JSON bytes with the bounded strict loader (the document is
treated as untrusted input), checks that they are the JCS bytes of the decoded document (E.5.3 item 1) and runs, in
order, :mod:`~agentprov.validate.prov_structure`, :mod:`~agentprov.validate.constraints` (whose time checks are "MAY
flag" diagnostics, reported apart), :mod:`~agentprov.validate.linkage`, :mod:`~agentprov.validate.profiles` and
:mod:`~agentprov.validate.roundtrip`. It never raises on a malformed document: bytes that do not decode to a JSON object
give one failing structure check and nothing else runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from agentprov.aer.reader import AerDocument
from agentprov.aer.rules import RuleRegistry
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import prov_document_limits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes
from agentprov.prov.specs import ProvSpec, load_spec
from agentprov.prov.vocab import VOCAB_VERSION
from agentprov.validate import constraints, linkage, profiles, prov_structure
from agentprov.validate import roundtrip as roundtrip_checks
from agentprov.validate._provdoc import ProvView
from agentprov.validate.tiers import CheckOutcome, Finding, Tier4Report, outcome

if TYPE_CHECKING:
    from agentprov.sem.types import SemDocument
    from agentprov.validate.cache import Fidelity

__all__ = ["validate_prov"]

ROUNDTRIP_CHECKS: Final = ("model_equality", "graphs", "completeness", "datatypes", "unqualified_layer")


def validate_prov(
    prov_json: bytes,
    aer: AerDocument,
    *,
    migration: bool = False,
    roundtrip: bool = True,
    spec: ProvSpec | None = None,
    registry: RuleRegistry | None = None,
    sems: Sequence[SemDocument] = (),
    fidelity: Fidelity | None = None,
) -> Tier4Report:
    """Run every tier-4 check over one execution's PROV-JSON and its AER.

    ``migration`` enables the gate-D checks for v1-import AERs (context membership only in
    ``inf.adprov-context_is_prefix-v1``; no generic statements). ``roundtrip=False`` reports the serialisation-fidelity
    checks as ``skipped`` (a dev-mode shortcut; release mode counts skipped checks as failures). ``registry`` supplies
    the adapter catalogues named by the AER header (package resources by default), as for ``derive``; it must also
    hold the catalogues the SEM headers declare. ``sems`` are the SEM documents the assessment bundles were derived
    from (matched by digest); an assessment bundle without its SEM document fails ``pv.linkage.annotation``.

    ``fidelity`` (D-550, :mod:`agentprov.validate.cache`) is consulted only when the round trip runs: an outcome it
    holds for these bytes replaces the round trip, and a round trip that ran is handed to it to keep. Every other
    check runs either way, and a cached outcome is the one the round trip returned, so the report is the same.
    """
    spec = spec or load_spec()
    report = Tier4Report(versions={"spec": spec.id, "vocabulary": VOCAB_VERSION, **roundtrip_checks.library_versions()})
    try:
        doc = strict_json_loads(prov_json, prov_document_limits())  # D-935: the PROV-document limit
    except (AgentProvError, ValueError) as exc:
        failure = Finding("pv.prov_structure.not_json", "document", type(exc).__name__)
        report.outcomes.append(CheckOutcome("pv.prov_structure.document", "fail", (failure,)))
        return report
    if not isinstance(doc, dict):
        failure = Finding("pv.prov_structure.not_object", "document", type(doc).__name__)
        report.outcomes.append(CheckOutcome("pv.prov_structure.document", "fail", (failure,)))
        return report
    report.outcomes.append(outcome("pv.prov_structure.canonical_bytes", _canonical(prov_json, doc)))
    report.extend(prov_structure.check(doc))
    view = ProvView.parse(doc)
    checks, diagnostics = constraints.check(view)
    report.extend(checks)
    report.diagnostics.extend(diagnostics)
    report.extend(linkage.check(view, aer, spec=spec, registry=registry, sems=sems))
    report.extend(profiles.check(view, aer, migration=migration, spec=spec))
    if roundtrip:
        cached = fidelity.lookup(prov_json) if fidelity is not None else None
        if cached is None:
            computed = roundtrip_checks.check(doc, view)
            if fidelity is not None:
                fidelity.store(prov_json, computed)
            report.extend(computed)
        else:
            report.extend(cached)
    else:
        report.extend(CheckOutcome(f"pv.roundtrip.{n}", "skipped", reason="round trip disabled by the caller")
                      for n in ROUNDTRIP_CHECKS)
    return report


def _canonical(data: bytes, doc: object) -> list[Finding]:
    if jcs_bytes(doc) != data:
        return [Finding("pv.prov_structure.canonical_bytes", "document", "the bytes are not the JCS form (E.5.3 item 1)")]
    return []
