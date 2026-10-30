"""Evidence classes and the effective tag of a field (C.6).

``O`` (observed) > ``D`` (derived) > ``I`` (inferred). A record's ``ev`` is its existence class and the default
for every field it asserts; ``evf`` overrides it per JSON Pointer with **longest-prefix** resolution on ``/``
boundaries (C.6.3, normative). A tag is ``O``, ``D``, ``I`` or ``O:<party>``; a bare ``O`` takes the record's
``by``. Nothing here can raise a class: :func:`weakest` is the only combinator (C.6.5 rule 5).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Final

from agentprov.aer.types import EVIDENCE_CLASSES, PARTIES

__all__ = [
    "ENVELOPE_UNTAGGED",
    "HEADER_META",
    "TAG_RE",
    "asserted_fields",
    "effective_party",
    "effective_tag",
    "effective_tags",
    "is_prefix",
    "is_valid_tag",
    "parse_tag",
    "tag_class",
    "weakest",
]

TAG_RE: Final = re.compile(r"(?:[ODI]|O:(?:capture|source|provider|benchmark|config|replay))")
#: Envelope members that carry no evidence tag. ``after`` is tagged (``evf {"/after": ...}``), ``ext`` is
#: tagged only through ``evf`` pointers below ``/ext`` (C.10 item 6).
ENVELOPE_UNTAGGED: Final = frozenset({"k", "id", "ev", "by", "evf", "rule", "src", "unk", "ext"})
#: Header members that are bookkeeping about the record, not assertions about the execution (C.3.1 "meta").
HEADER_META: Final = frozenset(
    {
        "aer",
        "ex",
        "mode",
        "unit",
        "source_key",
        "artifacts",
        "adapter",
        "dialect",
        "profile",
        "rules",
        "ns",
        "canon",
        "hash",
        "capture",
        "related",
    }
)
_RANK: Final = {cls: i for i, cls in enumerate(EVIDENCE_CLASSES)}  # O=0 strongest


def is_valid_tag(tag: object) -> bool:
    return isinstance(tag, str) and TAG_RE.fullmatch(tag) is not None


def parse_tag(tag: str) -> tuple[str, str | None]:
    """``("O", "provider")`` for ``"O:provider"``, ``("D", None)`` for ``"D"``."""
    if not is_valid_tag(tag):
        raise ValueError("not an evidence tag")
    cls, _, party = tag.partition(":")
    return cls, (party or None)


def tag_class(tag: str) -> str:
    """The class letter of a tag: ``O:<party>`` collapses to ``O``."""
    return parse_tag(tag)[0]


def is_prefix(prefix: str, pointer: str) -> bool:
    """True iff ``prefix`` equals ``pointer`` or is a proper prefix of it on a ``/`` boundary (root included)."""
    return pointer == prefix or pointer.startswith(prefix + "/")


def weakest(*tags: str) -> str:
    """The weakest class among ``tags`` in the order ``O`` > ``D`` > ``I`` (C.6.5).

    ``O:<party>`` counts as ``O`` and the result is always a bare class letter. At least one tag is required;
    nothing can raise a class, so ``weakest("O", "D")`` is ``"D"`` and ``weakest("D", "I")`` is ``"I"``.
    """
    if not tags:
        raise ValueError("weakest() needs at least one tag")
    return max((tag_class(t) for t in tags), key=_RANK.__getitem__)


def effective_tag(record: Mapping[str, object], pointer: str) -> str:
    """The effective tag at ``pointer``: the ``evf`` entry with the longest key equal to or a proper ``/``-prefix
    of ``pointer``; else the record's ``ev`` (C.6.3). ``ValueError`` for a record without ``ev`` (the seal)."""
    evf = record.get("evf")
    best: str | None = None
    if isinstance(evf, Mapping):
        best_len = -1
        for key, tag in evf.items():
            if isinstance(key, str) and isinstance(tag, str) and is_prefix(key, pointer) and len(key) > best_len:
                best, best_len = tag, len(key)
    if best is not None:
        return best
    ev = record.get("ev")
    if not isinstance(ev, str):
        raise ValueError("record has no existence class")
    return ev


def effective_party(record: Mapping[str, object], tag: str) -> str | None:
    """The attesting party of an observed ``tag``: its own party for ``O:<party>``, else the record's ``by``;
    ``None`` for ``D``/``I`` or when a bare ``O`` has no valid ``by``."""
    cls, party = parse_tag(tag)
    if cls != "O":
        return None
    if party is not None:
        return party
    by = record.get("by")
    return by if isinstance(by, str) and by in PARTIES else None


def asserted_fields(record: Mapping[str, object]) -> list[str]:
    """Top-level members of ``record`` that carry an evidence tag (document order of the mapping).

    The header's meta members and the untagged envelope members are excluded; ``after`` is included; the seal
    asserts nothing.
    """
    kind = record.get("k")
    if kind == "seal":
        return []
    skip = ENVELOPE_UNTAGGED | (HEADER_META if kind == "execution" else frozenset())
    return [name for name in record if name not in skip]


def effective_tags(record: Mapping[str, object]) -> set[str]:
    """Every effective tag present in the record: one per asserted top-level member, plus all ``evf`` values."""
    tags = {effective_tag(record, "/" + name) for name in asserted_fields(record)}
    evf = record.get("evf")
    if isinstance(evf, Mapping):
        tags.update(t for t in evf.values() if isinstance(t, str))
    return tags


def classes_of(tags: Iterable[str]) -> set[str]:
    return {tag_class(t) for t in tags if is_valid_tag(t)}
