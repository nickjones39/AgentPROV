"""The ``apv`` ontology 0.2.0 and its tooling (docs/architecture EF E.4; PQ phase 5; D-500/D-501 minor bump).

Covers the Turtle file, its published copy ``docs/ns/apv-0.2.ttl`` (the 0.1.0 release stays published as
``docs/ns/apv-0.1.ttl``), the generated constants
``agentprov.prov.vocab`` and the frozen-adprov mapping ``apv-adprov-map-0.1.ttl``.
"""

from __future__ import annotations

import ast
import importlib.util
from importlib import resources
from pathlib import Path
from types import ModuleType

import pytest
from rdflib import OWL, RDF, RDFS, SKOS, Graph, Literal, URIRef
from rdflib.namespace import PROV

from agentprov.prov import vocab

REPO = Path(__file__).resolve().parents[3]
VOCAB_DIR = resources.files("agentprov") / "vocab"
TTL = VOCAB_DIR / "apv-0.2.ttl"
MAP_TTL = VOCAB_DIR / "apv-adprov-map-0.1.ttl"
ADPROV_TTL = REPO / "src" / "agentprov" / "prov" / "compat" / "adprov_v2_3" / "adprov.ttl"
DOCS_COPY = REPO / "docs" / "ns" / "apv-0.2.ttl"
PUBLISHED_0_1 = REPO / "docs" / "ns" / "apv-0.1.ttl"

APV = "https://w3id.org/agentprov/ns#"
ADPROV = "https://nickjones39.github.io/agentdojo-prov/ns#"
ONTOLOGY = URIRef("https://w3id.org/agentprov/ns")
PROPERTY_TYPES = (OWL.ObjectProperty, OWL.DatatypeProperty)
TERM_TYPES = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.NamedIndividual)


def _load(path: object) -> Graph:
    graph = Graph()
    graph.parse(data=path.read_text(encoding="utf-8"), format="turtle")  # type: ignore[attr-defined]
    return graph


@pytest.fixture(scope="module")
def graph() -> Graph:
    return _load(TTL)


def _tool(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_tool_{name}", REPO / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apv_subjects(graph: Graph) -> set[URIRef]:
    return {s for s in graph.subjects() if isinstance(s, URIRef) and str(s).startswith(APV)}


def _local(graph: Graph, *kinds: URIRef) -> set[str]:
    return {str(s)[len(APV) :] for k in kinds for s in graph.subjects(RDF.type, k) if str(s).startswith(APV)}


def test_ontology_header(graph: Graph) -> None:
    assert (ONTOLOGY, RDF.type, OWL.Ontology) in graph
    assert set(graph.objects(ONTOLOGY, OWL.versionInfo)) == {Literal("0.2.0")}
    assert set(graph.objects(ONTOLOGY, OWL.versionIRI)) == {URIRef("https://w3id.org/agentprov/ns/0.2.0")}
    prior = URIRef("https://w3id.org/agentprov/ns/0.1.0")
    assert set(graph.objects(ONTOLOGY, OWL.priorVersion)) == {prior}
    assert set(graph.objects(ONTOLOGY, OWL.backwardCompatibleWith)) == {prior}
    assert any(graph.objects(ONTOLOGY, RDFS.label)) and any(graph.objects(ONTOLOGY, RDFS.comment))
    assert URIRef("https://creativecommons.org/licenses/by/4.0/") in set(graph.objects(ONTOLOGY, URIRef("http://purl.org/dc/terms/license")))
    assert URIRef("https://github.com/nickjones39") in set(graph.objects(ONTOLOGY, URIRef("http://purl.org/dc/terms/creator")))
    notes = " ".join(str(o) for o in graph.objects(ONTOLOGY, SKOS.note))
    assert "registered" in notes and "6836" in notes and "pending" not in notes and "placeholder" not in notes


def test_resource_is_readable_through_importlib_resources() -> None:
    assert TTL.is_file() and MAP_TTL.is_file()
    assert (REPO / "src" / "agentprov" / "vocab" / "__init__.py").exists() is False


def test_constants_match_the_ttl_both_ways(graph: Graph) -> None:
    assert vocab.APV_NS == APV and vocab.VOCAB_VERSION == "0.2.0"
    assert set(vocab.CLASSES) == _local(graph, OWL.Class)
    assert set(vocab.PROPERTIES) == _local(graph, *PROPERTY_TYPES)
    assert set(vocab.INDIVIDUALS) == _local(graph, OWL.NamedIndividual)
    assert not vocab.CLASSES & vocab.PROPERTIES and not vocab.CLASSES & vocab.INDIVIDUALS
    assert not vocab.PROPERTIES & vocab.INDIVIDUALS


def test_term_checks_membership() -> None:
    assert vocab.term("ModelInvocation") == "apv:ModelInvocation"
    assert vocab.term("evidenceClass") == "apv:evidenceClass"
    assert vocab.term("Observed") == "apv:Observed"
    for undeclared in ("Unknown", "CheckerReadsFinalState", "modelinvocation", "", "apv:Observed"):
        with pytest.raises(KeyError):
            vocab.term(undeclared)


def test_vocab_module_has_no_runtime_rdflib_import() -> None:
    tree = ast.parse((REPO / "src" / "agentprov" / "prov" / "vocab.py").read_text(encoding="utf-8"))
    imported = {
        n.module if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [None])
    }
    assert not any(m and m.split(".")[0] == "rdflib" for m in imported)


def test_docs_copy_is_byte_identical() -> None:
    assert DOCS_COPY.read_bytes() == (REPO / "src" / "agentprov" / "vocab" / "apv-0.2.ttl").read_bytes()


def test_the_0_1_release_stays_published_and_0_2_only_adds_terms(graph: Graph) -> None:
    """E.4.6 item 2: a minor version adds terms. Every 0.1.0 term is still declared in 0.2.0 with the same types."""
    old = _load(PUBLISHED_0_1)
    assert set(old.objects(ONTOLOGY, OWL.versionInfo)) == {Literal("0.1.0")}
    for subject in _apv_subjects(old):
        assert set(old.objects(subject, RDF.type)) == set(graph.objects(subject, RDF.type)), subject
        assert set(old.objects(subject, RDFS.range)) == set(graph.objects(subject, RDFS.range)), subject


def test_apv_namespace_holds_only_terms(graph: Graph) -> None:
    for subject in _apv_subjects(graph):
        types = set(graph.objects(subject, RDF.type))
        assert types & set(TERM_TYPES), f"{subject} is in the vocabulary namespace but is not a term"
    # the ontology IRI is not in the apv# namespace; nothing else is declared outside it
    for subject in set(graph.subjects()):
        if isinstance(subject, URIRef) and not str(subject).startswith(APV):
            assert subject == ONTOLOGY, f"unexpected subject {subject}"


def test_every_term_is_documented(graph: Graph) -> None:
    for subject in _apv_subjects(graph):
        assert any(graph.objects(subject, RDFS.label)), f"{subject}: no rdfs:label"
        assert any(graph.objects(subject, RDFS.comment)), f"{subject}: no rdfs:comment"
        assert set(graph.objects(subject, RDFS.isDefinedBy)) == {ONTOLOGY}, f"{subject}: isDefinedBy"


def _superclasses(graph: Graph, cls: URIRef) -> set[URIRef]:
    seen: set[URIRef] = set()
    todo = [cls]
    while todo:
        for sup in graph.objects(todo.pop(), RDFS.subClassOf):
            if isinstance(sup, URIRef) and sup not in seen:
                seen.add(sup)
                todo.append(sup)
    return seen


def test_every_class_chains_to_a_prov_class_or_is_a_closed_list_type(graph: Graph) -> None:
    closed_lists = set()
    for cls in graph.subjects(RDF.type, OWL.Class):
        assert isinstance(cls, URIRef)
        supers = _superclasses(graph, cls)
        if any(str(s).startswith(str(PROV)) for s in supers):
            continue
        # the only classes outside PROV are the closed-list (enumeration) types, rooted at skos:Concept
        assert SKOS.Concept in supers, f"{cls} has no PROV superclass"
        closed_lists.add(cls)
    assert len(closed_lists) == 17
    # every closed-list type has members, and every individual is a member of one or is a prov:Role
    members = {m for c in closed_lists for m in graph.subjects(RDF.type, c)}
    for c in closed_lists:
        assert any(graph.subjects(RDF.type, c)), f"{c} has no members"
    for ind in graph.subjects(RDF.type, OWL.NamedIndividual):
        assert ind in members or (ind, RDF.type, PROV.Role) in graph, f"{ind} has no list"


@pytest.mark.parametrize(
    ("name", "prov_class"),
    [
        ("ModelInvocation", PROV.Activity),
        ("ToolExecution", PROV.Activity),
        ("Message", PROV.Entity),
        ("ToolCallRequest", PROV.Entity),
        ("AttackPlan", PROV.Plan),
        ("RuleCatalogue", PROV.Plan),
        ("SemanticsProfile", PROV.Plan),
        ("ContextWindow", PROV.Dictionary),
        ("CoreBundle", PROV.Bundle),
        ("InferenceBundle", PROV.Bundle),
        ("AssessmentBundle", PROV.Bundle),
        ("Planner", PROV.Agent),
        ("Generator", PROV.Agent),
        ("AgentSystem", PROV.Agent),
    ],
)
def test_class_superclasses_from_the_spec(graph: Graph, name: str, prov_class: URIRef) -> None:
    assert prov_class in _superclasses(graph, URIRef(APV + name))


def test_message_role_part_state_fixture_subclasses(graph: Graph) -> None:
    for sub, sup in [
        ("SystemMessage", "Message"),
        ("OtherRoleMessage", "Message"),
        ("UriPart", "MessagePart"),
        ("SandboxState", "State"),
        ("GroundTruth", "Fixture"),
        ("AttackPlan", "Fixture"),
    ]:
        assert (URIRef(APV + sub), RDFS.subClassOf, URIRef(APV + sup)) in graph


def test_closed_lists_have_the_specified_sizes(graph: Graph) -> None:
    def members(cls: str) -> set[str]:
        return {str(s)[len(APV) :] for s in graph.subjects(RDF.type, URIRef(APV + cls))}

    assert members("EvidenceClass") == {"Observed", "Derived", "Inferred"}
    assert len(members("AttestingParty")) == 6
    assert len(members("EpistemicStatus")) == 9
    assert len(members("Assumption")) == 19
    assert len(members("SentTransform")) == 6
    assert members("CallStatus") == {"Kept", "Discarded", "Error", "Cached"}
    assert members("ExecutionStatus") == {"Ok", "Error", "Invalid"}
    assert members("DispatchStatus") == {"NotDispatched", "Denied"}
    assert len(members("OutcomeOrigin")) == 4 and len(members("Verdict")) == 7
    assert len(members("IntegrityValue")) == 3 and len(members("SecurityRole")) == 9
    assert len(members("AssessmentClaim")) == 7 and members("ProfileStatus") == {"RegressionOracle"}
    assert len(members("Capability")) == 18
    assert members("MarkerStatus") == {"Ambiguous"}
    roles = {str(s)[len(APV) :] for s in graph.subjects(RDF.type, PROV.Role)}
    assert len(roles) == 22 and {"ContextMessage", "ContextWindowRole"} <= roles


def test_shared_individuals_are_declared_once_with_both_types(graph: Graph) -> None:
    error = URIRef(APV + "Error")
    assert {APV + "CallStatus", APV + "ExecutionStatus"} <= {str(t) for t in graph.objects(error, RDF.type)}
    ambiguous = {str(t) for t in graph.objects(URIRef(APV + "Ambiguous"), RDF.type)}
    assert {APV + "EpistemicStatus", APV + "MarkerStatus"} <= ambiguous


def test_withdrawn_terms_are_not_declared(graph: Graph) -> None:
    # apv:Unknown never appears; apv:CheckerReadsFinalState was replaced by the four checker-input assumptions
    for name in ("Unknown", "CheckerReadsFinalState", "KnownAbsent"):
        assert URIRef(APV + name) not in set(graph.subjects())


def test_rule_ids_are_string_properties(graph: Graph) -> None:
    xsd_string = URIRef("http://www.w3.org/2001/XMLSchema#string")
    for name in ("rule", "basisRule", "rulePointer", "method"):
        node = URIRef(APV + name)
        assert (node, RDF.type, OWL.DatatypeProperty) in graph
        assert (node, RDFS.range, xsd_string) in graph


@pytest.mark.parametrize(
    "name",
    [
        "evidenceClass", "attestedBy", "assumption", "premise", "viaEntity", "partOf", "retryOf",
        "afterCausal", "afterTime", "afterPos", "afterProto", "afterEvidenceClass", "callStatus", "execStatus",
        "verdict", "outcomeOrigin", "subject", "object", "claim", "provides", "notProvided", "notObservable",
        "derivedAttribute", "decisionSubject", "sentTransform", "dispatchStatus", "contentStatus", "integrity",
        "securityRole", "markerStatus", "status", "about", "startTimeStatus", "outputStatus", "orderStatus",
    ],
)
def test_qname_valued_properties_are_object_properties(graph: Graph, name: str) -> None:
    assert (URIRef(APV + name), RDF.type, OWL.ObjectProperty) in graph


def test_engine_terms_are_declared() -> None:
    engine = {
        "scopeStatus", "activityStatus", "outputStatus", "inputIndex", "mediaType", "durationSeconds",
        "startTimeLexical", "endTimeLexical", "about", "property", "status", "reason", "issue", "accounting",
        "executionId", "thread", "outcomeValue", "usage", "paramsConfigured", "paramsTransmitted",
        "argsEffective", "exception", "requestBlob", "responseBlob", "responseId", "asSentSha256",
        "contextIndex", "afterEvidenceClass", "messageRole", "subtype", "contentLength",
    }
    assert engine <= vocab.PROPERTIES
    for name in ("CacheRead", "RegressionOracle", "Overwritten", "RecordedNull", "NotObservable", "declaredSender",
                 "sentTransform", "LastPassOnlyLogging", "EnvironmentCarriedOver", "GenericActivity",
                 "GenericArtefact"):
        assert name in vocab.CLASSES | vocab.PROPERTIES | vocab.INDIVIDUALS


def test_generated_constants_are_current() -> None:
    assert _tool("gen_vocab_py").main(["--check"]) == 0


def test_published_copy_is_current() -> None:
    assert _tool("sync_ns").main(["--check"]) == 0


def test_sync_ns_check_fails_on_a_stale_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _tool("sync_ns")
    stale = tmp_path / "apv-0.2.ttl"
    stale.write_bytes(DOCS_COPY.read_bytes() + b"# drift\n")
    monkeypatch.setattr(tool, "TARGET", stale)
    assert tool.main(["--check"]) == 1
    assert stale.read_bytes().endswith(b"# drift\n")  # --check never writes


def test_gen_vocab_check_fails_on_a_stale_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _tool("gen_vocab_py")
    stale = tmp_path / "vocab.py"
    stale.write_text("# stale\n", encoding="utf-8")
    monkeypatch.setattr(tool, "OUT", stale)
    assert tool.main(["--check"]) == 1


# ---- apv-adprov-map-0.1.ttl ------------------------------------------------------------------------------


def test_adprov_map_is_closeMatch_only_and_points_at_declared_terms(graph: Graph) -> None:
    mapping = _load(MAP_TTL)
    adprov = _load(ADPROV_TTL)
    banned = {OWL.equivalentProperty, OWL.equivalentClass, RDFS.subPropertyOf, RDFS.subClassOf, OWL.sameAs}
    assert not {p for _, p, _ in mapping} & banned
    matches = [
        (s, p, o)
        for s, p, o in mapping
        if p in (SKOS.closeMatch, SKOS.relatedMatch, SKOS.exactMatch)
    ]
    assert matches and all(p != SKOS.exactMatch for _, p, _ in matches)
    adprov_terms = {s for s in adprov.subjects(RDF.type, OWL.DatatypeProperty)}
    for s, _, o in matches:
        assert s in adprov_terms, f"{s} is not a term of the frozen adprov.ttl"
        assert isinstance(o, URIRef) and str(o).startswith(APV) and (o, None, None) in graph, o
    # every adprov term is accounted for: matched, or explained by a skos:note
    for term in adprov_terms:
        assert any(mapping.objects(term, SKOS.closeMatch)) or any(mapping.objects(term, SKOS.relatedMatch)) or any(
            mapping.objects(term, SKOS.note)
        ), f"{term} is not mapped or explained"
    # every mapped or noted term carries a comment or a note on how the semantics changed
    for s in {s for s, _, _ in matches}:
        assert any(mapping.objects(s, RDFS.comment)), f"{s}: no rdfs:comment"
    assert set(mapping.objects(None, SKOS.closeMatch)) >= {
        URIRef(APV + n) for n in ("integrity", "securityRole", "sourceChannel", "contentSha256", "contentLength")
    }
    assert {str(s) for s in mapping.subjects() if str(s).startswith(ADPROV)} <= {str(t) for t in adprov_terms}


def test_adprov_map_header() -> None:
    mapping = _load(MAP_TTL)
    ontology = URIRef("https://w3id.org/agentprov/ns/adprov-map")
    assert (ontology, RDF.type, OWL.Ontology) in mapping
    assert set(mapping.objects(ontology, OWL.versionInfo)) == {Literal("0.1.0")}
