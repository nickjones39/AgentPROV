"""Which class-D rules a profile may cite at D: code verification and ``_unverified`` twins (D.5.4 "Citation of D rules",
D-24, D-27 c6).

A D-class rule rests on the behaviour of the code that wrote the source, and the code that behaviour was read from is
the rule's ``code`` list in its catalogue (40-hex commits). A profile states the commits whose code produced its records
(``verified_code``, each entry with an optional selector). A D rule is cited at D only when one of its ``code`` commits
is among them; otherwise the mapper cites the rule's I twin ``<id>_unverified@<n>`` (same version), which moves the
statements the rule justifies into the inference bundles. A rule with no ``code`` entry (its evidence is a document)
is never verified this way, so it always resolves to its twin (D-27 c6). The choice is a function of the profile, its
selector facets and the catalogue version, fixed at map time, never of the data's content (D.5.2 validation item 8).

Fail closed: a D rule that resolves to a twin the catalogue does not declare raises
:class:`~agentprov.errors.RuleNotDeclared` (package data is wrong; the import stops), unless the family lists the rule
among its ``independent`` rules: rules whose reading does not depend on the code that wrote the source (a digest
comparison against a pinned text, a released correction applied to the logged messages). Rules of other namespaces
(``aer`` and the like) pass through.

:func:`weaken_to_rule_class` applies C.6.5 rule 1 to a finished record: a field justified by an I-class rule is at
most I. It never raises a class, so a record whose rules all resolved to D is unchanged.
"""

from __future__ import annotations

import fnmatch
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.aer.evidence import asserted_fields, effective_tag, is_prefix, tag_class
from agentprov.aer.locators import pointer_exists
from agentprov.aer.rules import CATALOGUE_HOMES, load_catalogue
from agentprov.errors import ProfileError, RuleNotDeclared
from agentprov.io.canonical import sha256_hex

__all__ = ["TWIN_SUFFIX", "Citations", "VerifiedCode", "code_commits", "parse_verified_code", "reading_of", "rule_class",
           "weaken_to_rule_class"]

#: The name suffix of a D rule's I twin (D.5.4).
TWIN_SUFFIX: Final = "_unverified"


@cache
def code_commits(namespace: str) -> Mapping[str, frozenset[str]]:
    """The commits of each rule's ``code`` list in the shipped catalogue ``namespace``, by rule id ``<id>@<n>``.

    Read from the same package resource as :func:`agentprov.aer.rules.load_catalogue` (whose parsed entries do not keep
    ``code``); the bytes must be the loaded catalogue's, so the two never describe different versions."""
    home = CATALOGUE_HOMES.get(namespace) or f"agentprov.adapters.{namespace}"
    parts = (*home.split(".")[1:], "rules", f"{namespace}.rules.toml")  # package data under agentprov/
    data = resources.files("agentprov").joinpath(*parts).read_bytes()
    if sha256_hex(data) != load_catalogue(namespace).digest:
        raise ProfileError(f"catalogue {namespace!r}: the code list was read from other bytes than the loaded catalogue")
    doc = tomllib.loads(data.decode("utf-8"))
    return {f"{r['id']}@{r['version']}": frozenset(str(c["commit"]) for c in r.get("code", ())) for r in doc.get("rule", ())}


@dataclass(frozen=True, slots=True)
class VerifiedCode:
    """One ``verified_code`` entry of a profile: a commit and the facets it applies to (empty: every record)."""

    commit: str
    applies: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def matches(self, facets: Mapping[str, str | None]) -> bool:
        """``applies`` keys are ANDed, the globs of one key ORed (``fnmatch``), as for quirk selectors (D.4.1)."""
        for key, globs in self.applies.items():
            value = facets.get(key)
            if value is None or not any(fnmatch.fnmatchcase(value, g) for g in globs):
                return False
        return True


def parse_verified_code(entries: Iterable[Any], where: str) -> tuple[VerifiedCode, ...]:
    """The ``verified_code`` entries of a profile (each ``{commit, applies?, note?}``); ``ProfileError`` if malformed.

    Fail closed (CD-2): an unknown entry key or a selector value that is not an array of non-empty strings is refused,
    never read as a wider selector (a string's ``*`` or an ignored, misspelt ``applies`` would match every record)."""
    out: list[VerifiedCode] = []
    for entry in entries:
        commit = entry.get("commit") if isinstance(entry, Mapping) else None
        if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ProfileError(f"{where}: a verified_code entry names a full 40-hex commit")
        if extra := set(entry) - {"commit", "applies", "note"}:
            raise ProfileError(f"{where}: verified_code entry has unknown keys {sorted(map(str, extra))}")
        if not isinstance(entry.get("note", ""), str):
            raise ProfileError(f"{where}: verified_code note is a string")
        applies = entry.get("applies", {})
        if not isinstance(applies, Mapping):
            raise ProfileError(f"{where}: verified_code applies is a selector table")
        for key, globs in applies.items():
            if (not isinstance(key, str) or not isinstance(globs, list | tuple) or not globs
                    or not all(isinstance(g, str) and g for g in globs)):
                raise ProfileError(f"{where}: verified_code applies maps each facet to an array of non-empty strings")
        out.append(VerifiedCode(commit, {k: tuple(v) for k, v in applies.items()}))
    return tuple(out)


class Citations:
    """The rule a mapper cites for a D-class rule under one profile and one record's facets (module docstring)."""

    def __init__(self, verified: Iterable[VerifiedCode], facets: Mapping[str, str | None], *, namespaces: Iterable[str],
                 independent: Iterable[str] = ()) -> None:
        self.verified = frozenset(v.commit for v in verified if v.matches(facets))
        self.namespaces = frozenset(namespaces)
        self.independent = frozenset(independent)
        self._resolved: dict[str, str] = {}

    def cite(self, rule_id: str) -> str:
        """``rule_id`` (``<id>@<n>``, no pointer) when it is class I, outside the family's namespaces, independent of the
        producing code, or verified for this record; else its twin. :class:`RuleNotDeclared` when the twin is missing."""
        hit = self._resolved.get(rule_id)
        if hit is None:
            hit = self._resolved[rule_id] = self._resolve(rule_id)
        return hit

    def cls(self, rule_id: str) -> str:
        """The class (``D`` or ``I``) of the rule :meth:`cite` returns for ``rule_id``."""
        return rule_class(self.cite(rule_id))

    def _resolve(self, rule_id: str) -> str:
        namespace = rule_id.split(".", 1)[0]
        if namespace not in self.namespaces or rule_id in self.independent or rule_class(rule_id) != "D":
            return rule_id
        if code_commits(namespace).get(rule_id, frozenset()) & self.verified:
            return rule_id
        name, _, version = rule_id.partition("@")
        twin = f"{name}{TWIN_SUFFIX}@{version}"
        entry = load_catalogue(namespace).get(twin)
        if entry is None or not entry.citable or entry.cls != "I":
            raise RuleNotDeclared(f"{rule_id} is cited for code its catalogue entry does not list, and the {namespace!r} "
                                  f"catalogue declares no class-I twin {twin} (D.5.4)")
        return twin


def reading_of(ref: str) -> str:
    """The D rule id whose reading ``ref`` cites: ``<id>@<n>`` for ``<id>@<n>`` and for its twin ``<id>_unverified@<n>``,
    the pointer dropped. Counts of a rule's applications (the profile census) count both (D.5.4)."""
    name, _, version = ref.partition("#")[0].partition("@")
    return f"{name.removesuffix(TWIN_SUFFIX)}@{version}"


@cache
def rule_class(rule_id: str) -> str:
    """The class of a shipped rule; ``D`` when undeclared (the mapping context refuses an undeclared rule anyway)."""
    entry = load_catalogue(rule_id.split(".", 1)[0]).get(rule_id)
    return entry.cls if entry is not None else "D"


def weaken_to_rule_class(record: dict[str, Any]) -> None:
    """C.6.5 rule 1 on one finished record, in place: no field is stronger than an I-class rule that justifies it.

    A record whose existence is ``D`` and that cites an I rule unscoped becomes ``I``; every asserted field or ``evf``
    pointer, or scoped rule pointer holding a value, still tagged ``D`` whose applicable rules (the longest-prefix scoped rules, else the unscoped ones; the AER
    validator's AER-V14 reading) include an I rule gets ``evf`` ``I``. A causal ``after`` edge rests on the link it follows
    (C.6.5 rule 1): an output's on its ``generated_by`` ("m3 after dc0" is I when ``m3.generated_by`` is), an execution's
    on its ``call`` (D-87: a positional or twinned call link makes the execution's causal ``after`` I), so it is weakened
    with it. ``O`` tags are untouched (an observation is not justified by a rule). Nothing is raised."""
    refs = [r for r in record.get("rule", ()) if isinstance(r, str)]
    if not refs or all(rule_class(r.partition("#")[0]) == "D" for r in refs):
        return
    scoped = [(r.partition("#")[0], r.partition("#")[2]) for r in refs if "#" in r]
    unscoped = [r for r in refs if "#" not in r]
    if record.get("ev") == "D" and any(rule_class(r) == "I" for r in unscoped):
        record["ev"] = "I"
    evf: dict[str, str] = dict(record.get("evf") or {})
    # a scoped rule's own pointer, when a value is there, as AER-V14 reads it (pre-round review F-1, D-224)
    pointers = ["/" + name for name in asserted_fields(record)] + list(evf) + [
        p for _r, p in scoped if pointer_exists(record, p)]
    for pointer in dict.fromkeys(pointers):
        if tag_class(effective_tag({**record, "evf": evf}, pointer)) != "D":
            continue
        matching = [(r, p) for r, p in scoped if is_prefix(p, pointer)]
        if matching:
            longest = max(len(p) for _r, p in matching)
            applicable = [r for r, p in matching if len(p) == longest]
        else:
            applicable = unscoped
        if any(rule_class(r) == "I" for r in applicable):
            evf[pointer] = "I"
    after = record.get("after")
    causal = isinstance(after, list) and any(isinstance(a, dict) and a.get("b") == "causal" for a in after)
    view = {**record, "evf": evf}
    link = "/generated_by" if "generated_by" in record else "/call" if "call" in record else None
    if causal and link is not None and tag_class(effective_tag(view, link)) == "I" \
            and tag_class(effective_tag(view, "/after")) == "D":
        evf["/after"] = "I"
    if evf:
        record["evf"] = evf
