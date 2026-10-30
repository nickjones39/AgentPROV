"""T1 job ``validate``: tiers 3 and 4 of one stored execution for ``validate --corpus`` (MN N.2.5; G.4.2; D-413).

The parent (:func:`agentprov.corpus.validation.validate_corpus` with ``jobs``) reads and verifies every document, runs the
AER tier itself, and hands the exact verified bytes to this job by digest from a private scratch store (G.4.5). The job
runs :func:`~agentprov.corpus.validation.validate_documents`, the function the in-process path runs, so the two give the
same checks.

Inputs, in order: role ``aer``; one ``sem`` per ref in ``params["sems"]`` (the refs whose SEM document was read, in the
order of ``semantics``); role ``prov`` when ``params["prov"]``. Params: ``tiers``, ``mode``, ``semantics``, ``sems``,
``prov``. Frame: one ``{"checks": {id: status}, "spec"?, "versions"?}`` (ids and statuses only, as a stored row).

The round-trip cache (D-550; :mod:`agentprov.validate.cache`): with ``params["fidelity"]`` (``{"collect", "hint"}``)
and ``hint`` true, one more input, role ``fidelity``, holds the parent's cache entry for the document it expects; it
replaces the round trip only when it names the digest of the PROV bytes read here and this worker's context. With
``collect``, a round trip that ran and completed is returned in a second frame, ``{"fidelity": ...}``, for the parent
to store. The job reads no file besides its inputs.

The validators and every shipped semantics profile are imported and loaded here at module level, so a worker loads them
before its audit hook (G.4.4). A ref is resolved through the parent's default lookup
(:func:`~agentprov.corpus.validation.default_semantics_profile`), cached per worker: a pure function of package data
(G.4.7).
"""

from __future__ import annotations

from typing import Any, Final

from agentprov.adapters.semantics_profiles import load_all_semantics_profiles
from agentprov.aer.reader import load_aer_bytes
from agentprov.corpus.validation import default_semantics_profile, validate_documents
from agentprov.errors import AgentProvError
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.validate import validate_sem_document  # noqa: F401 - loaded before the audit hook (G.4.4)
from agentprov.validate import validate_prov  # noqa: F401 - loaded before the audit hook (G.4.4)
from agentprov.validate.cache import JobFidelity, context_digest

context_digest()  # the cache context reads the package and library files: before the audit hook (G.4.4)

__all__ = ["job_validate"]

#: Semantics profiles by ref, seeded with every shipped profile under its canonical ref; any other ref is resolved on
#: first use through the parent's default lookup (``None`` when it does not resolve, as in the parent).
_PROFILES: Final[dict[str, Any]] = dict(load_all_semantics_profiles())


def _profile_of(ref: str) -> Any:
    if ref not in _PROFILES:
        try:
            _PROFILES[ref] = default_semantics_profile(ref)
        except (AgentProvError, ValueError):
            _PROFILES[ref] = None
    return _PROFILES[ref]


def job_validate(ctx: Any) -> dict[str, Any]:
    params = ctx.params
    refs = [str(r) for r in params["sems"]]
    aer = load_aer_bytes(ctx.read_input(0), verify=True)
    sems = {ref: load_sem_bytes(ctx.read_input(1 + n), verify=True) for n, ref in enumerate(refs)}
    prov = ctx.read_input(1 + len(refs)) if params.get("prov") else None
    fidelity: JobFidelity | None = None
    wanted = params.get("fidelity")
    if prov is not None and isinstance(wanted, dict):
        hint = ctx.read_input(2 + len(refs)) if wanted.get("hint") else None
        fidelity = JobFidelity(hint, collect=bool(wanted.get("collect")))
    part = validate_documents(aer, sems, prov, tiers=[str(t) for t in params["tiers"]], mode=str(params["mode"]),
                              semantics=[str(r) for r in params["semantics"]], profile_of=_profile_of,
                              fidelity=fidelity)
    ctx.emit(part)
    frame = fidelity.frame() if fidelity is not None else None
    if frame is not None:
        ctx.emit(frame)
    return {"checks": len(part["checks"])}
