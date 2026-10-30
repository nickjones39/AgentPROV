"""Canonical PROV-O TriG with the unqualified layer, produced on demand (EF E.5.4; HL H.8.4(1); ``derive --trig DIR``).

TriG is never stored or hashed in a corpus (AD-10 row 3). :func:`to_trig` turns one canonical bundled PROV-JSON document
into the E.5.4 form:

1. **Triples.** The ``prov``-library PROV-O image of the document, read through the N-Quads encode and parse of
   :mod:`agentprov.prov.serialise.nquads` that the tier-4 round trip checks (D-131), plus the *unqualified layer*:
   one triple per identified relation with the most specific PROV-O property (``prov:used``,
   ``prov:wasGeneratedBy``, ...; ``wasDerivedFrom`` typed ``prov:Revision``/``prov:Quotation``/``prov:PrimarySource``
   gives ``prov:wasRevisionOf``/``prov:wasQuotedFrom``/``prov:hadPrimarySource``). A layer triple goes into the graph
   of its statement: the bundle's named graph, or the default graph for top-level statements.
2. **Graphs.** The default graph first, as ``{ ... }``, then one ``<bundle IRI> { ... }`` per bundle, ordered by IRI.
3. **Writer.** AgentPROV's own, not rdflib's serialiser: no ``@prefix`` block, full IRIs, one triple per line in
   N-Triples term syntax, lines ordered by code point, canonical N-Triples escaping (RDFC-1.0), UTF-8, LF, final newline.
4. **No blank nodes.** A blank node anywhere raises :class:`TrigError`; without them, sorted lines are a canonical form.

The output is deterministic for the same input and the same ``prov`` and ``rdflib`` versions
(:func:`serialiser_versions`), which callers report with the digest (E.5.4(5)). Pure: nothing is read or written here.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping
from importlib import metadata
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.prov.serialise import nquads

__all__ = ["TrigError", "serialiser_versions", "to_trig"]

PROV_NS: Final = "http://www.w3.org/ns/prov#"
XSD_STRING: Final = "http://www.w3.org/2001/XMLSchema#string"
DEFAULT_GRAPH: Final = "urn:x-rdflib:default"


class TrigError(AgentProvError):
    """The document cannot be written as canonical TriG (unreadable, or the library produced a blank node)."""

    code = "prov.trig.invalid"
    exit_code = 1


def serialiser_versions() -> dict[str, str]:
    """The ``prov`` and ``rdflib`` versions the TriG depends on (E.5.4(5))."""
    out: dict[str, str] = {}
    for name in ("prov", "rdflib"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "absent"
    return out


# ------------------------------------------------------------------------------------------------ N-Triples terms
_ECHAR: Final = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r", 0x22: '\\"', 0x5C: "\\\\"}
_IRI_FORBIDDEN: Final = frozenset('<>"{}|^`\\')


def _literal_text(text: str) -> str:
    """Canonical N-Triples escaping (RDFC-1.0): ECHARs, other controls and DEL as ``\\uXXXX``, everything else as is."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if code in _ECHAR:
            out.append(_ECHAR[code])
        elif code < 0x20 or code == 0x7F:
            out.append(f"\\u{code:04X}")
        else:
            out.append(ch)
    return "".join(out)


def _iri(value: str) -> str:
    out: list[str] = []
    for ch in value:
        code = ord(ch)
        if code <= 0x20 or ch in _IRI_FORBIDDEN:
            out.append(f"\\u{code:04X}" if code <= 0xFFFF else f"\\U{code:08X}")
        else:
            out.append(ch)
    return "<" + "".join(out) + ">"


def _term(node: Any) -> str:
    import rdflib

    if isinstance(node, rdflib.BNode):
        raise TrigError("the PROV-O image holds a blank node (E.5.4 item 4)")
    if isinstance(node, rdflib.URIRef):
        return _iri(str(node))
    if isinstance(node, rdflib.Literal):
        text = '"' + _literal_text(str(node)) + '"'
        if node.language:
            return f"{text}@{str(node.language).lower()}"
        if node.datatype is not None and str(node.datatype) != XSD_STRING:
            return f"{text}^^{_iri(str(node.datatype))}"
        return text
    raise TrigError(f"an unexpected RDF term ({type(node).__name__})")


# ------------------------------------------------------------------------------------------------ the unqualified layer
#: PROV-JSON relation class -> unqualified PROV-O property (E.5.4 item 1). Subject and object are the first two formal
#: arguments of the relation, in PROV-DM order.
_UNQUALIFIED: Final[Mapping[str, str]] = {
    "ProvUsage": "used",
    "ProvGeneration": "wasGeneratedBy",
    "ProvCommunication": "wasInformedBy",
    "ProvAssociation": "wasAssociatedWith",
    "ProvDelegation": "actedOnBehalfOf",
    "ProvStart": "wasStartedBy",
    "ProvAttribution": "wasAttributedTo",
    "ProvInvalidation": "wasInvalidatedBy",
    "ProvDerivation": "wasDerivedFrom",
}
_DERIVATION_SUBTYPES: Final[Mapping[str, str]] = {
    PROV_NS + "Revision": "wasRevisionOf",
    PROV_NS + "Quotation": "wasQuotedFrom",
    PROV_NS + "PrimarySource": "hadPrimarySource",
}


def _uri(value: Any) -> str | None:
    uri = getattr(value, "uri", None)
    return uri if isinstance(uri, str) else None


def _layer(records: Iterable[Any]) -> set[tuple[str, str, str]]:
    """The unqualified triples ``(subject, property, object)`` of the identified relations among ``records``."""
    out: set[tuple[str, str, str]] = set()
    for record in records:
        prop = _UNQUALIFIED.get(type(record).__name__)
        if prop is None or record.identifier is None:
            continue
        args = record.args
        if len(args) < 2:
            continue
        subject, obj = _uri(args[0]), _uri(args[1])
        if subject is None or obj is None:
            continue
        if prop == "wasDerivedFrom":
            asserted = {_uri(t) for t in record.get_asserted_types()}
            prop = next((p for t, p in _DERIVATION_SUBTYPES.items() if t in asserted), prop)
        out.add((subject, PROV_NS + prop, obj))
    return out


# ------------------------------------------------------------------------------------------------ writer
def to_trig(prov_json: bytes | str) -> bytes:
    """The canonical TriG of one PROV-JSON document (see the module docstring). Raises :class:`TrigError`."""
    import rdflib
    from prov.model import ProvDocument

    text = prov_json.decode("utf-8") if isinstance(prov_json, bytes) else prov_json
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # caveat C4: rdflib deprecation warnings on xsd:int
            document = ProvDocument.deserialize(content=text, format="json")
        dataset = nquads.parse_nquads(*nquads.encode_nquads(document))  # the path tier 4 checks (D-131)
    except TrigError:
        raise
    except Exception as exc:  # noqa: BLE001 - library failures on a hostile or broken document become one error
        raise TrigError(f"the PROV-JSON document cannot be converted to PROV-O ({type(exc).__name__})") from None
    graphs: dict[str, set[str]] = {}
    for s, p, o, g in dataset.quads():
        graph = getattr(g, "identifier", g)
        if isinstance(graph, rdflib.BNode):
            raise TrigError("the PROV-O image names a graph by a blank node (E.5.4 item 4)")
        name = DEFAULT_GRAPH if graph is None else str(graph)
        graphs.setdefault(name, set()).add(f"{_term(s)} {_term(p)} {_term(o)} .")
    layers: list[tuple[str, Iterable[Any]]] = [(DEFAULT_GRAPH, document.get_records())]
    for bundle in document.bundles:
        iri = _uri(bundle.identifier)
        if iri is None:
            raise TrigError("a bundle has no IRI")
        layers.append((iri, bundle.get_records()))
    for name, records in layers:
        lines = graphs.setdefault(name, set())
        for subject, prop, obj in _layer(records):
            lines.add(f"{_iri(subject)} {_iri(prop)} {_iri(obj)} .")
    out: list[str] = []
    default = graphs.pop(DEFAULT_GRAPH, set())
    out.append("{\n" + "".join(line + "\n" for line in sorted(default)) + "}\n")
    for name in sorted(graphs):
        out.append(_iri(name) + " {\n" + "".join(line + "\n" for line in sorted(graphs[name])) + "}\n")
    return "".join(out).encode("utf-8")
