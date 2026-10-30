#!/usr/bin/env python3
"""Generate ``src/agentprov/prov/vocab.py`` (apv term constants) from ``src/agentprov/vocab/apv-0.2.ttl``.

The generated module is pure constants (no rdflib at runtime): the sets of class, property and individual local
names declared by the ontology, written out literally so that a reviewer sees every term change in a diff.

    uv run python tools/gen_vocab_py.py            # (re)write src/agentprov/prov/vocab.py
    uv run python tools/gen_vocab_py.py --check    # exit 1 if vocab.py is not what the TTL generates
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdflib import OWL, RDF, Graph, URIRef

REPO = Path(__file__).resolve().parents[1]
TTL = REPO / "src" / "agentprov" / "vocab" / "apv-0.2.ttl"
OUT = REPO / "src" / "agentprov" / "prov" / "vocab.py"
APV_NS = "https://w3id.org/agentprov/ns#"
ONTOLOGY = URIRef("https://w3id.org/agentprov/ns")
WIDTH = 110


def load_terms(ttl: Path = TTL) -> tuple[str, dict[str, list[str]]]:
    """Return (version, {"CLASSES"|"PROPERTIES"|"INDIVIDUALS": sorted local names}) declared in ``ttl``."""
    graph = Graph()
    graph.parse(ttl, format="turtle")
    versions = [str(o) for o in graph.objects(ONTOLOGY, OWL.versionInfo)]
    if len(versions) != 1:
        raise SystemExit(f"{ttl}: expected exactly one owl:versionInfo, found {versions}")

    def local_names(*kinds: URIRef) -> list[str]:
        names: set[str] = set()
        for kind in kinds:
            for subject in graph.subjects(RDF.type, kind):
                if isinstance(subject, URIRef) and str(subject).startswith(APV_NS):
                    names.add(str(subject)[len(APV_NS) :])
        return sorted(names)

    return versions[0], {
        "CLASSES": local_names(OWL.Class),
        "PROPERTIES": local_names(OWL.ObjectProperty, OWL.DatatypeProperty),
        "INDIVIDUALS": local_names(OWL.NamedIndividual),
    }


def _frozenset_literal(name: str, annotation: str, names: list[str]) -> list[str]:
    lines = [f"{name}: {annotation} = frozenset(", "    {"]
    row = "        "
    for local in names:
        item = f'"{local}", '
        if len(row) + len(item.rstrip()) > WIDTH:
            lines.append(row.rstrip())
            row = "        "
        row += item
    if row.strip():
        lines.append(row.rstrip())
    lines += ["    }", ")"]
    return lines


def render(ttl: Path = TTL) -> str:
    version, groups = load_terms(ttl)
    out = [
        '"""apv term constants, generated from vocab/apv-0.2.ttl. Do not edit by hand.',
        "",
        "Regenerate with ``uv run python tools/gen_vocab_py.py``; ``--check`` fails when this file is stale",
        "(docs/architecture EF E.4). The module is pure constants: it never imports rdflib. Names are local",
        "names in the ``apv`` namespace; :func:`term` returns the QName used in PROV-JSON.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        '__all__ = ["APV_NS", "CLASSES", "INDIVIDUALS", "PROPERTIES", "VOCAB_VERSION", "term"]',
        "",
        f'APV_NS = "{APV_NS}"',
        f'VOCAB_VERSION = "{version}"',
        "",
    ]
    for key, annotation in (
        ("CLASSES", "frozenset[str]"),
        ("PROPERTIES", "frozenset[str]"),
        ("INDIVIDUALS", "frozenset[str]"),
    ):
        out += _frozenset_literal(key, annotation, groups[key])
        out.append("")
    out += [
        "_ALL = CLASSES | PROPERTIES | INDIVIDUALS",
        "",
        "",
        "def term(local: str) -> str:",
        '    """Return ``"apv:" + local`` for a declared term; raise :class:`KeyError` for an undeclared one."""',
        "    if local not in _ALL:",
        '        raise KeyError(f"apv:{local} is not declared in apv {VOCAB_VERSION}")',
        '    return "apv:" + local',
        "",
    ]
    return "\n".join(out)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if vocab.py is stale")
    args = parser.parse_args(argv)

    text = render()
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print(f"{_rel(OUT)} is stale; run tools/gen_vocab_py.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {_rel(OUT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
