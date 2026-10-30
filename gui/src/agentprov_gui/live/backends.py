"""The Run live backend picker (user decision 2026-10-22, relayed by the orchestrator). No Qt.

A backend entry is a registry source whose live capability names a registered backend (``adapters.registry``:
``agentdojo`` and ``autodojo`` today; ``agentdyn`` once its backend is built). Import-only benchmarks (a live part
without a backend) have no entry. The CLI's ``run <source> --catalogue`` (D-652) is the source of truth for what a
backend offers; an environment that is not built is shown as such and nothing is launched for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from agentprov.adapters.registry import BACKENDS, REGISTRY

__all__ = ["NOT_BUILT", "LiveBackend", "live_backends"]

NOT_BUILT: Final = "not built: agentprov backends build {backend}"


@dataclass(frozen=True, slots=True)
class LiveBackend:
    source: str  # the run SOURCE
    backend: str  # the backend environment
    live_status: str | None
    profile: str


def live_backends() -> list[LiveBackend]:
    out: dict[str, LiveBackend] = {}
    for registration in REGISTRY:
        for cap in registration.capabilities:
            backend = cap.backend
            if cap.live_status is not None and backend is not None and backend in BACKENDS \
                    and registration.source_id not in out:
                out[registration.source_id] = LiveBackend(registration.source_id, backend, cap.live_status,
                                                          BACKENDS[backend].profile)
    return [out[k] for k in sorted(out)]
