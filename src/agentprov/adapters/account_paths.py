"""Account-path shapes in artefact labels (regeneration-batch item 108; the D-510 census safeguard, user-approved
2026-10-14, fail closed).

A label (an origin path inside a pinned tree or archive) can name a workstation or cluster account in a directory:
slashed (``home/<x>/``, ``Users/<x>/``, ``scratch/<x>/``, ``mfs1/u/<x>/``) or munged into one segment
(``_home_<x>_``, ``_Users_<x>_``, ``_scratch_<x>_``, ``_ceph_…_students_<x>_``, as EnvironmentOptim's
``_ceph_ssd_students_<x>_qwen3_5``). :func:`account_shapes` reports where, by shape and segment index only, never the
value. The importer holds a selected file whose label has such a shape unless a redaction rule of the profile covers
that segment (:func:`covered`); a profile exempts a verified false positive by glob (``[import] account_path_exempt``).
Pure, stdlib only.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

__all__ = ["AccountShape", "RedactCover", "account_shapes", "covered", "redaction_patterns"]

#: Slashed forms: a parent directory name followed by an account segment (the segment after it is the account).
_SLASHED: Final = (("home", 1), ("Users", 1), ("scratch", 1), ("mfs1/u", 2))
#: Munged forms: one segment that spells a home-like parent and an account between underscores.
_MUNGED: Final = (
    # a munged absolute path keeps the root's separator as a leading underscore: `/home/x/` becomes `_home_x_`
    ("munged_home", re.compile(r"(?:^|[^A-Za-z0-9])_(?:home|Users|scratch)_(?P<name>[A-Za-z0-9.-]+)_")),
    ("munged_cluster", re.compile(r"_ceph_(?:[a-z0-9]+_)*?(?:students|users|home)_(?P<name>[A-Za-z0-9.-]+)_")),
)
#: AgentDojo's fictional sandbox user (benchmark content); never an operator's account.
_FICTIONAL: Final = frozenset({"user"})


@dataclass(frozen=True, slots=True)
class AccountShape:
    """One account-bearing place in a label: the shape and the index of the segment that holds the account. ``name`` is
    the account token itself, kept in memory for :func:`covered` only: never in ``repr``, a report or a register row."""

    shape: str
    segment: int
    name: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RedactCover:
    """A declared redaction rule as the lint reads it: its pattern, and its ``labels`` allowlist when it has one (the
    dtap family's D-607 grammar: a match whose ``{span12}`` label is not listed is left unredacted)."""

    pattern: re.Pattern[str]
    labels: frozenset[str] | None = None


def account_shapes(label: str) -> list[AccountShape]:
    """The account-path shapes of ``label`` (``/``-separated), by shape and segment index."""
    segs = label.split("/")
    out: list[AccountShape] = []
    for parent, width in _SLASHED:
        parts = parent.split("/")
        for i in range(len(segs) - width):
            if segs[i : i + len(parts)] == parts and segs[i + width] not in _FICTIONAL:
                out.append(AccountShape(f"slashed_{parts[0].lower()}", i + width, segs[i + width]))
    for i, seg in enumerate(segs):
        for name, pattern in _MUNGED:
            found = pattern.search(seg)
            if found:
                out.append(AccountShape(name, i, found.group("name")))
                break
    return out


def _span_label(span: str, salt: str) -> str:
    """D-476's ``{span12}``: SHA-256 over ``<salt> NUL <span>``, first 12 hex digits (the families' redaction labels)."""
    return hashlib.sha256(f"{salt}\0{span}".encode("utf-8", "surrogatepass")).hexdigest()[:12]


def covered(label: str, shape: AccountShape, covers: Iterable[RedactCover | re.Pattern[str]], *, salt: str = "") -> bool:
    """Whether a redaction rule of the profile redacts the account of ``shape`` in its segment of ``label``: one of the
    rule's matches there includes the account token (its ``span`` group, else the whole match), and, for a rule with a
    ``labels`` allowlist, that span's label (salted with ``salt``, the profile id) is listed (pre-round review #19: a
    match elsewhere in the segment, or an unlisted token, redacts nothing)."""
    seg = label.split("/")[shape.segment]
    for cover in covers:
        rule = cover if isinstance(cover, RedactCover) else RedactCover(cover)
        for found in rule.pattern.finditer(seg):
            span = found.group("span") if "span" in rule.pattern.groupindex else found.group(0)
            if span is None or (shape.name and shape.name not in span):
                continue
            if rule.labels is None or _span_label(span, salt) in rule.labels:
                return True
    return False


def redaction_patterns(rules: Sequence[object]) -> list[RedactCover]:
    """Every declared redaction rule (any family's ``[[family.<f>.redact]]`` table) as a :class:`RedactCover`."""
    out = []
    for rule in rules:
        pattern = rule.get("pattern") if isinstance(rule, Mapping) else getattr(rule, "pattern", None)
        raw = rule.get("labels") if isinstance(rule, Mapping) else getattr(rule, "labels", None)
        labels = frozenset(str(x) for x in raw) if isinstance(raw, (list, tuple, set, frozenset)) else None
        if isinstance(pattern, str):
            out.append(RedactCover(re.compile(pattern), labels))
        elif isinstance(pattern, re.Pattern):
            out.append(RedactCover(pattern, labels))
    return out
