"""Serialisation fidelity (K.10 ``test_serialisation_fidelity.py``; EF E.5.2, E.5.5): the round trip on a clean
document, negative controls showing that both the round trip and the typed completeness check can fail (C3, C8), and
the prov 3.2.2 decode defect that forces the surrogate-namespace round trip."""

from __future__ import annotations

from typing import Any

from agentprov.validate import roundtrip
from agentprov.validate._provdoc import ProvView

from validate_support import CORE, ev, minimal_doc, q

EXAMPLE = {"ex": "http://example.org/ns#"}


def _run(doc: dict[str, Any]) -> dict[str, tuple[str, set[str]]]:
    return {o.id: (o.status, o.codes()) for o in roundtrip.check(doc, ProvView.parse(doc))}


def test_clean_document_round_trips() -> None:
    core = {"entity": {"x:m0": ev(rule="aprov.n_message@1", **{"prov:type": q("apv:Message"), "apv:partCount": 2})},
            "activity": {"x:te0": ev(**{"prov:startTime": "2026-10-08T00:00:00+00:00",
                                        "apv:durationSeconds": {"$": "1.5", "type": "xsd:double"}})},
            "used": {"x:use_request.aaaaaaaaaaaaaaaa": {"prov:activity": "x:te0", "prov:entity": "x:m0",
                                                        "prov:role": q("apv:CallRequestInput"),
                                                        "apv:sourcePointer": ["te0/call", "te0/name"],
                                                        **ev(rule="aprov.use_request@1")}}}
    results = _run(minimal_doc(core))
    assert {k: s for k, (s, _) in results.items()} == {
        "pv.roundtrip.model_equality": "pass", "pv.roundtrip.graphs": "pass", "pv.roundtrip.completeness": "pass",
        "pv.roundtrip.datatypes": "pass", "pv.roundtrip.unqualified_layer": "not_applicable"}


def test_completeness_sees_what_the_round_trip_misses() -> None:
    """C3/C8: a ``Z`` time and a non-shortest double survive the model round trip but not lexically."""
    doc = {"prefix": EXAMPLE, "activity": {"ex:a": {"prov:startTime": "2026-10-08T00:00:00Z"}},
           "entity": {"ex:e": {"ex:v": {"$": "1.50", "type": "xsd:double"}}}}
    results = _run(doc)
    assert results["pv.roundtrip.model_equality"][0] == "pass"
    assert "pv.roundtrip.literal_form" in results["pv.roundtrip.completeness"][1]


def test_foreign_datatype_namespace() -> None:
    doc = {"prefix": EXAMPLE, "entity": {"ex:e": {"ex:v": {"$": "abc", "type": "ex:custom"}}}}
    assert "pv.roundtrip.datatype_namespace" in _run(doc)["pv.roundtrip.datatypes"][1]


def test_round_trip_negative_control_library_decode_defect() -> None:
    """prov 3.2.2 rewrites decoded predicates by substring: a delegation attribute whose *local* name contains
    ``agent`` cannot survive the round trip even under the surrogate namespaces, so model equality fails."""
    doc = {"prefix": EXAMPLE, "agent": {"ex:a": {}, "ex:b": {}},
           "actedOnBehalfOf": {"ex:d": {"prov:delegate": "ex:a", "prov:responsible": "ex:b", "ex:agentNote": "v"}}}
    status, codes = _run(doc)["pv.roundtrip.model_equality"]
    assert status == "fail" and codes == {"pv.roundtrip.load"}


def test_surrogate_namespaces_make_apv_delegations_round_trip() -> None:
    core = {"agent": {"x:agent": ev(rule="aprov.n_actor@1"), "x:user": ev(rule="aprov.n_actor@1")},
            "actedOnBehalfOf": {"x:deleg_user.aaaaaaaaaaaaaaaa": {"prov:delegate": "x:agent", "prov:responsible": "x:user",
                                                                  **ev("Derived", "aprov.deleg_user@1")}}}
    out = roundtrip.check(minimal_doc(core), ProvView.parse(minimal_doc(core)))
    eq = next(o for o in out if o.id == "pv.roundtrip.model_equality")
    assert eq.status == "pass" and "surrogate" in eq.reason


def test_unexplained_bundle_graph(monkeypatch: Any) -> None:
    doc = minimal_doc()
    view = ProvView.parse(doc)
    view.bundles.pop(CORE)
    results = {o.id: o.codes() for o in roundtrip.check(doc, view)}
    assert "pv.roundtrip.unexplained_triple" in results["pv.roundtrip.completeness"]


def _graphs_by_parse(text1: bytes, text2: bytes) -> list[tuple[str, str]]:
    """The comparison D-89 step 1 made: parse both texts and compare the triple sets of each graph."""
    import rdflib

    def graphs(text: bytes) -> dict[str, set[Any]]:
        ds = rdflib.Dataset()
        ds.parse(data=text, format="nquads")
        return {str(g.identifier): set(g) for g in ds.graphs() if len(g)}

    g1, g2 = graphs(text1), graphs(text2)
    out = []
    for name in sorted(set(g1) | set(g2)):
        a, b = g1.get(name, set()), g2.get(name, set())
        if any(isinstance(x, rdflib.BNode) for t in a for x in t):
            out.append(("pv.roundtrip.blank_node", name))
        if a != b:
            out.append(("pv.roundtrip.graph_differs", f"{name} {len(a - b)}/{len(b - a)}"))
    return out


def test_graph_comparison_by_lines_equals_comparison_by_parse() -> None:
    """D-89 step 2: two graphs are compared as N-Quads line sets; a literal that looks like a graph term or a blank
    node does not confuse the grouping, and the counts are those of the parsed triple sets."""
    a, b, p, g = "<http://a/#s>", "<http://a/#t>", "<http://a/#p>", "<http://a/#g>"
    text1 = (f'{a} {p} "x <http://a/#h> ."  .\n{a} {p} "_:b0 ."  .\n{a} {p} {b} {g} .\n'
             f'{a} {p} "1"^^<http://www.w3.org/2001/XMLSchema#int> {g} .\n_:n {p} {b} <http://a/#k> .\n\n')
    text2 = f'{a} {p} "x <http://a/#h> ."  .\n{a} {p} "_:b0 ."  .\n{a} {p} {b} {g} .\n{a} {p} "2" {g} .\n\n'
    t1, t2 = text1.encode(), text2.encode()
    for x, y in ((t1, t1), (t1, t2), (t2, t1)):
        got = [(f.code, f.where if f.code.endswith("blank_node") else f"{f.where} {f.detail.split()[0]}/{f.detail.split()[3]}")
               for f in roundtrip._graphs(x, y).findings]
        assert sorted(got) == sorted(_graphs_by_parse(x, y))
    assert roundtrip._graphs(t1, t1).status == "fail"  # the blank node in <http://a/#k>
    assert {f.where for f in roundtrip._graphs(t2, t1).findings} == {"http://a/#g", "http://a/#k"}


def test_a_line_break_in_a_name_fails_tier_1_and_the_round_trip() -> None:
    """The one input on which the TriG and N-Quads round trips differ (TriG accepts an IRI with a raw line break,
    N-Quads does not) is already rejected by tier 1."""
    from agentprov.validate import prov_structure

    doc = {"prefix": EXAMPLE, "entity": {"ex:a\nb": {"ex:v": 1}}}
    assert "pv.prov_structure.qname" in {c for o in prov_structure.check(doc) for c in o.codes()}
    assert _run(doc)["pv.roundtrip.model_equality"] == ("fail", {"pv.roundtrip.load"})


def test_a_failed_model_round_trip_names_records_by_the_document_prefixes() -> None:
    """N-Quads carries no prefixes; the parsed image is given the encoding's bindings, so the model findings name
    records as a TriG text did (``ex:e``, never a minted ``ns1:e``). A lone surrogate is replaced on write."""
    doc = {"prefix": EXAMPLE, "bundle": {"ex:b": {"entity": {"ex:e": {"ex:v": "bad\ud800"}}}}}
    eq = next(o for o in roundtrip.check(doc, ProvView.parse(doc)) if o.id == "pv.roundtrip.model_equality")
    assert eq.status == "fail" and eq.findings
    assert {(f.where, f.detail) for f in eq.findings} == {("ex:b", "lost prov:Entity ex:e"),
                                                         ("ex:b", "added prov:Entity ex:e")}
