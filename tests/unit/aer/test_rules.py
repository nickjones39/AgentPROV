"""C.6.4 / D.5: rule references, the shipped ``aer`` catalogue, the registry and the catalogue self-test."""

from __future__ import annotations

import pytest

from agentprov.aer.accounting import CORE_CHECK_IDS
from agentprov.aer.rules import (
    CatalogueError,
    CatalogueUnavailableError,
    RuleCatalogue,
    RuleRegistry,
    load_catalogue,
    parse_catalogue,
    parse_rule_ref,
    rule_id_of,
)


@pytest.mark.parametrize(
    "good",
    ["agentdojo.context_is_prefix@1", "aer.acc.reported_counts@1", "a.b@12#/input", "a.b@1#/a/b~1c", "x.y_z@9#/"],
)
def test_rule_reference_grammar_accepts(good: str) -> None:
    assert parse_rule_ref(good).text == good


@pytest.mark.parametrize(
    "bad",
    ["", "noversion", "a@1", "a.b@0", "a.b@01", "A.b@1", "a.b@1#", "a.b@1#x", "a.b@1 ", "a..b@1", "a.b@1\n", ".b@1"],
)
def test_rule_reference_grammar_rejects(bad: str) -> None:
    with pytest.raises(ValueError, match="."):
        parse_rule_ref(bad)


def test_rule_id_is_the_reference_without_pointer() -> None:
    assert rule_id_of("agentdojo.context_is_prefix@1#/input") == "agentdojo.context_is_prefix@1"
    ref = parse_rule_ref("aer.acc.reported_counts@3#/usage")
    assert (ref.namespace, ref.name, ref.version, ref.pointer) == ("aer", "acc.reported_counts", 3, "/usage")
    assert ref.rule_id == "aer.acc.reported_counts@3"


def test_shipped_aer_catalogue_declares_every_cited_rule_and_check() -> None:
    cat = load_catalogue("aer", 1)
    assert (cat.namespace, cat.version) == ("aer", 1)
    for rid in (
        "aer.output_after_generator@1",
        "aer.execution_after_call@1",
        "aer.decision_after_subject@1",
        "aer.time_order@1",
        *CORE_CHECK_IDS,
        "aer.acc.passes_closed@1",
        "aer.acc.dispatch_vs_results@1",
        "aer.acc.env_recorded@1",
        "aer.acc.capture_chain@1",
    ):
        entry = cat.get(rid)
        assert entry is not None and entry.cls == "D" and entry.citable, rid
    assert len(cat.digest) == 64


def test_catalogue_is_loaded_from_package_data_and_unknown_ones_are_unavailable() -> None:
    assert load_catalogue("aer").version == 1
    with pytest.raises(CatalogueUnavailableError) as info:
        load_catalogue("aer", 2)
    assert info.value.code == "rules.unavailable"
    with pytest.raises(CatalogueUnavailableError):
        load_catalogue("nonexistent_family")
    with pytest.raises(CatalogueUnavailableError):
        load_catalogue("../aer")


def test_registry_lookup_respects_declared_versions() -> None:
    registry = RuleRegistry.default()
    assert registry.lookup("aer.time_order@1", {"aer": 1}) is not None
    assert registry.lookup("aer.time_order@1", {}) is None  # namespace not declared in the header
    assert registry.lookup("aer.time_order@2", {"aer": 1}) is None
    assert registry.lookup("aer.time_order@1", {"aer": 9}) is None  # catalogue version not shipped
    assert registry.lookup("not a rule id", {"aer": 1}) is None
    assert registry.has("aer", 1) and not registry.has("aer", 2)


def test_registry_without_autoload_only_knows_added_catalogues() -> None:
    registry = RuleRegistry(autoload=False)
    with pytest.raises(CatalogueUnavailableError):
        registry.get("aer", 1)
    registry.add(load_catalogue("aer", 1))
    assert registry.get("aer", 1).namespace == "aer"


GOOD = b"""
[catalogue]
id = "tst"
version = 2
issue_codes = ["odd"]
subtypes = ["tst.sub"]
types = ["tst:plan"]

[[assumption]]
id = "tst:SingleLlm"

[[rule]]
id = "tst.a"
version = 1
class = "I"
assumptions = ["tst:SingleLlm"]
verification = [{ assumption = "tst:SingleLlm", status = "asserted" }]

[[rule]]
id = "tst.b"
version = 1
class = "D"
assumptions = ["apv:LastPassOnlyLogging"]
verification = [{ assumption = "apv:LastPassOnlyLogging", status = "verified", framework_identity = ["git:r@%s"], code_ref = "f.py", test = "t.py::t" }]
code = [{ repo = "r", commit = "%s", path = "p" }]
""" % (b"a" * 40, b"a" * 40)


def test_parse_catalogue_accepts_a_wellformed_file() -> None:
    cat = parse_catalogue(GOOD)
    assert isinstance(cat, RuleCatalogue)
    assert cat.get("tst.a@1").cls == "I"  # type: ignore[union-attr]
    entry = cat.get("tst.b@1")
    assert entry is not None and entry.verified_identities() == ("git:r@" + "a" * 40,)
    assert cat.declares_issue_code("tst.odd") and not cat.declares_issue_code("tst.other")
    assert not cat.declares_issue_code("other.odd")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b'id = "tst"', b'id = "tst.rules"'),
        (b"version = 2", b"version = 0"),
        (b'class = "I"', b'class = "O"'),
        (b'id = "tst.b"', b'id = "tst.a"'),  # duplicate (id, version)
        (b'id = "tst.b"', b'id = "other.b"'),  # wrong namespace
        (b'class = "D"', b'class = "D"\nstatus = "weird"'),
        (b'assumptions = ["tst:SingleLlm"]', b'assumptions = ["tst:Undeclared"]'),
        (b'status = "asserted" }', b'status = "asserted" }, { assumption = "tst:SingleLlm", status = "asserted" }'),
        (b'code_ref = "f.py", ', b""),  # verified without code_ref
        (b'commit = "' + b"a" * 40 + b'", path', b'commit = "abc", path'),
    ],
)
def test_parse_catalogue_rejects_violations(old: bytes, new: bytes) -> None:
    with pytest.raises(CatalogueError):
        parse_catalogue(GOOD.replace(old, new, 1))


def test_a_class_d_rule_may_only_have_verified_assumptions() -> None:
    bad = GOOD.replace(b'class = "I"', b'class = "D"', 1)
    with pytest.raises(CatalogueError, match="verified"):
        parse_catalogue(bad)


def test_non_toml_is_a_catalogue_error() -> None:
    with pytest.raises(CatalogueError):
        parse_catalogue(b"\xff\xfe not toml")


def test_loaded_catalogues_are_parsed_once_per_source_and_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """pipeline-perf: ``load_catalogue`` caches the parse by (source, sha256 of the bytes). Equal bytes give the same,
    equal catalogue without parsing again; changed bytes are parsed again; bytes that fail to parse are never cached."""
    import agentprov.aer.rules as rules

    served = {"rules/tst.rules.toml": GOOD}
    monkeypatch.setattr(rules, "_read_resource", lambda _package, relative: served.get(relative))
    monkeypatch.setattr(rules, "_PARSED", {})
    calls: list[str] = []
    real = rules.parse_catalogue

    def counting(data: bytes, *, source: str = "<bytes>") -> RuleCatalogue:
        calls.append(source)
        return real(data, source=source)

    monkeypatch.setattr(rules, "parse_catalogue", counting)
    first = load_catalogue("tst", package="agentprov.adapters.tst")
    assert first == parse_catalogue(GOOD, source="agentprov.adapters.tst:rules/tst.rules.toml")
    assert load_catalogue("tst", package="agentprov.adapters.tst") is first
    assert load_catalogue("tst", 2, package="agentprov.adapters.tst") is first
    assert len(calls) == 1
    served["rules/tst.rules.toml"] = GOOD.replace(b"version = 2", b"version = 3", 1)
    assert load_catalogue("tst", package="agentprov.adapters.tst").version == 3  # new bytes: parsed again
    assert len(calls) == 2
    served["rules/tst.rules.toml"] = b"\xff\xfe not toml"
    for _ in range(2):
        with pytest.raises(CatalogueError):
            load_catalogue("tst", package="agentprov.adapters.tst")
    assert len(calls) == 4 and len(rules._PARSED) == 2


def test_a_cached_catalogue_cannot_be_changed_by_a_caller() -> None:
    """Regen item 33 (bug pass BF-5): the D-410 cache hands every caller the same catalogue, so its rules are read-only;
    a caller that tried to drop or replace a rule would have changed every later load in the process."""
    catalogue = load_catalogue("aer")
    rid = next(iter(catalogue.rules))
    count = len(catalogue.rules)
    with pytest.raises(TypeError):
        catalogue.rules[rid] = catalogue.rules[rid]  # type: ignore[index]
    assert not hasattr(catalogue.rules, "pop")
    again = load_catalogue("aer")
    assert again is catalogue and len(again.rules) == count and rid in again.rules
