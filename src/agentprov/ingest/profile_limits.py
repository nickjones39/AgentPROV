"""Profile-raised ingest limits (D-323, RB-2; docs/architecture G.3.2, D.2.9 note item 14).

A source profile may raise a few tier-1 limits in ``[import] limits``. Only the fields of :data:`PROFILE_RAISABLE` may
be declared, each from its G.3.2 default up to a calibrated ceiling (raise-only). No worker resource cap
(``io.workers.WorkerLimits``) is ever profile-raisable. The profile loader checks the table
(:func:`check_profile_limits`), and the importer applies it (:func:`apply_profile_limits`), so the raised value is
recorded in ``corpus.json`` as an override, which ``recompute`` replays and compares.

This module is deliberately separate from :mod:`agentprov.ingest.limits`. That file is one of the ``expand`` stage's
hashed modules (``raw.members.EXPAND_MODULES``), and keeping it unchanged keeps every container corpus's ``expand``
identity unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agentprov.ingest.limits import MIB, IngestLimits

__all__ = ["PROFILE_RAISABLE", "apply_profile_limits", "check_profile_limits"]

#: The raisable fields and their ceilings. The element ceiling is the calibrated value
#: (``docs/reports/r10k1/d323-calibration.md``): a 64 MiB element streamed through ``open_json_stream`` and a mapper in a
#: release-mode T1 worker peaked at 1,197 MiB under the 2 GiB map RSS cap. A larger ceiling needs a new calibration.
PROFILE_RAISABLE: Final[Mapping[str, int]] = {"max_json_element_bytes": 64 * MIB}


def check_profile_limits(declared: object) -> dict[str, int]:
    """Validate a profile's ``[import] limits`` table: only :data:`PROFILE_RAISABLE` fields, each an integer from its
    default up to its ceiling. ``ValueError`` names the first defect; the profile loader turns it into a
    ``ProfileError``, so a profile with a defective table never loads."""
    if not isinstance(declared, Mapping):
        raise ValueError("[import] limits must be a table")
    defaults = IngestLimits()
    out: dict[str, int] = {}
    for name, value in sorted(declared.items()):
        if name not in PROFILE_RAISABLE:
            raise ValueError(f"[import] limits: {name!r} is not raisable by a profile (allowed: {sorted(PROFILE_RAISABLE)})")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"[import] limits: {name} must be an integer")
        if value < getattr(defaults, name):
            raise ValueError(f"[import] limits: {name} may only raise the default ({getattr(defaults, name)})")
        if value > PROFILE_RAISABLE[name]:
            raise ValueError(f"[import] limits: {name} exceeds its ceiling ({PROFILE_RAISABLE[name]})")
        out[name] = value
    return out


def apply_profile_limits(limits: IngestLimits, declared: object) -> IngestLimits:
    """``limits`` with a profile's ``[import] limits`` applied. Each declared field takes the declared value when it is at
    its default or already equal to it; a field set otherwise (another explicit override) is a conflict
    (``ValueError``), never a silent pick."""
    checked = check_profile_limits(declared)
    defaults = IngestLimits()
    for name, value in checked.items():
        current = getattr(limits, name)
        if current not in (getattr(defaults, name), value):
            raise ValueError(f"{name}: the profile declares {value}, the effective limits hold {current}")
    return limits.replace(**checked) if checked else limits
