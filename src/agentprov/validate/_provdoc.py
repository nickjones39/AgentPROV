"""A tolerant, read-only index over one bundled PROV-JSON document (shared by the tier-4 validators; not a public API).

The structure checks (:mod:`agentprov.validate.prov_structure`) report every malformation; this index only skips what it
cannot read, so the other validators never raise on hostile input (totality, K.10 / baseline V1).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

__all__ = [
    "ASSESS_RE",
    "ELEMENT_SECTIONS",
    "RELATION_ARGS",
    "REQUIRED_ARGS",
    "UNIDENTIFIED",
    "BundleView",
    "ProvView",
    "St",
    "as_list",
    "class_letter",
    "qname_value",
    "qname_values",
]

ELEMENT_SECTIONS: Final = ("entity", "activity", "agent")
#: PROV-JSON relation sections and their argument keys in PROV argument order.
RELATION_ARGS: Final[Mapping[str, tuple[str, ...]]] = {
    "wasGeneratedBy": ("prov:entity", "prov:activity", "prov:time"),
    "used": ("prov:activity", "prov:entity", "prov:time"),
    "wasInformedBy": ("prov:informed", "prov:informant"),
    "wasStartedBy": ("prov:activity", "prov:trigger", "prov:starter", "prov:time"),
    "wasEndedBy": ("prov:activity", "prov:trigger", "prov:ender", "prov:time"),
    "wasInvalidatedBy": ("prov:entity", "prov:activity", "prov:time"),
    "wasDerivedFrom": ("prov:generatedEntity", "prov:usedEntity", "prov:activity", "prov:generation", "prov:usage"),
    "wasAttributedTo": ("prov:entity", "prov:agent"),
    "wasAssociatedWith": ("prov:activity", "prov:agent", "prov:plan"),
    "actedOnBehalfOf": ("prov:delegate", "prov:responsible", "prov:activity"),
    "wasInfluencedBy": ("prov:influencee", "prov:influencer"),
    "alternateOf": ("prov:alternate1", "prov:alternate2"),
    "specializationOf": ("prov:specificEntity", "prov:generalEntity"),
    "mentionOf": ("prov:specificEntity", "prov:generalEntity", "prov:bundle"),
    "hadMember": ("prov:collection", "prov:entity"),
}
#: Arguments PROV-DM requires per relation (the others are optional).
REQUIRED_ARGS: Final[Mapping[str, tuple[str, ...]]] = {
    "wasGeneratedBy": ("prov:entity",),
    "used": ("prov:activity",),
    "wasInformedBy": ("prov:informed", "prov:informant"),
    "wasStartedBy": ("prov:activity",),
    "wasEndedBy": ("prov:activity",),
    "wasInvalidatedBy": ("prov:entity",),
    "wasDerivedFrom": ("prov:generatedEntity", "prov:usedEntity"),
    "wasAttributedTo": ("prov:entity", "prov:agent"),
    "wasAssociatedWith": ("prov:activity",),
    "actedOnBehalfOf": ("prov:delegate", "prov:responsible"),
    "wasInfluencedBy": ("prov:influencee", "prov:influencer"),
    "alternateOf": ("prov:alternate1", "prov:alternate2"),
    "specializationOf": ("prov:specificEntity", "prov:generalEntity"),
    "mentionOf": ("prov:specificEntity", "prov:generalEntity", "prov:bundle"),
    "hadMember": ("prov:collection", "prov:entity"),
}
#: Relations without an identifier (E.5.1 item 3).
UNIDENTIFIED: Final = frozenset({"specializationOf", "alternateOf", "hadMember", "mentionOf"})
CORE_RE: Final = re.compile(r"xd:bundle\.core\.([a-z2-7]{26})")
INF_RE: Final = re.compile(r"xd:bundle\.inf\.([A-Za-z0-9_\-]+)\.([a-z2-7]{26})")
ASSESS_RE: Final = re.compile(r"xd:bundle\.assess\.([a-z0-9_\-]+)\.([a-z2-7]{26})")
CLASS_LETTER: Final[Mapping[str, str]] = {"apv:Observed": "O", "apv:Derived": "D", "apv:Inferred": "I"}
RANK: Final[Mapping[str, int]] = {"I": 0, "D": 1, "O": 2}


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else [value]


def qname_value(value: Any) -> str | None:
    """The QName of a ``{"$": q, "type": "prov:QUALIFIED_NAME"}`` value, else ``None``."""
    if isinstance(value, dict) and value.get("type") == "prov:QUALIFIED_NAME" and isinstance(value.get("$"), str):
        return str(value["$"])
    return None


def qname_values(value: Any) -> list[str]:
    return [q for v in as_list(value) if (q := qname_value(v)) is not None]


def class_letter(attrs: Mapping[str, Any]) -> str | None:
    """``O``/``D``/``I`` from a single ``apv:evidenceClass`` QName value, else ``None``."""
    value = attrs.get("apv:evidenceClass")
    q = qname_value(value)
    return CLASS_LETTER.get(q) if q is not None else None


@dataclass(eq=False, slots=True)
class St:
    """One element or relation of the document: its key, section, containing bundle (``None`` = top level) and body."""

    key: str
    section: str
    bundle: str | None
    attrs: dict[str, Any]

    @property
    def is_element(self) -> bool:
        return self.section in ELEMENT_SECTIONS

    @property
    def is_identified(self) -> bool:
        return not self.key.startswith("_:")

    @property
    def rule(self) -> str | None:
        r = self.attrs.get("apv:rule")
        return r if isinstance(r, str) else None

    @property
    def cls(self) -> str | None:
        return class_letter(self.attrs)

    @property
    def types(self) -> set[str]:
        return set(qname_values(self.attrs.get("prov:type")))

    def arg(self, key: str) -> str | None:
        v = self.attrs.get(key)
        return v if isinstance(v, str) else None

    def args(self) -> dict[str, str]:
        """The present relation arguments (string-valued ``prov:`` argument keys of the section)."""
        return {k: v for k in RELATION_ARGS.get(self.section, ()) if k != "prov:time" and isinstance(v := self.attrs.get(k), str)}

    @property
    def where(self) -> str:
        return f"{self.bundle or 'top'}:{self.section}:{self.key}"


@dataclass(slots=True)
class BundleView:
    iri: str
    kind: Literal["core", "inference", "assessment", "unknown"]
    methods: frozenset[str] | None  # None when the top-level bundle entity gives none (inference), assessment, unknown
    statements: list[St] = field(default_factory=list)
    profile: str | None = None  # assessment bundles: the top-level entity's apv:profile


@dataclass(slots=True)
class ProvView:
    doc: Mapping[str, Any]
    prefixes: dict[str, str]
    top: list[St]
    bundles: dict[str, BundleView]
    by_key: dict[str, St]  # identified keys (elements and relations) across every container; first occurrence wins
    elements: dict[str, St]  # bundle-declared element keys (first occurrence)
    element_bundles: dict[str, list[str]]
    top_elements: dict[str, St]

    @classmethod
    def parse(cls, doc: Any) -> ProvView:
        if not isinstance(doc, dict):
            doc = {}
        raw_prefix = doc.get("prefix")
        prefixes = {str(k): str(v) for k, v in raw_prefix.items()} if isinstance(raw_prefix, dict) else {}
        top = list(_statements(doc, None))
        top_elements = {s.key: s for s in top if s.is_element}
        bundles: dict[str, BundleView] = {}
        raw_bundles = doc.get("bundle")
        if isinstance(raw_bundles, dict):
            for iri in sorted(raw_bundles):
                body = raw_bundles[iri]
                entity = top_elements.get(iri)
                types = entity.types if entity is not None else set()
                if CORE_RE.fullmatch(iri) or "apv:CoreBundle" in types:
                    kind: Literal["core", "inference", "assessment", "unknown"] = "core"
                elif INF_RE.fullmatch(iri) or "apv:InferenceBundle" in types:
                    kind = "inference"
                elif ASSESS_RE.fullmatch(iri) or "apv:AssessmentBundle" in types:
                    kind = "assessment"
                else:
                    kind = "unknown"
                methods: frozenset[str] | None = frozenset() if kind == "core" else None
                if kind == "inference" and entity is not None:
                    found = [m for m in as_list(entity.attrs.get("apv:method")) if isinstance(m, str)]
                    methods = frozenset(found) if found else None
                profile = entity.attrs.get("apv:profile") if entity is not None else None
                bundles[iri] = BundleView(iri, kind, methods, list(_statements(body, iri)) if isinstance(body, dict) else [],
                                          profile if isinstance(profile, str) else None)
        by_key: dict[str, St] = {}
        elements: dict[str, St] = {}
        element_bundles: dict[str, list[str]] = {}
        for s in top:
            if s.is_identified:
                by_key.setdefault(s.key, s)
        for b in bundles.values():
            for s in b.statements:
                if s.is_identified:
                    by_key.setdefault(s.key, s)
                if s.is_element:
                    elements.setdefault(s.key, s)
                    element_bundles.setdefault(s.key, []).append(b.iri)
        return cls(doc, prefixes, top, bundles, by_key, elements, element_bundles, top_elements)

    # ------------------------------------------------------------------------------------------ queries
    @property
    def core(self) -> BundleView | None:
        cores = [b for b in self.bundles.values() if b.kind == "core"]
        return cores[0] if len(cores) == 1 else None

    def inference(self) -> list[BundleView]:
        return [b for b in self.bundles.values() if b.kind == "inference"]

    def assessment(self) -> list[BundleView]:
        return [b for b in self.bundles.values() if b.kind == "assessment"]

    def methods(self, bundle: str | None) -> frozenset[str] | None:
        """The method set of a bundle (core: empty)."""
        if bundle is None:
            return None
        b = self.bundles.get(bundle)
        return b.methods if b is not None else None

    def visible(self, bundle: str) -> list[BundleView]:
        """The application view of ``bundle``: the core, the bundle and every inference bundle whose method set is a
        proper subset of its own (E.1.6 item 1; EF E.1.4 "PROV checks"). An assessment bundle sees the core and every
        inference bundle, since it mentions their nodes and cites their statements (E.7.2, E.7.3)."""
        own = self.methods(bundle)
        mine = self.bundles.get(bundle)
        assessing = mine is not None and mine.kind == "assessment"
        out: list[BundleView] = []
        for b in self.bundles.values():
            if b.iri == bundle or b.kind == "core" or (assessing and b.kind == "inference"):
                out.append(b)
            elif own is not None and b.methods is not None and b.methods < own:
                out.append(b)
        return out

    def scope(self, methods: frozenset[str]) -> list[BundleView]:
        """``S(M)``: the core and every inference bundle whose method set is a subset of ``methods``."""
        return [b for b in self.bundles.values()
                if b.kind == "core" or (b.methods is not None and b.methods <= methods)]

    def bundle_statements(self) -> Iterator[St]:
        for b in self.bundles.values():
            yield from b.statements

    def all_statements(self) -> Iterator[St]:
        yield from self.top
        yield from self.bundle_statements()

    def element_kind(self, key: str) -> str | None:
        s = self.elements.get(key) or self.top_elements.get(key)
        return s.section if s is not None else None


def _statements(container: Mapping[str, Any], bundle: str | None) -> Iterator[St]:
    for section, items in container.items():
        if section in ("prefix", "bundle") or not isinstance(items, dict):
            continue
        if section not in ELEMENT_SECTIONS and section not in RELATION_ARGS:
            continue
        for key, body in items.items():
            yield St(str(key), section, bundle, body if isinstance(body, dict) else {})
