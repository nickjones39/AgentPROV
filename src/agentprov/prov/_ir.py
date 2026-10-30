"""Internal representation of statements before routing and serialisation (not a public API).

Every node and relation the rules emit is a :class:`Stmt`. Its class is computed once, by the engine, from its
premises (E.1.5 item 2): the rule ceiling (or a per-path cap), the AER premise :class:`Field` s, the existence classes
of its endpoint nodes and the classes of its premise statements. Attributes (:class:`Attr`) carry their own premises
and are split out of the element when they are weaker (E.1.5 item 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.prov.evidence import EvidenceClass

__all__ = ["ARG_ORDER", "NODE_SECTIONS", "Attr", "Field", "Stmt", "dbl", "q"]

NODE_SECTIONS: Final = frozenset({"entity", "activity", "agent"})
#: PROV-JSON argument keys of each relation section, in PROV argument order (E.4.2 statement hash).
ARG_ORDER: Final[dict[str, tuple[str, ...]]] = {
    "used": ("prov:activity", "prov:entity"),
    "wasGeneratedBy": ("prov:entity", "prov:activity"),
    "wasInformedBy": ("prov:informed", "prov:informant"),
    "wasStartedBy": ("prov:activity", "prov:trigger", "prov:starter"),
    "wasInvalidatedBy": ("prov:entity", "prov:activity"),
    "wasDerivedFrom": ("prov:generatedEntity", "prov:usedEntity", "prov:activity", "prov:generation", "prov:usage"),
    "wasAttributedTo": ("prov:entity", "prov:agent"),
    "wasAssociatedWith": ("prov:activity", "prov:agent", "prov:plan"),
    "actedOnBehalfOf": ("prov:delegate", "prov:responsible", "prov:activity"),
    "specializationOf": ("prov:specificEntity", "prov:generalEntity"),
    "hadMember": ("prov:collection", "prov:entity"),
    "mentionOf": ("prov:specificEntity", "prov:generalEntity", "prov:bundle"),
}
#: Relations without an identifier (E.5.1 item 3): no attributes, key ``_:<rule-name>.<h16>``.
UNIDENTIFIED: Final = frozenset({"specializationOf", "hadMember", "mentionOf", "alternateOf"})


def q(qname: str) -> dict[str, str]:
    """A PROV-JSON QName value (E.5.3 item 3)."""
    return {"$": qname, "type": "prov:QUALIFIED_NAME"}


def dbl(value: float) -> dict[str, str]:
    """An ``xsd:double`` value in its shortest round-trip decimal form (E.5.3 item 3)."""
    return {"$": repr(float(value)), "type": "xsd:double"}


@dataclass(frozen=True, slots=True)
class Field:
    """An AER premise: record id and RFC 6901 pointer (``""`` is the record itself, i.e. its existence)."""

    rid: str
    ptr: str = ""


@dataclass(slots=True)
class Attr:
    """One attribute value of an element. ``fields`` empty means a structural constant (the element's own class)."""

    prop: str
    value: Any
    fields: tuple[Field, ...] = ()
    rule: str | None = None  # the attribute's rule when it is not the element's (after, status, part_of)
    ceiling: EvidenceClass = EvidenceClass.OBSERVED
    cited: tuple[str, ...] = ()  # AER rule ids whose class caps the attribute (e.g. a seal-issue rule)
    cls: EvidenceClass | None = None  # computed
    methods: frozenset[str] = frozenset()  # computed (INFERRED attributes)


@dataclass(eq=False, slots=True)
class Stmt:
    rule: str
    section: str
    args: dict[str, str]  # argument key -> node local name (or a full prefixed name for top-level/bundle refs)
    attrs: list[Attr] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)  # endpoint / capping node local names
    prem: list[Stmt] = field(default_factory=list)  # premise statements (classes and method sets propagate)
    ceiling: EvidenceClass = EvidenceClass.OBSERVED
    assumptions: tuple[str, ...] = ()  # the engine rule's own assumption terms on this path
    cited: tuple[str, ...] = ()  # AER rule ids that declare an assumption the statement rests on (class premises)
    disc: str = ""
    name: str | None = None  # node local name; for relations computed after routing
    # class premises that are not AER fields: SEM annotations, as (class, method set) (assessment bundle, E.7.3)
    sem: list[tuple[EvidenceClass, frozenset[str]]] = field(default_factory=list)
    # computed by the engine
    cls: EvidenceClass | None = None
    methods: frozenset[str] = frozenset()
    bundle: tuple[str, frozenset[str]] | None = None  # ("core", ∅) or ("inf", method set)
    top: bool = False  # top-level statement (conversion provenance): no AER evidence attributes

    @property
    def is_node(self) -> bool:
        return self.section in NODE_SECTIONS
