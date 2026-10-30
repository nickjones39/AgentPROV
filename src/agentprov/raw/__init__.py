"""L1 raw evidence store (docs/architecture D3, G.3.1, HL H.1.2; MN M.1.2).

========================  =====================================================================================
module                    purpose
========================  =====================================================================================
``store``                 content-addressed, immutable objects ``raw/objects/<h0h1>/<sha256>.<ext>``, mode 0444
``origins``               :class:`Origin` records and ``raw/origins.jsonl``
``members``               the versioned ``expand`` stage (AD-12) and ``raw/members.jsonl``
========================  =====================================================================================

``fetch`` (pinned, verified, extraction-free acquisition; the one raw module with network and subprocess use) and
``references`` (``raw/REFERENCES.json``) are imported explicitly (``from agentprov.raw.fetch import Fetcher``), not by this
package, so importing the store never loads the network stack. ``purge`` arrives in a later phase. The ``members`` names
are re-exported lazily (GR-34): ``members`` loads the worker pool and the host probes, which a reader of the store or of a
corpus (the GUI) does not need.
"""

from typing import TYPE_CHECKING, Any

from agentprov.raw.origins import Origin, OriginLog, OriginRow
from agentprov.raw.store import PutResult, RawObjectStore, put_stream

if TYPE_CHECKING:
    from agentprov.raw.members import (
        ContainerSpec,
        ExpandEvent,
        ExpandOutcome,
        MemberLog,
        MemberRow,
        Selection,
        expand_containers,
    )

_MEMBERS: frozenset[str] = frozenset(
    {"ContainerSpec", "ExpandEvent", "ExpandOutcome", "MemberLog", "MemberRow", "Selection", "expand_containers"}
)

__all__ = [
    "ContainerSpec",
    "ExpandEvent",
    "ExpandOutcome",
    "MemberLog",
    "MemberRow",
    "Origin",
    "OriginLog",
    "OriginRow",
    "PutResult",
    "RawObjectStore",
    "Selection",
    "expand_containers",
    "put_stream",
]


def __getattr__(name: str) -> Any:
    if name in _MEMBERS:  # GR-34: loaded on first use only
        from agentprov.raw import members

        return getattr(members, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

