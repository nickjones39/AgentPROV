"""An asserted JSON null goes on the ``apv:<prop>Status`` sibling, never on the data property (D-500; CA-21; EF E.5
item 5, E.4.5).

Before apv 0.2.0 the engine wrote the IRI ``apv:RecordedNull`` as the object of ``owl:DatatypeProperty`` terms
(``apv:error``, ``apv:defenceId``, ...): not OWL 2 DL, and under RDFS it entails ``apv:RecordedNull a xsd:string``.
The engine now emits ``<prop>Status apv:RecordedNull`` and omits the data property. Checked on the C.16 vectors, the
generic-kind AER, every golden pair and the R04 assessment document (``vocab_support``), at the PROV-JSON level and on
the TriG image (rdflib), plus a static check that every data property ``opt()`` can fill has its declared sibling.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from agentprov.prov.serialise.trig import to_trig

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vocab_support as vs  # noqa: E402

NODES = vs.REPO / "src" / "agentprov" / "prov" / "rules" / "nodes.py"
APV = rdflib.Namespace(vs.APV)
RECORDED_NULL = "apv:RecordedNull"


@pytest.fixture(scope="module")
def documents(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    tmp = tmp_path_factory.mktemp("vocab-null")
    return {**vs.vector_documents(), **vs.generic_document(tmp)}


@pytest.fixture(scope="module")
def golden(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    return vs.golden_documents(tmp_path_factory.mktemp("vocab-null-golden"))


def _data_properties() -> set[rdflib.URIRef]:
    return {p for p in vs.vocab_graph().subjects(RDF.type, OWL.DatatypeProperty) if isinstance(p, rdflib.URIRef)}


def _iri_objects_of_data_properties(prov_json: bytes) -> list[tuple[str, str]]:
    data = _data_properties()
    ds = rdflib.Dataset()
    ds.parse(data=to_trig(prov_json), format="trig")
    return sorted({(str(p)[len(vs.APV):], str(o)) for _s, p, o, _g in ds.quads() if p in data
                   and isinstance(o, rdflib.URIRef)})


def _null_placements(prov_json: bytes) -> list[str]:
    """The attribute keys that hold ``apv:RecordedNull`` in a PROV-JSON document."""
    out: list[str] = []
    for _scope, _section, _ident, body in vs.bodies(vs.decode(prov_json)):
        for key, value in body.items():
            if any(vs.qname(v) == RECORDED_NULL for v in vs.values(value)):
                out.append(key)
    return out


def _check_document(prov_json: bytes) -> list[str]:
    graph = vs.vocab_graph()
    problems = [f"data property apv:{p} has the IRI object {o}" for p, o in _iri_objects_of_data_properties(prov_json)]
    for key in _null_placements(prov_json):
        term = APV[key.removeprefix("apv:")]
        if not key.endswith("Status") or (term, RDF.type, OWL.ObjectProperty) not in graph:
            problems.append(f"{key} holds apv:RecordedNull but is not a status object property")
    return problems


def test_no_data_property_has_an_iri_object(documents: dict[str, bytes]) -> None:
    problems = {name: p for name, doc in documents.items() if (p := _check_document(doc))}
    assert problems == {}


def test_no_data_property_has_an_iri_object_on_the_golden_set(golden: dict[str, bytes]) -> None:
    problems = {name: p for name, doc in golden.items() if (p := _check_document(doc))}
    assert problems == {}


def test_the_nulls_moved_to_their_status_siblings(documents: dict[str, bytes]) -> None:
    """The vectors hold asserted nulls (C.16.2's ``defense_id``, tool-result ``error`` on success): each one is now a
    ``<prop>Status apv:RecordedNull`` and the data property is absent from that node."""
    placed = {key for doc in documents.values() for key in _null_placements(doc)}
    assert {"apv:defenceIdStatus", "apv:errorStatus"} <= placed
    for doc in documents.values():
        for _scope, _section, _ident, body in vs.bodies(vs.decode(doc)):
            for key, value in body.items():
                if key.endswith("Status") and any(vs.qname(v) == RECORDED_NULL for v in vs.values(value)):
                    prop = key.removesuffix("Status")
                    assert prop not in body, f"{key} beside {prop}"


def _opt_properties() -> set[str]:
    """Every apv property ``opt()`` fills with the default converter ``lit`` in ``prov/rules/nodes.py``. A property
    passed as a loop variable (the header's ``(field, property)`` table) is taken from the pairs of its function."""
    out: set[str] = set()
    for func in ast.walk(ast.parse(NODES.read_text(encoding="utf-8"))):
        if not isinstance(func, ast.FunctionDef):
            continue
        for node in ast.walk(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "opt"):
                continue
            if len(node.args) != 4 or node.keywords:
                continue  # a converter other than lit: no RecordedNull
            prop = node.args[3]
            if isinstance(prop, ast.Constant) and isinstance(prop.value, str) and prop.value.startswith("apv:"):
                out.add(prop.value)
            elif isinstance(prop, ast.Name):
                for pair in ast.walk(func):
                    if isinstance(pair, ast.Tuple) and len(pair.elts) == 2 and all(
                            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in pair.elts):
                        value = pair.elts[1].value  # type: ignore[attr-defined]
                        if value.startswith("apv:"):
                            out.add(value)
    return out


def test_every_opt_filled_data_property_has_a_status_sibling() -> None:
    graph = vs.vocab_graph()
    props = _opt_properties()
    assert {"apv:error", "apv:taskId", "apv:defenceId", "apv:finishReason", "apv:servedModel", "apv:requestedModel",
            "apv:toolName", "apv:outcomeValue", "apv:reason"} <= props
    missing = []
    for prop in sorted(props):
        local = prop.removeprefix("apv:")
        assert (APV[local], RDF.type, OWL.DatatypeProperty) in graph, prop
        status = APV[f"{local}Status"]
        if (status, RDF.type, OWL.ObjectProperty) not in graph or (status, RDFS.range, APV.EpistemicStatus) not in graph:
            missing.append(f"apv:{local}Status")
    assert missing == []
