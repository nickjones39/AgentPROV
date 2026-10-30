"""Registry rendering for ``agentprov info`` (docs/architecture D.3.5; MN N.2.9; layer L6).

Everything printed is generated from the registry data and the shipped profiles, per part and with caveats; nothing is
hand-written. Only registry and profile data are rendered; the caller passes every string through ``escape_untrusted``
before it reaches a terminal (D.3.5 rule 3). Loading a profile reads package data only and imports no adapter family.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from agentprov.adapters.registry import REGISTRY, REGISTRY_DATE, Capability, SourceRegistration, get_source

__all__ = ["registry_rows", "source_detail", "status_text"]

_PIN_KEYS: Final = ("role", "part", "kind", "repo", "commit", "date", "tree", "doi", "expected_files", "listing_sha256", "primary")


def status_text(value: str | None) -> str:
    """The rendered status: the closed vocabulary of D.3.2, ``—`` for none."""
    return "—" if value is None else value


def _restricted(registration: SourceRegistration, capability: Capability) -> bool:
    """Whether the part carries a use restriction: its profile's ``[licence] restrictions`` (the survey's AgentHarm part
    does, its AgentDojo part does not), else the registration's."""
    if capability.profile:
        from agentprov.adapters.profiles import load_profile

        return bool(load_profile(capability.profile).data.get("licence", {}).get("restrictions"))
    return bool(registration.licence.restrictions)


def _row(registration: SourceRegistration, capability: Capability) -> dict[str, Any]:
    return {
        "source_id": registration.source_id,
        "part": capability.part,
        "role": capability.role,
        "evidence": capability.evidence,
        "import": capability.import_status,
        "import_target": capability.target_import_status,
        "live": capability.live_status,
        "policy": registration.licence.policy,
        "restricted": _restricted(registration, capability),
        "caveat": capability.caveat,
        "profile": capability.profile,
        "corpus_id": capability.corpus_id,
        "sealed": [f"{s.corpus_id} {s.version} (tag {s.tag})" for s in capability.sealed],  # display only
        "dialects": list(capability.dialects),
        "variants": list(capability.variants),
        "via": capability.via,
        "owner": capability.owner,
    }


def registry_rows() -> dict[str, Any]:
    """The registry as JSON-able data, in registry order (one row per part; D.3.5 rule 1)."""
    return {
        "available": True,
        "date": REGISTRY_DATE,
        "parts": [_row(r, c) for r in REGISTRY for c in r.capabilities],
        "sources": [r.source_id for r in REGISTRY],
    }


def source_detail(source_id: str) -> dict[str, Any]:
    """``info --source ID`` (D.3.5 rule 2, phase-6 subset): parts, the profile identities and pins, licence policy,
    restrictions, basis and attribution, and the evidence references. ``KeyError`` for an unregistered id."""
    from agentprov.adapters.profiles import load_profile

    registration = get_source(source_id)
    profiles: dict[str, Any] = {}
    for capability in registration.capabilities:
        if capability.profile and capability.profile not in profiles:
            profile = load_profile(capability.profile)
            pins = [
                {k: pin[k] for k in _PIN_KEYS if k in pin}
                for pin in profile.data.get("source", {}).get("pins", ())
                if isinstance(pin, Mapping)
            ]
            profiles[profile.id] = {"version": profile.version, "sha256": profile.sha256, "pins": pins}
    licence = registration.licence
    return {
        "source_id": registration.source_id,
        "name": registration.name,
        "family": registration.family,
        "parts": [_row(registration, c) for c in registration.capabilities],
        "profiles": profiles,
        "licence": {
            "spdx": licence.spdx,
            "data_licence": licence.data_licence,
            "policy": licence.policy,
            "restrictions": list(licence.restrictions),
            "basis": licence.basis,
            "attribution": list(licence.attribution),
            "unassessed": list(licence.unassessed),
        },
        "evidence_refs": list(registration.evidence_refs),
    }
