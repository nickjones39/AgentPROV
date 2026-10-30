"""The phase-10d AgentDojo-format source profiles (D-100..D-109; shortlist D-90..D-96; docs/architecture D.4, D.5.4, D.6).

For every source of ``phase10d_support.SOURCES``: the profile's pin, licence and registry part (``planned``, D.3.2); the
closed family schema; quirk rules and census functions; the identity resolution of its directories; and D-24: no harness
code is verified, so every family D rule a record cites is its ``_unverified`` twin (class I), for the real fixtures and
for a synthetic log in the source's layout. The real fixtures' AER bytes are pinned in ``phase10d_aer_digests.json``
(regenerate with ``AGENTPROV_REGEN_AGENTDOJO_AER=1``). The five copyleft sources have synthetic fixtures in place of real
ones (D-945, ``phase10d_synthetic.py``): the same tests run on them, with their provenance checked instead of a licence text.
"""

from __future__ import annotations

import json
import os

import pytest
from phase10d_support import (
    DIGESTS,
    FIXTURES,
    REGEN,
    SOURCES,
    Source,
    d_rules_cited_at_d,
    fixture_bytes,
    fixture_entries,
    is_synthetic,
    layout_path,
    map_doc,
    map_fixture,
    ok,
    synthetic_path,
    twins_cited,
)
import phase10d_synthetic as synthetic
from agentdojo_support import new_log
from source_support import call, final, log_with, result, turn

from agentprov.adapters.agentdojo import census
from agentprov.adapters.agentdojo.identity import resolve
from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import get_source
from agentprov.aer.rules import load_catalogue
from agentprov.testing import golden

IDS = [s.name for s in SOURCES]


@pytest.fixture(params=SOURCES, ids=IDS)
def src(request: pytest.FixtureRequest) -> Source:
    return request.param


# ------------------------------------------------------------------------------------------------ profile and registry
def test_profile_pin_licence_and_import_table(src: Source):
    profile = load_profile(src.profile)
    data = profile.data
    (pin,) = [p for p in data["source"]["pins"] if p.get("primary") is True]
    assert pin["commit"] == src.commit and pin["part"] == "head" and pin["kind"] == "git" and "tree" not in pin
    assert pin["expected_files"] == src.expected_files and pin.get("expected_bytes") == src.expected_bytes
    assert data["source"]["canonical_repo"] == src.repo and profile.source_id == src.profile and profile.parts == ("head",)
    assert data["licence"]["spdx"] == src.spdx and data["licence"]["policy"] == "include" and data["licence"]["attribution"]
    imp = data["import"]
    assert tuple(imp["variants"]) == src.variants and imp["dialect"] == imp["mapper"] == "agentdojo.tracelogger"
    assert dict(imp["rules"]) == {"aer": 1, "agentdojo": 2}  # no source catalogue: generic rules only (D-100)
    assert profile.version == src.version


def test_registry_part_is_sealed_with_the_profile_and_its_own_corpus(src: Source):
    """D.3.2: supported after the recorded full import and the wave-2 seal (D-830); one corpus per source (D-94)."""
    registration = get_source(src.profile)
    (part,) = registration.capabilities
    assert part.part == "head" and part.profile == src.profile and part.corpus_id == src.profile
    assert part.import_status == "supported" and part.target_import_status == "supported"
    assert part.caveat is not None and part.caveat.startswith(
        f"full pinned snapshot imported through agentprov import in wave 2 and sealed as {src.profile} 0.1.0 ("
    )
    assert [s.corpus_id for s in part.sealed] == [src.profile]
    assert part.variants == src.variants and part.semantics == src.semantics
    assert registration.licence.spdx == src.spdx and registration.family == "agentdojo"
    profile = load_profile(src.profile)
    assert registration.licence.attribution == tuple(profile.data["licence"]["attribution"])


def test_family_part_conforms_to_the_closed_schema_both_checkers(src: Source):
    jsonschema = pytest.importorskip("jsonschema")
    table = family_table(load_profile(src.profile))
    jsonschema.validate(table.data, family_schema())
    assert check_against_schema(table.data, family_schema()) == []


def test_every_quirk_rule_exists_and_every_observed_key_has_a_census_function(src: Source):
    table = family_table(load_profile(src.profile))
    for quirk in table.quirks:
        for rule in quirk.rules:
            entry = load_catalogue(rule.split(".", 1)[0]).get(rule)
            assert entry is not None and entry.citable, (quirk.id, rule)
    assert [p for p in census.compare(table, "head", {}) if "no census function" in p] == []


def test_no_harness_code_is_verified(src: Source):
    """D-24 and the phase-10c shortlist §1: no candidate has verified harness code."""
    table = family_table(load_profile(src.profile))
    assert table.verified_code == () and table.harness["code_identity"] in ("range", "unpinned")


def test_identity_resolution_of_the_directories(src: Source):
    table = family_table(load_profile(src.profile))
    for pipeline_name, facets, model, defences in src.identity:
        found = resolve(table.identity, dict(facets), pipeline_name, table.table_rows)
        assert (found.model, found.defences) == (model, defences), (pipeline_name, facets)


# ------------------------------------------------------------------------------------------------ D-24 on synthetic logs
def _synthetic(src: Source) -> dict:
    if src.variants == ("v0.k11",):  # the June-2024 writer: string content, no version fields (D.6.2)
        return new_log(pipeline_name=src.synthetic_pipeline)
    c = call("send_money", {"recipient": "US133000000121212121212", "amount": 10.0}, "call_1")
    return log_with([turn(c), result(c, "Transaction sent."), final()], pipeline_name=src.synthetic_pipeline,
                    benchmark_version=src.bench_versions[0] if src.bench_versions else "v1.2.2")


def test_a_synthetic_log_maps_validates_and_cites_only_twins(src: Source):
    doc = _synthetic(src)
    path = synthetic_path(src, doc)
    m = map_doc(src, doc, path)
    ok(m)
    assert not m.outcome.degenerate and not m.issues("agentdojo.undeclared_quirk")
    if any(fragment in path for fragment in src.unresolved):  # D-92: a model recorded nowhere is never guessed
        assert m.issues("identity_unresolved") and m.get("agent")["unk"]["/model"] == "not_recorded"
    else:
        assert not m.issues("identity_unresolved")
    assert d_rules_cited_at_d(m) == []
    assert {"agentdojo.tool_msg_is_one_execution_unverified@1", "agentdojo.checker_outcome_unverified@1"} <= twins_cited(m)


# ------------------------------------------------------------------------------------------------ defence denials (R1)
DENIAL_QUIRK = "agentdojo.defence_denial_message"
DENIAL_RULE = "agentdojo.defence_denial_message@1"


def test_the_denial_quirk_is_declared_exactly_where_the_source_logs_denials(src: Source):
    quirks = [q for q in family_table(load_profile(src.profile)).quirks if q.id == DENIAL_QUIRK]
    assert bool(quirks) == bool(src.denial)
    for q in quirks:
        assert q.rules == (DENIAL_RULE,) and q.params["denials"]


def _denial_log(src: Source) -> tuple[dict, str]:
    """A log of the source with one denied call (the defence's text as error) and one ordinary tool error."""
    d = src.denial
    pipeline = d.get("pipeline", src.synthetic_pipeline)
    content = d["error"] if d.get("content_equals_error") else ""
    if src.variants == ("v0.k11",):
        doc = new_log(pipeline_name=pipeline)
        doc["messages"][3].update(content=content, error=d["error"])
        other = {"function": "get_balance", "args": {}, "id": "call_2"}
        doc["messages"][4:4] = [{"role": "assistant", "content": None, "tool_calls": [other]},
                                {"role": "tool", "content": "", "tool_call_id": "call_2", "tool_call": other,
                                 "error": "ValueError: synthetic"}]
    else:
        c1 = call("send_money", {"recipient": "US133000000121212121212", "amount": 10.0}, "call_1")
        c2 = call("get_balance", {}, "call_2")
        doc = log_with([turn(c1), result(c1, content, error=d["error"]), turn(c2), result(c2, "", "ValueError: synthetic"),
                        final()], pipeline_name=pipeline,
                       benchmark_version=src.bench_versions[0] if src.bench_versions else "v1.2.2")
    directory = d.get("pipeline") or src.notes.get("pipeline_dir", src.synthetic_pipeline)
    path = d.get("path", src.synthetic_path).format(
        pipeline_dir=directory, suite=doc["suite_name"], task=doc["user_task_id"],
        attack=doc.get("attack_type") or "none", file=doc.get("injection_task_id") or "none")
    return doc, path


def test_a_synthetic_denial_is_a_defence_decision_and_other_errors_stay_executions(src: Source):
    """R1 (D-113): the denied call has no tool_execution; a deny decision by the defence actor, citing the generic rule,
    has the refused call as subject and the logged error as reason; the tool message is generated by it. An ordinary
    error of the same file stays an executed call with status error, and D-24 holds."""
    if not src.denial:
        pytest.skip(f"{src.name} logs no defence denial")
    doc, path = _denial_log(src)
    m = map_doc(src, doc, path)
    ok(m)
    (dc,) = [r for r in m.of_kind("decision") if any(str(ref).split("#")[0] == DENIAL_RULE for ref in r["rule"])]
    actor = m.get(dc["actor"])
    assert actor["kind"] == "defense" and actor["name"] == src.denial["defence"]
    assert dc["verdict"] == "deny" and dc["ev"] == "I" and dc["reason"] == src.denial["error"]
    (msg,) = [r for r in m.of_kind("message") if r.get("generated_by") == dc["id"]]
    assert msg["role"] == "tool" and msg["actor"] == dc["actor"] and msg["parts"][0]["responds_to"] == dc["subject"]
    (te,) = m.of_kind("tool_execution")
    assert te["status"] == "error" and te["name"] == "get_balance"
    assert d_rules_cited_at_d(m) == []


# ------------------------------------------------------------------------------------------------ real fixtures
def test_fixtures_are_provenanced_and_licensed(src: Source):
    entries = fixture_entries(src)
    root = FIXTURES / src.name
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"SOURCE.json"}
    assert on_disk == {e["sample_file"] for e in entries}
    if src.name in synthetic.NAMES:  # D-945: synthetic fixtures, checked by their provenance (no third-party licence)
        _check_synthetic_provenance(src, entries)
        return
    for e in entries:
        raw = fixture_bytes(src, e)
        assert e["commit_or_revision"] == src.commit and e["repo"] == src.repo and e["synthetic"] is False
        assert e["licence_class"] in golden.LICENCE_CLASSES and e["size_bytes"] == len(raw) and e["criteria"]
        assert e["sample_file"] == e["original_path"]
    assert src.licence_file is not None
    text = (FIXTURES / "LICENSES" / src.licence_file).read_text(encoding="utf-8")
    assert src.licence_marker in text[:400]


def _check_synthetic_provenance(src: Source, entries: list[dict]) -> None:
    """K.4.1(3), K.4.2: self-authored, ``synthetic: true``, class ``permissive`` under the repository licence, written by
    the generator (byte for byte), in the layout of the source's primary pin, with no licence file of the source."""
    assert src.licence_file is None and src.licence_marker == ""
    assert synthetic.LAYOUT_OF[src.name] == (src.repo, src.commit)
    written = synthetic.build(src.name)
    assert (FIXTURES / src.name / "SOURCE.json").read_bytes() == written["SOURCE.json"]
    for e in entries:
        raw = (FIXTURES / src.name / e["sample_file"]).read_bytes()
        assert raw == written[e["sample_file"]], e["sample_file"]
        assert e["synthetic"] is True and e["licence_class"] == "permissive" and e["licence"] == synthetic.LICENCE
        assert e["repository"] == synthetic.REPOSITORY and e["original_path"] == synthetic.GENERATOR
        assert e["commit_or_revision"] is None and e["url"] is None and e["retrieved_at"] is None
        assert e["layout_of"] == {"repo": src.repo, "commit": src.commit} and e["criteria"]
        assert e["size_bytes"] == len(raw) and fixture_bytes(src, e)  # digests checked, template assembled
    stem = {"gate": "gate-", "sentry": "SENTRY-", "aiauthz": "aiAuthZ-", "bookkeeper": "bookkeeper-",
            "llm-lock": "llm-lock-"}[src.name]
    assert not [p.name for p in (FIXTURES / "LICENSES").iterdir() if p.name.startswith(stem)]


@pytest.mark.parametrize("name", synthetic.NAMES)
def test_synthetic_templates_hold_no_assembled_text(name: str):
    """R-42, K.4.1(3): the injection sentence and the borrowed system prompt are filled at run time; no template holds
    them, every attacked log has its placeholder, and the assembled log keeps the template's serialisation."""
    sentence = synthetic.injection_sentence().encode("ascii")
    for path, data in synthetic.build(name).items():
        if path == "SOURCE.json":
            continue
        assert sentence not in data and b"INFORMATION> This" not in data, path
        doc = json.loads(data)
        assert all(v == synthetic.INJECTION for v in doc["injections"].values()), path
        assert bool(doc["injections"]) == (doc["attack_type"] is not None), path
        assembled = synthetic.assemble(data)
        assert (b"\r\n" in data) == (b"\r\n" in assembled) == (name in synthetic.CRLF), path
        filled = json.loads(assembled)
        assert all(v == synthetic.injection_sentence() for v in filled["injections"].values()), path
        assert b"@@assemble:" not in assembled, path


def test_the_committed_synthetic_fixtures_are_what_the_generator_writes():
    assert synthetic.main(list(synthetic.NAMES)) == 0


def test_real_fixtures_map_validate_cite_only_twins_and_keep_their_aer_bytes(src: Source):
    """D.6.10 items 1 and 5 and D-24 on the real logs of each source."""
    produced: dict[str, str] = {}
    profile = load_profile(src.profile)
    for entry in fixture_entries(src):
        path = layout_path(entry)
        m = map_fixture(src, entry)
        ok(m)
        assert not m.outcome.degenerate and m.header["profile"] == profile.header()
        assert m.header["dialect"]["variant"] in src.variants
        if is_synthetic(entry) and m.of_kind("message") and src.name != "llm-lock":  # D-945: the borrowed default prompt
            assert m.get("m0")["ext"]["agentdojo"]["system_prompt_variant"] == "agentdojo_default", path
        if any(fragment in path for fragment in src.unresolved):  # D-92: never guessed
            assert m.issues("identity_unresolved") and m.get("agent")["unk"]["/model"] == "not_recorded"
            assert "model" not in m.get("agent")
        else:
            assert not m.issues("identity_unresolved")
        assert not m.issues("agentdojo.undeclared_quirk") and not m.issues("agentdojo.path_field_mismatch")
        assert d_rules_cited_at_d(m) == [], path
        assert "agentdojo.benchmark_from_dialect_unverified@1" in twins_cited(m)
        if src.bench_versions:
            assert m.get("bench").get("version") in src.bench_versions
        produced[f"{src.name}/{path}"] = golden.sha256_hex(m.data)
    expected = json.loads(DIGESTS.read_text(encoding="utf-8")) if DIGESTS.is_file() else {}
    if os.environ.get(REGEN):
        expected = {k: v for k, v in expected.items() if not k.startswith(f"{src.name}/")} | produced
        DIGESTS.write_text(json.dumps(dict(sorted(expected.items())), indent=2) + "\n", encoding="utf-8")
    mine = {k: v for k, v in expected.items() if k.startswith(f"{src.name}/")}
    assert mine == produced

# ------------------------------------------------------------------------------------------------ SEM under suites@2 (R9)
def test_real_fixtures_annotate_under_suites_v2_citing_only_twins(src: Source):
    """R9 (D-115): every phase-10d part reads agentdojo.suites@2. The harnesses are unverified (verified_code = []), so
    every SEM rule of version 2 that rests on cited harness code is cited through its _unverified twin (D-86) and its
    annotations are I; the SEM document validates against its AER."""
    from agentprov.adapters.agentdojo.semantics.suites import TWINNED
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.sem.engine import annotate
    from agentprov.sem.validate import validate_sem_document

    assert src.semantics == ("agentdojo.suites@2",)
    prof = load_semantics_profile("agentdojo.suites", 2)
    twins = {r.replace("@", "_unverified@") for r in TWINNED}
    cited: set[str] = set()
    for entry in fixture_entries(src):
        doc = load_aer_bytes(map_fixture(src, entry).data)
        sem = annotate(doc, prof)
        report = validate_sem_document(sem, doc, profile=prof)
        assert report.ok, (layout_path(entry), sorted(report.codes()))
        for ann in sem.records[1:]:
            rules = {str(r).split("#")[0] for r in ann.get("rule", ())}
            assert not rules & set(TWINNED), (layout_path(entry), ann.get("type"), sorted(rules & set(TWINNED)))
            if rules & twins:
                assert ann["ev"] == "I", (layout_path(entry), ann.get("type"))
            cited |= rules & twins
    assert "agentdojo.utility_meaning_unverified@1" in cited
