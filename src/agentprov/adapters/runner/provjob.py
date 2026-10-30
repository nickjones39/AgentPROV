"""T1 job ``prov``: SEM annotation, ``agentprov-prov/0.1`` derivation and tiers 3–4 of one sealed AER (MN N.2.2 steps
4–5; G.4.1).

G.4.1 lets SEM, PROV and validation run in T1 (MAY). The import pipeline runs them here because ``validate_prov`` is the
dominant cost of an import (about 0.4 s per AgentDojo execution) and the parent must stay free for the write gate. The
module imports the SEM and PROV engines, the validators and **every shipped semantics profile** at module level, so a
worker loads them before its audit hook is installed (G.4.4); a job reads nothing but its input.

Input 0 is the sealed AER file, read by digest from the pipeline's scratch store and re-hashed (G.4.5). Params:
``semantics`` (profile references ``<id>@<version>`` to annotate with, in order), ``derive`` (run the PROV stage; false
for ``--until sem``), ``spec`` (only ``agentprov-prov/0.1``), ``validate`` (run tiers 3 and 4) and ``strict`` (release
mode: a skipped check is a failure, D8). Frames, per profile: a ``$member`` header ``{"size", "role": "sem", "profile"}``
with the canonical SEM bytes, then with ``validate`` ``{"sem_validation": {"profile", "checks"}}``; or
``{"sem_error": {"profile", "code"}}``. Then ``{"prov_error": code}`` when derivation fails; otherwise a ``$member``
header ``{"size", "role": "prov"}`` with the canonical PROV-JSON bytes, then, with ``validate``, ``{"validation":
{"checks": {id: status}, "verdict", "versions"}}``. PROV is derived from the AER and the SEM documents that were
produced; a profile that failed contributes no assessment bundle (its failure is the stage's record). The AER is not
re-validated here: the parent ran the AER validator over the same bytes before it wrote them (``derive(check_aer=False)``,
E.0.1 item 4).

The tier-4 round-trip cache (D-550; :mod:`agentprov.validate.cache`): with ``validate`` and ``params["fidelity"]``
(``{"collect", "hint"}``), a ``hint`` input (index 1, role ``fidelity``) holds the parent's cache entry for the PROV the
parent expects; it replaces the round trip only when it names the digest of the bytes derived here and this worker's
context. With ``collect``, a round trip that ran and completed is emitted last, as ``{"fidelity": ...}``, for the parent
to store. The job reads no file besides its inputs.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from agentprov.adapters.semantics_profiles import load_all_semantics_profiles
from agentprov.aer.reader import load_aer_bytes
from agentprov.errors import AgentProvError
from agentprov.prov.engine import ProvDerivationError, derive
from agentprov.prov.specs import SPEC_ID
from agentprov.sem.engine import annotate, dumps_sem
from agentprov.sem.types import SemanticsProfile
from agentprov.sem.validate import SEM_CHECKS, validate_sem_document
from agentprov.validate import validate_prov
from agentprov.validate.cache import JobFidelity, context_digest
from agentprov.validate.tiers import report_outcomes

__all__ = ["PROFILES", "job_prov", "tier3_checks", "tier4_row"]

SUPPORTED_SPECS: Final = (SPEC_ID,)
#: Every shipped semantics profile, ``<id>@<version>`` -> profile (loaded at import, before the audit hook).
PROFILES: Final[dict[str, SemanticsProfile]] = load_all_semantics_profiles()
context_digest()  # the round-trip cache context reads package and library files: before the audit hook (G.4.4)


def tier4_row(report: Any, *, strict: bool) -> dict[str, Any]:
    """The tier-4 part of a ``validation/results.jsonl`` row: every check's status, the verdict, the versions.

    Only check ids and statuses are kept (finding details may quote identifiers derived from source data)."""
    checks = {o.id: o.status for o in report.outcomes}
    passed = report.passed if strict else report.ok
    return {"checks": dict(sorted(checks.items())), "verdict": "pass" if passed else "fail",
            "versions": dict(sorted(report.versions.items()))}


def tier3_checks(report: Any, profile: str) -> dict[str, str]:
    """The tier-3 checks of one SEM document, ``<profile ref>:<SEM check id>`` -> status (ids and statuses only)."""
    return {f"{profile}:{o.id}": o.status for o in report_outcomes(report, SEM_CHECKS)}


def job_prov(ctx: Any) -> dict[str, Any]:
    params = ctx.params
    spec = str(params.get("spec", SPEC_ID))
    if spec not in SUPPORTED_SPECS:
        raise ValueError(f"unsupported provenance spec {spec!r}")
    doc = load_aer_bytes(ctx.read_input(0))
    mode: Literal["dev", "release"] = "release" if params.get("strict") else "dev"
    sems: list[Any] = []
    profiles: dict[tuple[str, int], SemanticsProfile] = {}
    for ref in params.get("semantics", ()):
        profile = PROFILES.get(str(ref))
        if profile is None:
            ctx.emit({"sem_error": {"code": "sem.profile_unavailable", "profile": ref}})
            continue
        try:
            sem = annotate(doc, profile)
        except AgentProvError as exc:
            ctx.emit({"sem_error": {"code": exc.code, "profile": ref}})
            continue
        data = dumps_sem(sem)
        ctx.member({"profile": ref, "role": "sem", "size": len(data)})
        ctx.data(data)
        if params.get("validate"):
            sem_report = validate_sem_document(sem, doc, mode=mode, profile=profile)
            ctx.emit({"sem_validation": {"checks": dict(sorted(tier3_checks(sem_report, ref).items())), "profile": ref}})
        sems.append(sem)
        profiles[(profile.id, profile.version)] = profile
    if not params.get("derive", True):
        return {"annotated": len(sems), "derived": 0}
    try:
        result = derive(doc, sems, sem_profiles=profiles, check_aer=False)
    except ProvDerivationError as exc:
        ctx.emit({"prov_error": exc.code})
        return {"annotated": len(sems), "derived": 0}
    data = result.prov_json
    ctx.member({"role": "prov", "size": len(data)})
    ctx.data(data)
    if params.get("validate") and params.get("conformance", True):  # G2c-5: conformance False skips tier 4 only
        wanted = params.get("fidelity")
        fidelity = None
        if isinstance(wanted, dict) and params.get("conformance", True):  # G2c-5: a skipped tier 4 has no round trip
            fidelity = JobFidelity(ctx.read_input(1) if wanted.get("hint") else None, collect=bool(wanted.get("collect")))
        report = validate_prov(data, doc, sems=sems, fidelity=fidelity)
        ctx.emit({"validation": tier4_row(report, strict=bool(params.get("strict")))})
        frame = fidelity.frame() if fidelity is not None else None
        if frame is not None:
            ctx.emit(frame)
    return {"annotated": len(sems), "derived": 1, "bundles": len(result.bundles)}
