"""Derived PROV documents and the apv graph for the vocabulary/output consistency tests (D-500, D-501; EF E.4, E.5).

The inputs are the ones the existing PROV tests use:

- the four C.16 vectors (``docs/architecture/examples/C``; C.16.3 with the synthetic ``stac`` catalogue of
  ``aer_support.vector_registry``, the others with the package catalogues);
- the generic-kind construct AER of ``prov_support`` (F.2.6);
- every golden v1 pair mapped with profile ``adprov-v1`` (as ``tests/golden/test_prov_derive.py`` and
  ``tests/prov/conftest.py`` map them), skipped with the golden reason when the fixtures are absent;
- the assessment bundle of ``tests/prov/test_assessment_golden.py`` on pair R04 (every E.7.3 row).

Documents are returned as canonical PROV-JSON bytes; nothing is written outside the caller's temporary directory.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from functools import cache
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any

from rdflib import Graph

from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.aer.reader import load_aer
from agentprov.prov.engine import derive
from agentprov.prov.vocab import VOCAB_VERSION

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tests" / "unit" / "aer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402
from aer_support import VECTOR_NAMES, vector_path, vector_registry  # noqa: E402

APV = "https://w3id.org/agentprov/ns#"
QNAME = "prov:QUALIFIED_NAME"
GOLDEN_MODULE = REPO / "tests" / "golden" / "test_v1_round_trip.py"
ASSESSMENT_MODULE = REPO / "tests" / "prov" / "test_assessment_golden.py"
ASSESSMENT_PAIR = "R04"


def vocab_ttl() -> Path:
    """The package ontology file of the current apv version (``vocab/apv-<major>.<minor>.ttl``, E.4.6 item 1)."""
    major, minor, _patch = VOCAB_VERSION.split(".")
    return Path(str(resources.files("agentprov") / "vocab" / f"apv-{major}.{minor}.ttl"))


@cache
def vocab_graph() -> Graph:
    graph = Graph()
    graph.parse(data=vocab_ttl().read_text(encoding="utf-8"), format="turtle")
    return graph


def _module(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def golden_module() -> ModuleType:
    """``tests/golden/test_v1_round_trip.py`` under the name ``tests/prov/conftest.py`` loads it with."""
    return _module("agentprov_tests_golden_v1_pairs", GOLDEN_MODULE)


def vector_documents() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for name in VECTOR_NAMES:
        aer = load_aer(vector_path(name))
        result = derive(aer, registry=vector_registry()) if name == "stac_case_223" else derive(aer)
        out[f"C:{name}"] = result.prov_json
    return out


def generic_document(tmp: Path) -> dict[str, bytes]:
    doc = ps.write_aer(ps.generic_records(), tmp / "generic.aer.jsonl")
    return {"generic": derive(doc, registry=ps.registry()).prov_json}


def golden_documents(tmp: Path) -> dict[str, bytes]:
    """Every golden pair, plus the R04 assessment document (``golden:<id>``, ``assess:R04``). Skips without fixtures."""
    v1 = golden_module()
    v1._require()
    out: dict[str, bytes] = {}
    for pair in v1.PAIRS:
        outcome, _ = map_artefact(v1._source(pair), v1._origin(pair), profile_id="adprov-v1")
        data, _ = aer_bytes(outcome)
        path = tmp / f"{pair.id}.aer.jsonl"
        path.write_bytes(data)
        aer = load_aer(path)
        out[f"golden:{pair.id}"] = derive(aer).prov_json
        if pair.id == ASSESSMENT_PAIR:
            assessment = _module("agentprov_tests_vocab_assessment_golden", ASSESSMENT_MODULE)
            out[f"assess:{pair.id}"] = assessment.Golden(aer).result.prov_json
    return out


def bodies(document: dict[str, Any]) -> Iterator[tuple[str, str, str, dict[str, Any]]]:
    """``(scope, section, identifier, attributes)`` for every record, top level (scope ``""``) and in every bundle."""
    scopes = [("", document)] + [(iri, b) for iri, b in document.get("bundle", {}).items()]
    for scope, container in scopes:
        for section, items in container.items():
            if section in ("prefix", "bundle") or not isinstance(items, dict):
                continue
            for ident, body in items.items():
                if isinstance(body, dict):
                    yield scope, section, ident, body
                elif isinstance(body, list):  # several records under one identifier
                    for item in body:
                        yield scope, section, ident, item


def values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def qname(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("type") == QNAME and isinstance(value.get("$"), str):
        return value["$"]
    return None


def decode(prov_json: bytes) -> dict[str, Any]:
    doc = json.loads(prov_json)
    assert isinstance(doc, dict)
    return doc
