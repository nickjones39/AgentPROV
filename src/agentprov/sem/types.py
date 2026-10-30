"""Types of ``sem/0.1``, the standoff semantic annotations of one AER execution (C.14; EF E.7.1).

SEM holds *interpretations* of an AER file: integrity labels, tool roles, source channels, injection markers and
outcome polarity, produced by a versioned **semantics profile** that an adapter family supplies (D6). Annotations
never modify the AER; they target AER record or part ids and are hashed separately, so a labelling change never
changes an AER digest (C.14.1).

This module is the one in-code definition of the closed SEM vocabularies (C.14.3, EF E.7.1) and of the contract
between the three parties that meet at SEM:

- a semantics profile (:class:`SemanticsProfile`) yields :class:`Annotation` values for one AER;
- the SEM engine (:mod:`agentprov.sem.engine`) numbers them ``a0, a1, …`` in yield order, writes the header and
  the seal, and returns a :class:`SemDocument`;
- the PROV engine reads :class:`SemDocument` values (never profiles' code paths other than :attr:`taint_policy`)
  to build one assessment bundle per document (EF E.7.2).

Records are plain ``dict`` objects at run time, as for the AER.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, runtime_checkable

from agentprov.aer.types import Json

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = [
    "ANNOTATION_TYPES",
    "CORE_OUTCOME_CLAIMS",
    "INTEGRITY_VALUES",
    "MARKER_STATUSES",
    "ROLE_VALUES",
    "SEM_FORMAT",
    "SEM_VERSION",
    "SINK_ROLES",
    "Annotation",
    "Premise",
    "SemDocument",
    "SemanticsProfile",
    "TaintPolicy",
    "sem_profile_dir",
]

#: The format axis (L.1) and the header's ``sem`` member.
SEM_FORMAT: Final = "sem/0.1"
SEM_VERSION: Final = "0.1"

#: The core annotation types (C.14.3). Any other type is namespaced ``<ns>.<name>`` and declared by the profile.
ANNOTATION_TYPES: Final = ("integrity", "channel", "role", "injection_marker", "outcome", "author")
#: Three-valued integrity; ``unknown`` is a lattice value (fail-closed), never a default ``trusted`` (C.14.3).
INTEGRITY_VALUES: Final = ("trusted", "untrusted", "unknown")
#: EF E.7.1's security-role vocabulary (``apv:securityRole``); ``["unknown"]`` for tools a profile does not know.
ROLE_VALUES: Final = (
    "write_sink",
    "send_sink",
    "execute_sink",
    "egress_read",
    "response_sink",
    "content_source",
    "endorser",
    "neutral",
    "unknown",
)
#: The privileged roles of the v2.3 sink table, refined (C.14.5).
SINK_ROLES: Final = frozenset({"write_sink", "send_sink", "execute_sink"})
#: ``injection_marker`` statuses (C.14.3): ``ambiguous`` when a normaliser rejects the output, ``gap`` when the
#: fixture is missing or the output unreadable.
MARKER_STATUSES: Final = ("present", "absent", "ambiguous", "gap")
#: Outcome claims named by C.14.3; profiles may add namespaced claims (``<ns>.<claim>``).
CORE_OUTCOME_CLAIMS: Final = frozenset({"user_task_solved", "attack_succeeded", "attack_goal_progress"})

type EvidenceTag = Literal["O", "D", "I"]


def sem_profile_dir(profile_id: str, version: int) -> str:
    """The corpus directory name of a semantics profile: ``<id>-<version>`` (HL; RESOLUTIONS §3.5)."""
    return f"{profile_id}-{version}"


@dataclass(frozen=True, slots=True)
class Premise:
    """An AER field (or an earlier annotation) an annotation reads (C.14.2 ``premises``); becomes
    ``apv:sourcePointer`` in PROV. ``p`` is a JSON Pointer into the record (``""`` for the whole record)."""

    id: str
    p: str = ""

    def as_json(self) -> dict[str, Json]:
        return {"id": self.id, "p": self.p}


@dataclass(frozen=True, slots=True)
class Annotation:
    """One annotation as a profile yields it, before the engine assigns its id ``a<n>`` (C.14.2).

    ``rule`` is at least one ``RuleRef`` (``<ns>.<rule>@<n>`` with an optional ``#<pointer>``) from a catalogue the
    profile declares in :attr:`SemanticsProfile.rules`. ``ev`` follows C.6.5 rule 3: ``O`` only when the source
    itself recorded the label. ``method`` and ``confidence`` are required for method-based ``I`` annotations
    (attribution, judges). A premise may name an earlier annotation by the id it will receive (``a<n>``, n smaller
    than this annotation's index).
    """

    target: str
    type: str
    value: Json
    ev: EvidenceTag
    rule: tuple[str, ...]
    premises: tuple[Premise, ...]
    at: str | None = None
    span: tuple[int, int] | None = None
    method: str | None = None
    confidence: float | None = None

    def to_record(self, ann_id: str) -> dict[str, Json]:
        """The ``k: "ann"`` record (C.14.2); optional members are omitted when ``None``."""
        record: dict[str, Json] = {
            "k": "ann",
            "id": ann_id,
            "target": self.target,
            "type": self.type,
            "value": self.value,
            "ev": self.ev,
            "rule": list(self.rule),
            "premises": [p.as_json() for p in self.premises],
        }
        if self.at is not None:
            record["at"] = self.at
        if self.span is not None:
            record["span"] = [self.span[0], self.span[1]]
        if self.method is not None:
            record["method"] = self.method
        if self.confidence is not None:
            record["confidence"] = self.confidence
        return record


@dataclass(frozen=True, slots=True)
class TaintPolicy:
    """The policy that turns exposures into taint assessments (EF E.7.3 ``aprov.a_taint@1``).

    An exposure (request part ``p`` exposed to context member ``m``) becomes ``apv:PotentiallyInfluencedBy`` when the
    request's roles meet ``subject_roles`` and the member's integrity is in ``object_integrity``. ``rule`` is the
    profile's rule reference stated as ``apv:policy`` (e.g. ``agentdojo.taint_sink_untrusted@1``). For the v2.3
    reading: sink roles plus ``unknown`` (fail-closed) over ``untrusted`` and ``unknown`` integrity.
    """

    rule: str
    subject_roles: frozenset[str]
    object_integrity: frozenset[str]


@runtime_checkable
class SemanticsProfile(Protocol):
    """A versioned semantics profile supplied by an adapter family (C.14.1; D.1 "Semantics profile").

    Profiles are data plus small pure functions (tool tables, integrity, roles, marker normalisers, outcome
    polarity). ``annotate`` MUST be deterministic, read only the AER (never raw bytes), and yield annotations in a
    stable order; it MUST label tools it does not know ``unknown`` (integrity) and ``["unknown"]`` (role).
    """

    @property
    def id(self) -> str: ...  # "<ns>.<name>", e.g. "agentdojo.suites"

    @property
    def version(self) -> int: ...  # integer, bumped on any byte change (AD-18)

    @property
    def sha256(self) -> str: ...  # hex digest of the profile's data files (:func:`agentprov.sem.profiles.profile_digest`)

    @property
    def rules(self) -> Mapping[str, int]: ...  # catalogue namespace -> version the annotations cite

    @property
    def ns(self) -> Mapping[str, Json]: ...  # namespaced annotation types "<ns>.<name>" -> JSON Schema of the value

    @property
    def taint_policy(self) -> TaintPolicy | None: ...

    def annotate(self, aer: AerDocument) -> Iterable[Annotation]: ...


@dataclass(slots=True)
class SemDocument:
    """A sealed SEM document, in memory or read back and verified (C.14.1).

    ``records`` holds the header and the annotations in file order (the seal excluded). ``digest`` is the hex
    SHA-256 over every line before the seal (the seal's ``records_sha256``, the SEM digest of the D9 chain).
    """

    header: dict[str, Any]
    records: list[dict[str, Any]]
    seal: dict[str, Any]
    digest: str
    file_sha256: str
    _index: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _by_target: dict[str, list[dict[str, Any]]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for record in self.records[1:]:
            self._index[str(record["id"])] = record
            self._by_target.setdefault(str(record["target"]), []).append(record)

    @property
    def ex(self) -> str:
        return str(self.header["ex"])

    @property
    def profile_id(self) -> str:
        return str(self.header["profile"]["id"])

    @property
    def profile_version(self) -> int:
        return int(self.header["profile"]["version"])

    @property
    def profile_dir(self) -> str:
        return sem_profile_dir(self.profile_id, self.profile_version)

    @property
    def aer_digest(self) -> str:
        """The header's ``aer_digest`` as bare hex (the header stores ``sha256:<hex>``)."""
        return str(self.header["aer_digest"]).removeprefix("sha256:")

    @property
    def annotations(self) -> list[dict[str, Any]]:
        return self.records[1:]

    def get(self, ann_id: str) -> dict[str, Any] | None:
        return self._index.get(ann_id)

    def on(self, target: str, type_: str | None = None) -> list[dict[str, Any]]:
        """The annotations whose ``target`` is ``target`` (optionally of one type), in file order."""
        found = self._by_target.get(target, [])
        return found if type_ is None else [a for a in found if a["type"] == type_]
