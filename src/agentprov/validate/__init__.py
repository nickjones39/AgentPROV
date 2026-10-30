"""D8 validators (layer L3; MN M.1.2): the check registry, tier 3 (SEM) and the tier-4 validators of ``agentprov-prov/0.1``.

``validate_sem(path, aer_path)`` / ``validate_sem_document(sem, aer)`` run tier 3 (C.14.4; :mod:`agentprov.sem.validate`)
and :func:`~agentprov.validate.tiers.report_outcomes` folds their report into check outcomes (``SEM_CHECKS``).

``validate_prov(prov_json, aer)`` runs every tier-4 check (structure, PROV-CONSTRAINTS subset, evidence linkage, profile
rules including the never-emit list, serialisation fidelity) and returns a :class:`Tier4Report`. The submodules import
only layers L0-L2 (``io``, ``ingest``, ``aer``, ``sem``, ``prov``).
"""

from __future__ import annotations

from agentprov.sem.validate import SEM_CHECKS, validate_sem, validate_sem_document
from agentprov.validate.prov import validate_prov
from agentprov.validate.tiers import TIERS, CheckOutcome, CheckStatus, Finding, Tier4Report, report_outcomes

__all__ = [
    "SEM_CHECKS",
    "TIERS",
    "CheckOutcome",
    "CheckStatus",
    "Finding",
    "Tier4Report",
    "report_outcomes",
    "validate_prov",
    "validate_sem",
    "validate_sem_document",
]
