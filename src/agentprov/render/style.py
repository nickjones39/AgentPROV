"""Styles and labels of ``agentprov render`` (MN N.2.13; G.8.6; docs/architecture K.5.12).

Pure data and string functions: this module imports neither ``pydot`` nor any layer above ``ingest``, so it works
without the ``render`` extra.

**Look.** The shapes and fills are the W3C PROV notation of ``prov.dot`` that the baseline renderer
(``agentdojo_prov/visualize.py``) started from: entities are yellow ovals, activities blue boxes, agents orange houses,
and each relation keeps ``prov.dot``'s colour. On top of it:

* *evidence class* (``apv:evidenceClass``) is the border and line style: Observed solid and thick, Derived dashed,
  Inferred dotted, no class thin grey. Nodes and edges use the same mapping;
* *bundle* is the border and line colour of what the inference and assessment bundles add: purple for inference, brown
  for assessment (the core keeps the W3C colours);
* the baseline's *integrity* and *role* colours (untrusted salmon, sink dark red, endorser light blue) come from the
  assessment bundle and are drawn only when it is drawn. Integrity or role that is recorded as unknown, and a missing
  label, are never drawn as trusted or neutral (audit F-76): unknown has its own grey fill.

**Labels** (G.8.6). A node label is its local id, its PROV types, its rule id and its evidence class, each only if it
matches a trusted grammar below; a token that does not match is replaced by a fixed placeholder, never shown. Other
attribute values appear only with ``show_content``, after ``escape_untrusted`` (G.8.2), reduced to one line and
truncated, and then DOT-string escaped. No HTML-like label is ever built, and no ``URL``, ``href``, ``tooltip``,
``image`` or ``shapefile`` attribute exists in these tables.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Final

from agentprov.ingest.quote import escape_untrusted

__all__ = [
    "ANNOTATION_LINK_STYLE",
    "BUNDLE_COLOUR",
    "CONTENT_EXCLUDED",
    "DEFAULT_CONTENT_CHARS",
    "EDGE_TARGETS",
    "dot_quote",
    "edge_attrs",
    "evidence_letter",
    "integrity_overlay",
    "node_attrs",
    "node_label",
    "role_overlay",
    "token",
]

DEFAULT_CONTENT_CHARS: Final = 200
MAX_CONTENT_LINES: Final = 40

# ----------------------------------------------------------------------------------------------- trusted grammars
_ID_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.:\-]{0,199}")
_QNAME_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*:[A-Za-z0-9_][A-Za-z0-9_.\-]{0,99}")
_RULE_RE: Final = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+@[1-9][0-9]{0,5}")
_SLUG_RE: Final = re.compile(r"[A-Za-z0-9_\-]{1,100}")

#: ``apv:evidenceClass`` QName to the letter the label and the legend use.
_CLASS_LETTER: Final[Mapping[str, str]] = {"apv:Observed": "O", "apv:Derived": "D", "apv:Inferred": "I"}


def token(value: object, pattern: re.Pattern[str], fallback: str) -> str:
    """``value`` if it is a string matching the trusted grammar ``pattern``, else the fixed ``fallback``."""
    if isinstance(value, str) and pattern.fullmatch(value):
        return value
    return fallback


def id_token(value: object) -> str:
    return token(value, _ID_RE, "(id)")


def slug_token(value: object) -> str:
    return token(value, _SLUG_RE, "?")


def _qname(value: Any) -> str | None:
    """The QName of a ``{"$": q, "type": "prov:QUALIFIED_NAME"}`` value."""
    if isinstance(value, dict) and value.get("type") == "prov:QUALIFIED_NAME" and isinstance(value.get("$"), str):
        return str(value["$"])
    return None


def qnames(value: Any) -> list[str]:
    """Every QName value of a single or list-valued attribute, in document order (grammar-checked)."""
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        q = _qname(item)
        if q is not None and _QNAME_RE.fullmatch(q):
            out.append(q)
    return out


def evidence_letter(attrs: Mapping[str, Any]) -> str | None:
    """``O``, ``D`` or ``I`` from a single ``apv:evidenceClass`` value, else ``None`` (never guessed)."""
    q = _qname(attrs.get("apv:evidenceClass"))
    return _CLASS_LETTER.get(q) if q is not None else None


# ----------------------------------------------------------------------------------------------- DOT strings
def dot_quote(text: str) -> str:
    """``text`` as a double-quoted DOT string: backslash, quote and line breaks escaped (G.8.6).

    The result starts and ends with ``"`` so that ``pydot`` leaves it as it is. HTML-like labels need ``<...>``
    delimiters, not quotes, but Graphviz still decodes HTML character references (``&#x202E;``, ``&#27;``, ``&lt;``) in
    a quoted label after the string is read, which would put back the characters ``escape_untrusted`` removed (and, for
    ``&#27;``, make the SVG ill-formed). So ``&`` is written as ``&amp;`` first: Graphviz decodes that once, to a
    literal ``&`` (escaping finding F-02).
    """
    escaped = (
        text.replace("&", "&amp;").replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\n").replace("\n", "\\n")
    )
    return '"' + escaped + '"'


def display_text(value: object, max_chars: int) -> str:
    """One line of display text for a data-derived value: ``escape_untrusted``, line breaks and tabs written as escapes,
    truncated at ``max_chars`` (G.8.6). The result is display-only and is never hashed or compared."""
    text = escape_untrusted(value if isinstance(value, str) else str(value), max_chars=max_chars)
    return text.replace("\n", "<U+000A>").replace("\t", "<U+0009>")


def _plain(value: Any) -> str:
    """A scalar rendering of an attribute value (QName values by their name, containers joined)."""
    q = _qname(value)
    if q is not None:
        return q
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, list):
        return ", ".join(_plain(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return "null" if value is None else str(value)


# ----------------------------------------------------------------------------------------------- tables
#: W3C PROV notation of ``prov.dot`` (shape, fill, border) per element section.
_KIND: Final[Mapping[str, Mapping[str, str]]] = {
    "entity": {"shape": "oval", "fillcolor": "#FFFC87", "color": "#808080"},
    "activity": {"shape": "box", "fillcolor": "#9FB1FC", "color": "#0000FF"},
    "agent": {"shape": "house", "fillcolor": "#FED37F", "color": "#B08A3C"},
}
#: Evidence class to border style and pen width (nodes) and line style (edges).
_CLASS_NODE: Final[Mapping[str | None, tuple[str, str]]] = {
    "O": ("filled", "2.0"),
    "D": ("filled,dashed", "1.2"),
    "I": ("filled,dotted", "1.6"),
    None: ("filled", "0.6"),
}
_CLASS_EDGE: Final[Mapping[str | None, tuple[str, str]]] = {
    "O": ("solid", "1.8"),
    "D": ("dashed", "1.1"),
    "I": ("dotted", "1.5"),
    None: ("solid", "0.6"),
}
#: Border and edge colour contributed by a non-core bundle.
BUNDLE_COLOUR: Final[Mapping[str, str]] = {"inference": "#6A3D9A", "assessment": "#B15928"}
_OUTSIDE: Final = "#999999"  # a node declared outside the drawn bundles (a ghost)

#: ``prov.dot`` relation colours (``DOT_PROV_STYLE``): edge colour and font colour per relation.
_RELATION_COLOUR: Final[Mapping[str, tuple[str, str]]] = {
    "wasGeneratedBy": ("darkgreen", "darkgreen"),
    "used": ("red4", "red"),
    "wasAttributedTo": ("#FED37F", "#7A5A10"),
    "wasAssociatedWith": ("#FED37F", "#7A5A10"),
    "actedOnBehalfOf": ("#FED37F", "#7A5A10"),
    "wasInfluencedBy": ("grey", "grey"),
}
_DEFAULT_RELATION_COLOUR: Final = ("black", "black")

#: PROV-JSON relation to the arguments that make its edges: ``(source argument, target arguments)``. One edge is drawn
#: from the source to each target that is present (``prov.dot`` does the same for the n-ary start and end relations).
EDGE_TARGETS: Final[Mapping[str, tuple[str, tuple[str, ...]]]] = {
    "wasGeneratedBy": ("prov:entity", ("prov:activity",)),
    "used": ("prov:activity", ("prov:entity",)),
    "wasInformedBy": ("prov:informed", ("prov:informant",)),
    "wasStartedBy": ("prov:activity", ("prov:trigger", "prov:starter")),
    "wasEndedBy": ("prov:activity", ("prov:trigger", "prov:ender")),
    "wasInvalidatedBy": ("prov:entity", ("prov:activity",)),
    "wasDerivedFrom": ("prov:generatedEntity", ("prov:usedEntity",)),
    "wasAttributedTo": ("prov:entity", ("prov:agent",)),
    "wasAssociatedWith": ("prov:activity", ("prov:agent",)),
    "actedOnBehalfOf": ("prov:delegate", ("prov:responsible",)),
    "wasInfluencedBy": ("prov:influencee", ("prov:influencer",)),
    "alternateOf": ("prov:alternate1", ("prov:alternate2",)),
    "specializationOf": ("prov:specificEntity", ("prov:generalEntity",)),
    "mentionOf": ("prov:specificEntity", ("prov:generalEntity",)),
    "hadMember": ("prov:collection", ("prov:entity",)),
}

#: The link from a claim of the assessment bundle to what it is about (``prov.dot``'s annotation-link style).
ANNOTATION_LINK_STYLE: Final[Mapping[str, str]] = {
    "arrowhead": "none", "style": "dashed", "color": "gray", "fontcolor": "gray", "fontsize": "9",
}

#: Attributes the default label already shows (type, rule, class), so ``show_content`` does not repeat them.
CONTENT_EXCLUDED: Final = frozenset({"apv:evidenceClass", "apv:rule", "prov:type"})

# --- the baseline's integrity and role overlay (visualize.py:47-103), from the assessment bundle only
_INTEGRITY_RANK: Final[Mapping[str, int]] = {"trusted": 0, "unknown": 1, "untrusted": 2}
_INTEGRITY_OF: Final[Mapping[str, str]] = {
    "apv:Trusted": "trusted", "apv:Untrusted": "untrusted", "apv:IntegrityUnknown": "unknown",
}
_ROLE_NAME: Final[Mapping[str, str]] = {
    "apv:WriteSink": "write_sink", "apv:SendSink": "send_sink", "apv:ExecuteSink": "execute_sink",
    "apv:EgressRead": "egress_read", "apv:ResponseSink": "response_sink", "apv:ContentSource": "content_source",
    "apv:Endorser": "endorser", "apv:Neutral": "neutral", "apv:RoleUnknown": "unknown",
}
_SINKS: Final = frozenset({"write_sink", "send_sink", "execute_sink", "egress_read", "response_sink"})


def integrity_overlay(values: list[str]) -> str | None:
    """The weakest integrity among the recorded ``apv:integrity`` QNames (untrusted over unknown over trusted), or
    ``None`` when none is recorded. A value outside the vocabulary counts as unknown, never as trusted."""
    if not values:
        return None
    names = [_INTEGRITY_OF.get(v, "unknown") for v in values]
    return max(names, key=lambda n: _INTEGRITY_RANK[n])


def role_overlay(values: list[str]) -> str | None:
    """One role name for the recorded ``apv:securityRole`` QNames: a sink beats an endorser, which beats unknown, which
    beats the neutral roles; ``None`` when none is recorded. A QName outside the vocabulary counts as unknown."""
    if not values:
        return None
    names = {_ROLE_NAME.get(v, "unknown") for v in values}
    for rank in (
        sorted(names & _SINKS),
        ["endorser"] if "endorser" in names else [],
        ["unknown"] if "unknown" in names else [],
        sorted(names),
    ):
        if rank:
            return rank[0]
    return None


def node_attrs(
    section: str,
    cls: str | None,
    bundle_kind: str | None,
    *,
    integrity: str | None = None,
    role: str | None = None,
) -> dict[str, str]:
    """DOT attributes (values unquoted, all from this module's tables) of one node.

    ``bundle_kind`` is ``core``, ``inference``, ``assessment`` or ``None`` for a node declared outside the drawn bundles.
    """
    base = _KIND.get(section, _KIND["entity"])
    style, penwidth = _CLASS_NODE.get(cls, _CLASS_NODE[None])
    attrs = {
        "shape": base["shape"], "style": style, "penwidth": penwidth,
        "fillcolor": base["fillcolor"], "color": base["color"], "fontname": "Helvetica", "fontsize": "10",
    }  # fmt: skip
    if bundle_kind is not None and bundle_kind in BUNDLE_COLOUR:
        attrs["color"] = BUNDLE_COLOUR[bundle_kind]
    elif bundle_kind is None:
        attrs["color"] = _OUTSIDE
        attrs["fillcolor"] = "#F2F2F2"
        attrs["style"] = "filled,dashed"
    if integrity == "untrusted":
        attrs["fillcolor"], attrs["color"] = "#FFAAAA", "#CC4444"
    elif integrity == "unknown":
        attrs["fillcolor"], attrs["color"] = "#D9D9D9", "#555555"
    if role in _SINKS:
        attrs["fillcolor"], attrs["color"], attrs["fontcolor"] = "#B02E2E", "#6E1414", "white"
    elif role == "endorser":
        attrs["fillcolor"], attrs["color"] = "#B8CCF8", "#2244AA"
    elif role == "unknown":
        attrs["fillcolor"], attrs["color"] = "#D9D9D9", "#555555"
    return attrs


def edge_attrs(relation: str, cls: str | None, bundle_kind: str | None) -> dict[str, str]:
    """DOT attributes of one relation edge: ``prov.dot`` colour, evidence-class line style, bundle colour."""
    colour, font = _RELATION_COLOUR.get(relation, _DEFAULT_RELATION_COLOUR)
    style, penwidth = _CLASS_EDGE.get(cls, _CLASS_EDGE[None])
    if bundle_kind is not None and bundle_kind in BUNDLE_COLOUR:
        colour = font = BUNDLE_COLOUR[bundle_kind]
    return {
        "color": colour, "fontcolor": font, "style": style, "penwidth": penwidth,
        "fontname": "Helvetica", "fontsize": "9",
    }  # fmt: skip


def node_label(
    key: str,
    section: str,
    attrs: Mapping[str, Any],
    *,
    cls: str | None,
    tags: tuple[str, ...] = (),
    show_content: bool = False,
    content_chars: int = DEFAULT_CONTENT_CHARS,
) -> str:
    """The text of a node label (not yet DOT-quoted): lines separated by ``\\n``.

    Without ``show_content`` every character of the label comes from a trusted grammar or from this module: the local
    id, the PROV type QNames and the rule id are grammar-checked tokens, the class is a letter, and ``tags`` are fixed
    words chosen by the caller. With ``show_content`` the other attributes follow as ``name: value`` lines.
    """
    lines = [id_token(key)]
    types = [t for t in qnames(attrs.get("prov:type")) if t not in ("prov:Bundle",)]
    if types:
        lines.append("«" + ", ".join(types) + "»")
    rule = attrs.get("apv:rule")
    tail = []
    if isinstance(rule, str):
        tail.append(token(rule, _RULE_RE, "(rule)"))
    if cls is not None:
        tail.append(cls)
    if tail:
        lines.append(" · ".join(tail))
    lines.extend(tags)
    if show_content:
        shown = 0
        for name in sorted(attrs):
            if name in CONTENT_EXCLUDED or not isinstance(name, str):
                continue
            if shown >= MAX_CONTENT_LINES:
                lines.append("… (more attributes not shown)")
                break
            shown += 1
            lines.append(f"{display_text(name, 80)}: {display_text(_plain(attrs[name]), content_chars)}")
    return "\n".join(lines)
