"""Render the HTML documentation page of the ``apv`` vocabulary from ``vocab/apv-0.2.ttl`` (EF E.4.6).

    uv run python tools/ns_page.py --out ../AgentPROV-ns/ns/0.2.0/index.html
    uv run python tools/ns_page.py --check ../AgentPROV-ns/ns/0.2.0/index.html

The page is served at ``https://w3id.org/agentprov/ns`` (HTML clients) and ``…/ns/0.2.0``. It lists every class,
property and individual with its label and comment, generated from the ontology only, so the page and the Turtle never
disagree. Output is deterministic: terms are sorted, and nothing depends on the clock.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef

ROOT = Path(__file__).resolve().parents[1]
TTL = ROOT / "src" / "agentprov" / "vocab" / "apv-0.2.ttl"
APV = "https://w3id.org/agentprov/ns#"
ONTOLOGY = URIRef("https://w3id.org/agentprov/ns")
PREFIXES = {
    APV: "apv:",
    "http://www.w3.org/ns/prov#": "prov:",
    "http://www.w3.org/2001/XMLSchema#": "xsd:",
    "http://www.w3.org/2004/02/skos/core#": "skos:",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
}
STYLE = (
    "body{font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;max-width:60rem;margin:2.5rem auto;padding:0 1rem;"
    "color:#1d1d1f;background:#fff}code{background:#f2f2f4;padding:.1em .3em;border-radius:4px}h1{font-size:1.6rem}"
    "h2{margin-top:2.2rem;border-bottom:1px solid #ddd}table{border-collapse:collapse;width:100%;font-size:.92rem}"
    "td,th{text-align:left;vertical-align:top;padding:.35rem .5rem;border-bottom:1px solid #eee}a{color:#0b5cad}"
    ".note{background:#fff7e0;border-left:4px solid #e0a800;padding:.6rem .8rem}"
    "@media (prefers-color-scheme:dark){body{color:#e6e6e8;background:#141416}code{background:#26262a}a{color:#7ab4ff}"
    "td,th{border-color:#2a2a2e}h2{border-color:#333}.note{background:#2a2410;border-color:#a07a00}}"
)


def curie(node: object) -> str:
    text = str(node)
    for ns, prefix in PREFIXES.items():
        if text.startswith(ns):
            return prefix + text[len(ns):]
    return text


def text_of(graph: Graph, subject: URIRef, prop: URIRef) -> str:
    value = graph.value(subject, prop)
    return str(value) if isinstance(value, Literal) else ""


def link(node: object) -> str:
    name = curie(node)
    if name.startswith("apv:"):
        return f'<a href="#{html.escape(name[4:])}"><code>{html.escape(name)}</code></a>'
    return f"<code>{html.escape(name)}</code>"


def render(graph: Graph) -> str:
    def terms(kind: URIRef) -> list[URIRef]:
        return sorted((s for s in graph.subjects(RDF.type, kind) if isinstance(s, URIRef) and str(s).startswith(APV)),
                      key=str)

    classes = terms(OWL.Class)
    props = sorted(set(terms(OWL.ObjectProperty)) | set(terms(OWL.DatatypeProperty)), key=str)
    individuals = terms(OWL.NamedIndividual)
    version = text_of(graph, ONTOLOGY, OWL.versionInfo)
    version_iri = str(graph.value(ONTOLOGY, OWL.versionIRI) or "")
    note = text_of(graph, ONTOLOGY, URIRef("http://www.w3.org/2004/02/skos/core#note"))
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>AgentPROV vocabulary (apv) {html.escape(version)}</title>",
        f'<link rel="alternate" type="text/turtle" href="apv.ttl"><style>{STYLE}</style></head><body>',
        f"<h1>AgentPROV vocabulary (<code>apv:</code>) {html.escape(version)}</h1>",
        f"<p>{html.escape(text_of(graph, ONTOLOGY, RDFS.comment))}</p>",
        "<ul>",
        "<li>Namespace: <code>https://w3id.org/agentprov/ns#</code></li>",
        f"<li>This version: <code>{html.escape(version_iri)}</code></li>",
        '<li>Machine-readable: <a href="apv.ttl">apv.ttl</a> (Turtle; also served for <code>Accept: text/turtle</code>)</li>',
        '<li>Licence: <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></li>',
        f"<li>{len(classes)} classes, {len(props)} properties, {len(individuals)} individuals</li>",
        "</ul>",
    ]
    if note:
        out.append(f'<p class="note">{html.escape(note)}</p>')
    out += [
        "<p>The vocabulary qualifies W3C PROV statements about LLM-agent executions with an evidence class (observed, "
        "derived or inferred), the identifier of the rule that produced each statement, a pointer to the execution-record "
        "field that justifies it, and explicit statuses for information that is unknown, not recorded or not observable. "
        "Instance IRIs never live in this namespace.</p>",
        '<p><a href="#classes">Classes</a> · <a href="#properties">Properties</a> · '
        '<a href="#individuals">Individuals</a></p>',
        '<h2 id="classes">Classes</h2><table><tr><th>Term</th><th>Subclass of</th><th>Description</th></tr>',
    ]
    for c in classes:
        supers = " ".join(link(o) for o in sorted(graph.objects(c, RDFS.subClassOf), key=str))
        out.append(f'<tr id="{html.escape(curie(c)[4:])}"><td>{link(c)}</td><td>{supers}</td>'
                   f"<td>{html.escape(text_of(graph, c, RDFS.comment))}</td></tr>")
    out += ["</table>", '<h2 id="properties">Properties</h2>',
            "<table><tr><th>Term</th><th>Kind</th><th>Range</th><th>Description</th></tr>"]
    for p in props:
        kind = "object" if (p, RDF.type, OWL.ObjectProperty) in graph else "datatype"
        ranges = " ".join(link(o) for o in sorted(graph.objects(p, RDFS.range), key=str))
        out.append(f'<tr id="{html.escape(curie(p)[4:])}"><td>{link(p)}</td><td>{kind}</td><td>{ranges}</td>'
                   f"<td>{html.escape(text_of(graph, p, RDFS.comment))}</td></tr>")
    out += ["</table>", '<h2 id="individuals">Individuals</h2>',
            "<table><tr><th>Term</th><th>Type</th><th>Description</th></tr>"]
    for i in individuals:
        types = " ".join(link(o) for o in sorted(graph.objects(i, RDF.type), key=str) if o != OWL.NamedIndividual)
        out.append(f'<tr id="{html.escape(curie(i)[4:])}"><td>{link(i)}</td><td>{types}</td>'
                   f"<td>{html.escape(text_of(graph, i, RDFS.comment))}</td></tr>")
    out += ["</table>", "</body></html>", ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=Path, help="write the page here")
    group.add_argument("--check", type=Path, help="exit 1 if this page differs from a fresh render")
    args = parser.parse_args()
    page = render(Graph().parse(TTL, format="turtle")).encode("utf-8")
    if args.check is not None:
        same = args.check.is_file() and args.check.read_bytes() == page
        print("up to date" if same else f"{args.check} is stale", file=sys.stderr)
        return 0 if same else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(page)
    print(f"wrote {args.out} ({len(page)} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
