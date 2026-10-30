"""Every apv predicate the engine emits matches its declaration in the vocabulary (D-500, D-501; CA-21, CA-22; EF E.4).

For every ``apv:`` attribute of every derived document (``vocab_support``: the C.16 vectors, the generic-kind AER, every
golden pair and the R04 assessment document), at two levels:

- **PROV-JSON.** An ``owl:ObjectProperty`` takes ``prov:QUALIFIED_NAME`` values; an ``owl:DatatypeProperty`` takes
  plain JSON values or a typed literal whose datatype fits its ``rdfs:range``.
- **TriG / rdflib** (the E.5.4 image, as the A3 review repro read it). An object property has IRI objects; when the
  object is an ``apv:`` term and the range is an ``apv:`` class, the vocabulary types that individual with the range
  class (``rdf:Property`` ranges take a declared property). A data property has literal objects whose datatype is the
  declared range or derived from it (``xsd:int`` from ``xsd:integer``; a plain literal is ``xsd:string``).

Before apv 0.2.0 this failed on ``apv:RecordedNull`` objects of data properties (D-500) and on adapter-declared
assumptions written as ``xsd:string`` literals of the object property ``apv:assumption`` (D-501): they now go on the
data property ``apv:adapterAssumption``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import rdflib
from rdflib.namespace import OWL, RDF, RDFS, XSD

from agentprov.prov.serialise.trig import to_trig

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vocab_support as vs  # noqa: E402

#: Datatypes accepted for each declared range (XSD derivation: xsd:int and xsd:long are xsd:integer).
COMPATIBLE: dict[rdflib.URIRef, frozenset[rdflib.URIRef]] = {
    XSD.string: frozenset({XSD.string}),
    XSD.integer: frozenset({XSD.integer, XSD.int, XSD.long, XSD.short, XSD.nonNegativeInteger}),
    XSD.nonNegativeInteger: frozenset({XSD.nonNegativeInteger, XSD.int, XSD.long, XSD.integer}),
    XSD.boolean: frozenset({XSD.boolean}),
    XSD.double: frozenset({XSD.double}),
}
PROPERTY_TYPES = (OWL.ObjectProperty, OWL.DatatypeProperty)


@pytest.fixture(scope="module")
def documents(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    tmp = tmp_path_factory.mktemp("vocab-consistency")
    return {**vs.vector_documents(), **vs.generic_document(tmp)}


@pytest.fixture(scope="module")
def golden(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    return vs.golden_documents(tmp_path_factory.mktemp("vocab-consistency-golden"))


def _kind(term: rdflib.URIRef) -> rdflib.URIRef | None:
    graph = vs.vocab_graph()
    return next((k for k in PROPERTY_TYPES if (term, RDF.type, k) in graph), None)


def _range(term: rdflib.URIRef) -> rdflib.URIRef | None:
    value = vs.vocab_graph().value(term, RDFS.range)
    return value if isinstance(value, rdflib.URIRef) else None


def _json_datatype(value: Any) -> rdflib.URIRef | None:
    """The datatype of a PROV-JSON attribute value (None for a QName or an unknown shape)."""
    if isinstance(value, bool):
        return XSD.boolean
    if isinstance(value, int):
        return XSD.integer
    if isinstance(value, str):
        return XSD.string
    if isinstance(value, dict) and isinstance(value.get("type"), str) and value["type"] != vs.QNAME:
        prefix, _, local = value["type"].partition(":")
        return XSD[local] if prefix == "xsd" else rdflib.URIRef(value["type"])
    return None


def _fits(datatype: rdflib.URIRef | None, declared: rdflib.URIRef | None) -> bool:
    if declared is None:  # no rdfs:range (apv:outcomeValue): any literal
        return datatype is not None
    return datatype is not None and datatype in COMPATIBLE.get(declared, frozenset({declared}))


def _individual_ok(obj: rdflib.URIRef, declared: rdflib.URIRef | None) -> bool:
    """An apv: object of an object property whose range is a class: the vocabulary types it with that class."""
    graph = vs.vocab_graph()
    if declared is None or not str(obj).startswith(vs.APV):
        return True
    if declared == RDF.Property:
        return any((obj, RDF.type, k) in graph for k in PROPERTY_TYPES)
    if not str(declared).startswith(vs.APV):
        return True  # a PROV class range (prov:Bundle): instances are not vocabulary terms
    return (obj, RDF.type, declared) in graph


def _provjson_problems(prov_json: bytes) -> list[str]:
    problems: set[str] = set()
    for _scope, _section, _ident, body in vs.bodies(vs.decode(prov_json)):
        for key, value in body.items():
            if not key.startswith("apv:"):
                continue
            term = rdflib.URIRef(vs.APV + key[4:])
            kind, declared = _kind(term), _range(term)
            for v in vs.values(value):
                name = vs.qname(v)
                if kind is None:
                    problems.add(f"{key}: not a declared property")
                elif kind == OWL.ObjectProperty and name is None:
                    problems.add(f"{key}: object property with the literal {type(v).__name__} value")
                elif kind == OWL.ObjectProperty and name is not None and name.startswith("apv:") and not \
                        _individual_ok(rdflib.URIRef(vs.APV + name[4:]), declared):
                    problems.add(f"{key}: {name} is not a {declared}")
                elif kind == OWL.DatatypeProperty and name is not None:
                    problems.add(f"{key}: data property with the QName value {name}")
                elif kind == OWL.DatatypeProperty and not _fits(_json_datatype(v), declared):
                    problems.add(f"{key}: value of type {_json_datatype(v)} outside the range {declared}")
    return sorted(problems)


def _trig_problems(prov_json: bytes) -> list[str]:
    ds = rdflib.Dataset()
    ds.parse(data=to_trig(prov_json), format="trig")
    problems: set[str] = set()
    for _s, p, o, _g in ds.quads():
        if not isinstance(p, rdflib.URIRef) or not str(p).startswith(vs.APV):
            continue
        key = "apv:" + str(p)[len(vs.APV):]
        kind, declared = _kind(p), _range(p)
        if kind is None:
            problems.add(f"{key}: not a declared property")
        elif kind == OWL.ObjectProperty and not isinstance(o, rdflib.URIRef):
            problems.add(f"{key}: object property with a literal object")
        elif kind == OWL.ObjectProperty and not _individual_ok(o, declared):
            problems.add(f"{key}: {o} is not a {declared}")
        elif kind == OWL.DatatypeProperty and not isinstance(o, rdflib.Literal):
            problems.add(f"{key}: data property with the IRI object {o}")
        elif kind == OWL.DatatypeProperty and isinstance(o, rdflib.Literal):
            datatype = o.datatype or (None if o.language else XSD.string)
            if not _fits(datatype, declared):
                problems.add(f"{key}: literal of type {datatype} outside the range {declared}")
    return sorted(problems)


def _all(docs: dict[str, bytes]) -> dict[str, list[str]]:
    return {name: p for name, doc in docs.items() if (p := _provjson_problems(doc) + _trig_problems(doc))}


def test_emitted_predicates_match_their_declarations(documents: dict[str, bytes]) -> None:
    assert _all(documents) == {}


def test_emitted_predicates_match_their_declarations_on_the_golden_set(golden: dict[str, bytes]) -> None:
    assert _all(golden) == {}


def test_adapter_assumptions_are_strings_on_apv_adapter_assumption(documents: dict[str, bytes],
                                                                    golden: dict[str, bytes]) -> None:
    """E.10 item 11 / D-17: an adapter-declared ``<ns>:<Name>`` stays a string, on ``apv:adapterAssumption``; a core
    ``apv:`` assumption stays a QName on ``apv:assumption``. Both occur in the inputs (ROPE, the assessment's
    ``semtest:NormaliserFaithful``)."""
    seen = {"apv:assumption": set(), "apv:adapterAssumption": set()}  # type: dict[str, set[str]]
    for doc in {**documents, **golden}.values():
        for _scope, _section, _ident, body in vs.bodies(vs.decode(doc)):
            for key in seen:
                for v in vs.values(body.get(key, [])):
                    seen[key].add(vs.qname(v) or f"literal:{v}")
    assert seen["apv:assumption"] and all(v.startswith("apv:") for v in seen["apv:assumption"])
    adapter = seen["apv:adapterAssumption"]
    assert adapter and all(v.startswith("literal:") and not v.startswith("literal:apv:") for v in adapter)
    assert "literal:semtest:NormaliserFaithful" in adapter
