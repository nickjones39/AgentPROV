"""Serialisation fidelity: the PROV-JSON -> PROV-O round trip and the typed, bidirectional completeness check (D8 tier
4; EF E.5.2, E.5.5; K.10 ``test_serialisation_fidelity.py``).

Checks:

* ``pv.roundtrip.model_equality`` - PROV-JSON -> ``prov.model.ProvDocument`` -> PROV-O N-Quads -> ``ProvDocument``
  gives a model equal to the first;
* ``pv.roundtrip.graphs`` - every graph (the default graph and one named graph per bundle) is identical across the
  two serialisations (no blank nodes are expected, so isomorphism is set equality, compared as sets of N-Quads lines;
  blank nodes are themselves a finding, E.5.4 item 4);
* ``pv.roundtrip.completeness`` - typed and bidirectional (caveat C8): every attribute and argument of every JSON
  statement appears in the RDF with the same datatype and lexical form, and every triple of every graph is explained
  by the JSON (an attribute, a typing triple, a qualification link or a qualified-node argument);
* ``pv.roundtrip.datatypes`` - every literal datatype is under ``http://www.w3.org/2001/XMLSchema#`` (E.4.1, C5);
* ``pv.roundtrip.unqualified_layer`` - ``not_applicable`` here: the unqualified layer belongs to the on-demand TriG of
  E.5.4 (``agentprov derive --trig``), which is not an input of this validator.

**Library defect (prov 3.2.2; observed 2026-10-08, EF E.5.2 caveat C9).** ``ProvRDFSerializer`` rewrites predicates on decode by *substring*:
``_DECODE_PREDICATE_REWRITES`` maps every predicate whose IRI contains ``"agent"`` on a ``prov:Delegation`` node to
``prov:responsible`` (likewise ``"activity"``/``"entity"`` on communications, starts, ends and derivations). Every
``apv:`` IRI contains ``agentprov``, so a qualified delegation with any ``apv:`` attribute cannot be decoded. The model
round trip therefore runs under a bijective renaming of every declared namespace IRI to a neutral surrogate
(``http://ns<i>.roundtrip.invalid/#``); model equality is invariant under such a renaming except for this defect. The
completeness check, which only encodes, uses the real namespaces. The outcome's ``reason`` records the renaming.

**One encoding per model, one parse (regeneration batch, D-89 and its step-2 addendum).** The document is encoded and
written as N-Quads once (under the surrogate names), that text is parsed once, and the parsed dataset serves the model
decode (what ``ProvDocument.deserialize`` does with the same text) and the completeness check, which reads it with
every surrogate namespace mapped back to its real IRI (the renaming is a bijection on namespace IRIs, and the encoder
and the N-Quads writer and parser treat a namespace IRI as an opaque string). The decoded model is encoded and written
again, and the two texts are compared as sets of lines per graph: the N-Quads writer prints each term in one form, so
two graphs are equal exactly when their line sets are, and the second text need not be parsed (a blank node counts
as lost and added, as it did when both texts were parsed). N-Quads carries no prefixes, so the parsed image is given
the namespace bindings of the encoding, which a TriG text declared: the decoder names IRIs by them. N-Quads replaced TriG
(the writer is about ten times faster on the largest DTap run); the two parsers differ only on an IRI with a raw line
break, which TriG accepts and N-Quads rejects, and tier 1 already rejects such a name (``pv.structure.qname``). Each
object is released as soon as the checks no longer need it: the parsed image after completeness, the first model
before the second is encoded.

The encode and the parse are :mod:`agentprov.prov.serialise.nquads`, the same functions the on-demand TriG
(:func:`agentprov.prov.serialise.trig.to_trig`) reads its triple set through (D-131).

Library versions (``prov``, ``rdflib``) are returned for the report (caveat C4). Integers are written as ``xsd:int``
and plain strings as untyped literals (``xsd:string`` in RDF 1.1): both are compared as typed literals.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterator, Mapping
from importlib import metadata
from typing import Any, Final

from agentprov.prov.serialise import nquads
from agentprov.validate._provdoc import RELATION_ARGS, UNIDENTIFIED, ProvView, St, as_list
from agentprov.validate.tiers import CheckOutcome, Finding, outcome

__all__ = ["SURROGATE", "check", "library_versions"]

M: Final = "pv.roundtrip"
PROV_NS: Final = "http://www.w3.org/ns/prov#"
XSD_NS: Final = "http://www.w3.org/2001/XMLSchema#"
RDF_TYPE: Final = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL: Final = "http://www.w3.org/2000/01/rdf-schema#label"
SURROGATE: Final = "http://ns{i}.roundtrip.invalid/#"
DEFECT_NEEDLES: Final = ("agent", "activity", "entity", "startTime", "endTime")
#: PROV-JSON attribute -> PROV-O predicate, where they differ.
PREDICATE: Final[Mapping[str, str]] = {
    "prov:type": RDF_TYPE,
    "prov:label": RDFS_LABEL,
    "prov:role": PROV_NS + "hadRole",
    "prov:startTime": PROV_NS + "startedAtTime",
    "prov:endTime": PROV_NS + "endedAtTime",
    "prov:time": PROV_NS + "atTime",
    "prov:location": PROV_NS + "atLocation",
}
ELEMENT_CLASS: Final = {"entity": "Entity", "activity": "Activity", "agent": "Agent"}
QUALIFIED_CLASS: Final = {
    "used": "Usage", "wasGeneratedBy": "Generation", "wasInformedBy": "Communication", "wasStartedBy": "Start",
    "wasEndedBy": "End", "wasInvalidatedBy": "Invalidation", "wasDerivedFrom": "Derivation",
    "wasAttributedTo": "Attribution", "wasAssociatedWith": "Association", "actedOnBehalfOf": "Delegation",
    "wasInfluencedBy": "Influence",
}  # fmt: skip
DERIVATION_SUBCLASSES: Final = frozenset(("U", PROV_NS + c) for c in ("Revision", "Quotation", "PrimarySource"))
UNQUALIFIED_PREDICATE: Final = {"hadMember": "hadMember", "specializationOf": "specializationOf",
                                "mentionOf": "mentionOf", "alternateOf": "alternateOf"}

Term = tuple[str, ...]  # ("U", iri) | ("L", lexical, datatype, lang)


def library_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ("prov", "rdflib"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "absent"
    return out


def check(doc: Mapping[str, Any], view: ProvView) -> list[CheckOutcome]:
    """Run the fidelity checks; a library that is absent or fails to load the document gives ``skipped``/``fail``."""
    try:
        import rdflib  # noqa: F401
        from prov.model import ProvDocument  # noqa: F401
    except ImportError as exc:  # pragma: no cover - both are core dependencies
        reason = f"prov/rdflib not importable: {type(exc).__name__}"
        return [CheckOutcome(f"{M}.{n}", "skipped", reason=reason)
                for n in ("model_equality", "graphs", "completeness", "datatypes")] + [_unqualified()]
    return [*_round_trip(doc, view), _unqualified()]


def _unqualified() -> CheckOutcome:
    return CheckOutcome(f"{M}.unqualified_layer", "not_applicable",
                        reason="the unqualified layer is part of the on-demand TriG (E.5.4), not of the PROV-JSON input")


def _load(text: str, fmt: str, **kw: Any) -> Any:
    from prov.model import ProvDocument

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # caveat C4: rdflib DeprecationWarnings on xsd:int
        return ProvDocument.deserialize(content=text, format=fmt, **kw)


def _decode(ds: Any) -> Any:
    """``ProvDocument.deserialize`` of the text ``ds`` was parsed from: the library parses into a ``Dataset`` with
    ``default_union=True`` and decodes it; the same dataset is decoded here instead of parsing the text again."""
    from prov.model import ProvDocument
    from prov.serializers.provrdf import ProvRDFSerializer

    document = ProvDocument()
    ds.default_union = True
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            serializer = ProvRDFSerializer()
            serializer.document = document  # as deserialize() does before decoding
            serializer.decode_document(ds, document)
    finally:
        ds.default_union = False
    return document


# ============================================================================================================ model
class _Image:
    """The parsed PROV-O image of the document under the surrogate names, and the map back to the real names; ``None``
    as ``dataset`` when encoding, writing or parsing failed (then ``error`` names the exception type)."""

    def __init__(self, dataset: Any, back: Mapping[str, str], error: str | None = None) -> None:
        self.dataset, self.back, self.error = dataset, back, error

    def real(self, iri: str) -> str:
        """``iri`` with its surrogate namespace (``http://ns<i>.roundtrip.invalid/#``) replaced by the real one."""
        if iri.startswith("http://ns") and ".roundtrip.invalid/#" in iri:
            head, sep, tail = iri.partition("/#")
            real = self.back.get(head + sep)
            if real is not None:
                return real + tail
        return iri


def _round_trip(doc: Mapping[str, Any], view: ProvView) -> list[CheckOutcome]:
    prefixes = doc.get("prefix") if isinstance(doc.get("prefix"), dict) else {}
    assert isinstance(prefixes, dict)
    renamed = dict(doc)
    renamed["prefix"] = {p: SURROGATE.format(i=i) for i, p in enumerate(sorted(prefixes))}
    back = {SURROGATE.format(i=i): str(prefixes[p]) for i, p in enumerate(sorted(prefixes))}
    hit = sorted(p for p, iri in prefixes.items() if any(n in str(iri) for n in DEFECT_NEEDLES))
    note = ("namespace IRIs renamed bijectively to surrogates (prov 3.2.2 substring rewrite on decode"
            + (f"; affected prefixes: {', '.join(hit)})" if hit else ")"))

    def failed(exc: Exception) -> list[CheckOutcome]:
        f = Finding(f"{M}.load", "document", f"prov library failed: {type(exc).__name__}")
        return [CheckOutcome(f"{M}.model_equality", "fail", (f,), reason=note),
                CheckOutcome(f"{M}.graphs", "skipped", reason="the round trip did not complete")]

    try:  # the library is total on nothing; any failure is a finding, never a crash
        first = _load(json.dumps(renamed), "json")
        text1, bindings = nquads.encode_nquads(first)
        image = _Image(nquads.parse_nquads(text1, bindings), back)
    except Exception as exc:
        return [*failed(exc), *_completeness(_Image(None, back, error=type(exc).__name__), view)]
    try:
        second = _decode(image.dataset)
        findings: list[Finding] = list(_model_diff(first, second)) if first != second else []
        del first
    except Exception as exc:
        return [*failed(exc), *_completeness(image, view)]
    # peak memory: completeness releases the parsed image after the first model and before the second encoding
    completeness = _completeness(image, view)
    try:
        text2, _ = nquads.encode_nquads(second)
        del second
    except Exception as exc:
        return [*failed(exc), *completeness]
    eq = outcome(f"{M}.model_equality", findings)
    eq = CheckOutcome(eq.id, eq.status, eq.findings, reason=note, truncated=eq.truncated)
    return [eq, _graphs(text1, text2), *completeness]


def _quads(text: bytes) -> dict[str, set[bytes]]:
    """N-Quads lines by graph name (``urn:x-rdflib:default`` for the default graph). The writer prints each term in
    one canonical form and escapes line breaks inside literals, so two graphs are equal exactly when their line sets
    are; a default-graph line has an empty graph term (it ends ``"  ."``), a named one ends ``" <iri> ."``."""
    from rdflib.graph import DATASET_DEFAULT_GRAPH_ID

    out: dict[str, set[bytes]] = {}
    default = str(DATASET_DEFAULT_GRAPH_ID)
    for line in text.split(b"\n"):
        if not line:
            continue
        body = line[:-2]
        name = default if body.endswith(b" ") else body.rsplit(b" ", 1)[1][1:-1].decode("utf-8")
        out.setdefault(name, set()).add(line)
    return out


def _graphs(text1: bytes, text2: bytes) -> CheckOutcome:
    graphs1, graphs2 = _quads(text1), _quads(text2)
    findings: list[Finding] = []
    for name in sorted(set(graphs1) | set(graphs2)):
        a, b = graphs1.get(name, set()), graphs2.get(name, set())
        blank_a, blank_b = _blank(a), _blank(b)
        if blank_a:
            findings.append(Finding(f"{M}.blank_node", name, "the PROV-O image contains blank nodes"))
        # a parse relabels every blank node, so a triple naming one never matched when both texts were parsed (D-89):
        # it counts as lost and added, as it did then
        lost, added = len(a - blank_a - b) + len(blank_a), len(b - blank_b - a) + len(blank_b)
        if lost or added:
            findings.append(Finding(f"{M}.graph_differs", name, f"{lost} triples lost, {added} added"))
    return outcome(f"{M}.graphs", findings)


def _blank(lines: set[bytes]) -> set[bytes]:
    """The lines whose subject or object is a blank node (a predicate never is; a literal object starts with ``"``)."""
    return {q for q in lines if q.startswith(b"_:") or q.split(b" ", 2)[2].startswith(b"_:")}


def _model_diff(first: Any, second: Any) -> Iterator[Finding]:
    def containers(d: Any) -> dict[str, set[Any]]:
        out = {"top": set(d.get_records())}
        for b in d.bundles:
            out[str(b.identifier)] = set(b.get_records())
        return out

    c1, c2 = containers(first), containers(second)
    for name in sorted(set(c1) | set(c2)):
        a, b = c1.get(name, set()), c2.get(name, set())
        for r in sorted(a - b, key=str)[:20]:
            yield Finding(f"{M}.model_differs", name, f"lost {r.get_type()} {r.identifier}")
        for r in sorted(b - a, key=str)[:20]:
            yield Finding(f"{M}.model_differs", name, f"added {r.get_type()} {r.identifier}")
    if c1 == c2:
        yield Finding(f"{M}.model_differs", "document", "documents differ outside their records")


# ============================================================================================================ completeness
class _Expander:
    def __init__(self, prefixes: Mapping[str, Any]) -> None:
        self.ns = {str(k): str(v) for k, v in prefixes.items()}
        self.ns.setdefault("prov", PROV_NS)
        self.ns.setdefault("xsd", XSD_NS)

    def iri(self, qname: str) -> str:
        prefix, _, local = qname.partition(":")
        return self.ns.get(prefix, prefix + ":") + local

    def predicate(self, attr: str) -> str:
        return PREDICATE.get(attr) or self.iri(attr)

    def term(self, attr: str, value: Any) -> Term:
        if isinstance(value, dict):
            t = str(value.get("type", ""))
            if t == "prov:QUALIFIED_NAME":
                return ("U", self.iri(str(value.get("$"))))
            return ("L", str(value.get("$")), self.iri(t) if t else XSD_NS + "string", str(value.get("lang") or ""))
        if isinstance(value, bool):
            return ("L", "true" if value else "false", XSD_NS + "boolean", "")
        if isinstance(value, int):
            return ("L", str(value), XSD_NS + "int", "")
        if attr in ("prov:startTime", "prov:endTime", "prov:time"):
            return ("L", str(value), XSD_NS + "dateTime", "")
        return ("L", str(value), XSD_NS + "string", "")


def _rdf_term(node: Any) -> Term:
    import rdflib

    if isinstance(node, rdflib.Literal):
        dt = str(node.datatype) if node.datatype is not None else XSD_NS + "string"
        return ("L", str(node), dt, str(node.language or ""))
    return ("U", str(node))


def _completeness(image: _Image, view: ProvView) -> list[CheckOutcome]:
    import rdflib

    x = _Expander(view.prefixes)
    if image.dataset is None:
        f = Finding(f"{M}.load", "document", f"prov library failed: {image.error or 'no PROV-O image'}")
        return [CheckOutcome(f"{M}.completeness", "fail", (f,)), CheckOutcome(f"{M}.datatypes", "skipped",
                                                                              reason="no PROV-O image")]
    graphs: dict[str, set[tuple[str, str, Term]]] = {}
    datatype_findings: list[Finding] = []
    real = image.real
    for g in image.dataset.graphs():
        name = real(str(g.identifier))
        triples: set[tuple[str, str, Term]] = set()
        for s, p, o in g:
            raw: Term = _rdf_term(o)
            term: Term = ("U", real(raw[1])) if raw[0] == "U" else ("L", raw[1], real(raw[2]), raw[3])
            if term[0] == "L" and not term[2].startswith(XSD_NS) and term[2] != str(rdflib.RDF.langString):
                datatype_findings.append(Finding(f"{M}.datatype_namespace", name, f"datatype {term[2]}"))
            triples.add((real(str(s)), real(str(p)), term))
        graphs[name] = triples
    image.dataset = None  # the last reader: release the parsed image
    default = next((n for n in graphs if n.startswith("urn:x-rdflib:default")), "urn:x-rdflib:default")
    findings: list[Finding] = []
    containers: list[tuple[str, list[St]]] = [(default, view.top)]
    containers += [(x.iri(b.iri), b.statements) for b in view.bundles.values()]
    for name, statements in containers:
        findings += _container_completeness(x, name, statements, graphs.get(name, set()))
    known = {n for n, _ in containers}
    for name, triples in graphs.items():
        if name not in known and triples:
            findings.append(Finding(f"{M}.unexplained_triple", name, f"graph with {len(triples)} triples not in the JSON"))
    return [outcome(f"{M}.completeness", findings), outcome(f"{M}.datatypes", datatype_findings)]


def _container_completeness(x: _Expander, name: str, statements: list[St],
                            graph: set[tuple[str, str, Term]]) -> Iterator[Finding]:
    expected: set[tuple[str, str, Term]] = set()
    optional: set[tuple[str, str, Term]] = set()
    by_subject_pred: dict[tuple[str, str], set[Term]] = {}
    by_subject: dict[str, set[tuple[str, Term]]] = {}
    for s, p, o in graph:
        by_subject_pred.setdefault((s, p), set()).add(o)
        by_subject.setdefault(s, set()).add((p, o))
    qualified: dict[str, tuple[str, set[str]]] = {}  # qualified node -> (influencee, other argument IRIs)
    missing: list[Finding] = []
    for st in statements:
        if st.is_element:
            subject = x.iri(st.key)
            want = _attr_triples(x, subject, st, skip=())
            want.add((subject, RDF_TYPE, ("U", PROV_NS + ELEMENT_CLASS[st.section])))
        elif st.section in UNIDENTIFIED:
            args = st.args()
            first = RELATION_ARGS[st.section][0]
            second = RELATION_ARGS[st.section][1]
            if first not in args or second not in args:
                continue
            subject = x.iri(args[first])
            want = set[tuple[str, str, Term]]()
            want.add((subject, PROV_NS + UNQUALIFIED_PREDICATE[st.section], ("U", x.iri(args[second]))))
            if st.section == "mentionOf" and "prov:bundle" in args:
                want.add((subject, PROV_NS + "asInBundle", ("U", x.iri(args["prov:bundle"]))))
        else:
            subject = x.iri(st.key)
            args = st.args()
            arg_keys = RELATION_ARGS[st.section]
            influencee = args.get(arg_keys[0])
            base = (subject, RDF_TYPE, ("U", PROV_NS + QUALIFIED_CLASS[st.section]))
            want = _attr_triples(x, subject, st, skip=tuple(k for k in arg_keys if k != "prov:time"))
            if st.section == "wasDerivedFrom" and any(t[2] in DERIVATION_SUBCLASSES for t in want if t[1] == RDF_TYPE):
                optional.add(base)  # the library types a Revision/Quotation/PrimarySource node by its subclass only
            else:
                want.add(base)
            others = {x.iri(v) for k, v in args.items() if k != arg_keys[0]}
            qualified[subject] = (x.iri(influencee) if influencee else "", others)
            if influencee and not any(p.startswith(PROV_NS + "qualified") and o == ("U", subject)
                                      for p, o in by_subject.get(x.iri(influencee), ())):
                missing.append(Finding(f"{M}.missing_triple", f"{name}:{st.key}", "no qualification link from its subject"))
            for k, v in args.items():
                if k == arg_keys[0]:
                    continue
                if not any(p.startswith(PROV_NS) and o == ("U", x.iri(v)) for p, o in by_subject.get(subject, ())):
                    missing.append(Finding(f"{M}.missing_triple", f"{name}:{st.key}", f"argument {k} not in the RDF"))
        expected |= want
        for triple in want:
            if triple not in graph:
                alt = by_subject_pred.get((triple[0], triple[1]), set())
                code = "literal_form" if alt and triple[2][0] == "L" else "missing_triple"
                missing.append(Finding(f"{M}.{code}", f"{name}:{st.key}", f"{_short(triple[1])} {_describe(triple[2])}"))
    yield from missing
    for s, p, o in sorted(graph - expected - optional, key=lambda t: (t[0], t[1], t[2])):
        if p.startswith(PROV_NS + "qualified") and o[0] == "U" and o[1] in qualified and qualified[o[1]][0] == s:
            continue
        if s in qualified and p.startswith(PROV_NS) and o[0] == "U" and o[1] in qualified[s][1]:
            continue
        yield Finding(f"{M}.unexplained_triple", f"{name}:{_short(s)}", f"{_short(p)} not explained by the JSON")


def _attr_triples(x: _Expander, subject: str, st: St, *, skip: tuple[str, ...]) -> set[tuple[str, str, Term]]:
    out: set[tuple[str, str, Term]] = set()
    for attr, value in st.attrs.items():
        if attr in skip:
            continue
        pred = x.predicate(attr)
        for v in as_list(value):
            out.add((subject, pred, x.term(attr, v)))
    return out


def _short(iri: str) -> str:
    for prefix, ns in (("prov:", PROV_NS), ("xsd:", XSD_NS), ("rdf:", RDF_TYPE[:-4]), ("rdfs:", RDFS_LABEL[:-5])):
        if iri.startswith(ns):
            return prefix + iri[len(ns):]
    return iri.rsplit("#", 1)[-1] if "#" in iri else iri.rsplit("/", 1)[-1]


def _describe(term: Term) -> str:
    if term[0] == "U":
        return _short(term[1])
    return f"literal typed {_short(term[2])}"
