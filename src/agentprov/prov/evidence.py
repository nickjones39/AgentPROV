"""Evidence classes and statement-class arithmetic of ``agentprov-prov/0.1`` (EF E.0.3, E.0.4, E.1.5, F.1).

The engine reads classes only (AD-05): the adapter fixed every class at map time, so :func:`cls` and
:func:`existence` are pure functions of an AER record. :func:`weakest` is the only combinator, so nothing here can
raise a class (C.6.5 rule 5).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from typing import Any, Final

from agentprov.aer.evidence import effective_party, effective_tag, is_prefix, tag_class
from agentprov.aer.rules import RULE_REF_RE, rule_id_of

__all__ = [
    "CLASS_QNAME",
    "LETTER",
    "PARTY_QNAME",
    "EvidenceClass",
    "applicable_refs",
    "cls",
    "existence",
    "party",
    "weakest",
]


class EvidenceClass(enum.IntEnum):
    """Ordered: weaker < stronger (E.0.3)."""

    INFERRED = 0
    DERIVED = 1
    OBSERVED = 2

    @property
    def letter(self) -> str:
        return "IDO"[self.value]

    @property
    def qname(self) -> str:
        return CLASS_QNAME[self]


LETTER: Final[Mapping[str, EvidenceClass]] = {
    "O": EvidenceClass.OBSERVED,
    "D": EvidenceClass.DERIVED,
    "I": EvidenceClass.INFERRED,
}
CLASS_QNAME: Final[Mapping[EvidenceClass, str]] = {
    EvidenceClass.OBSERVED: "apv:Observed",
    EvidenceClass.DERIVED: "apv:Derived",
    EvidenceClass.INFERRED: "apv:Inferred",
}
#: AER ``by`` party -> attesting-party individual (E.4.5, F.1.3).
PARTY_QNAME: Final[Mapping[str, str]] = {
    "capture": "apv:ByCapture",
    "source": "apv:BySource",
    "provider": "apv:ByProvider",
    "benchmark": "apv:ByBenchmark",
    "config": "apv:ByConfig",
    "replay": "apv:ByReplay",
}


def weakest(*classes: EvidenceClass) -> EvidenceClass:
    """The minimum under INFERRED < DERIVED < OBSERVED; at least one class is required."""
    if not classes:
        raise ValueError("weakest() needs at least one class")
    return min(classes)


def cls(record: Mapping[str, Any], pointer: str) -> EvidenceClass:
    """The class of the field at ``pointer``: longest-prefix ``evf``, else the record's ``ev`` (C.6.3, E.0.4)."""
    return LETTER[tag_class(effective_tag(record, pointer))]


def existence(record: Mapping[str, Any]) -> EvidenceClass:
    """The record's existence class: its ``ev`` (C.6.1, R-22)."""
    ev = record.get("ev")
    if ev not in LETTER:
        raise ValueError("record has no existence class")
    return LETTER[str(ev)]


def party(record: Mapping[str, Any], pointer: str) -> str | None:
    """The attesting party of an OBSERVED field (``by`` or the ``O:<party>`` of ``evf``); ``None`` otherwise."""
    return effective_party(record, effective_tag(record, pointer))


def applicable_refs(record: Mapping[str, Any], pointer: str) -> list[str]:
    """The rule references applicable at ``pointer`` (C.6.4): the scoped references whose pointer is the longest one
    equal to or a ``/``-prefix of ``pointer``; if there is none, the unscoped references. Order of the ``rule`` array.
    """
    refs = [r for r in record.get("rule", ()) if isinstance(r, str) and RULE_REF_RE.fullmatch(r)]
    best = -1
    scoped: list[str] = []
    for ref in refs:
        _, sep, scope = ref.partition("#")
        if not sep or not is_prefix(scope, pointer):
            continue
        if len(scope) > best:
            best, scoped = len(scope), [ref]
        elif len(scope) == best:
            scoped.append(ref)
    if scoped:
        return scoped
    return [r for r in refs if "#" not in r]


def rule_ids(refs: Sequence[str]) -> list[str]:
    return [rule_id_of(r) for r in refs]
