"""Catalogue schema, discovery and rule-id existence (the first two tests of D.15.7; D.15.8 items 1, 2 and 4)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from art_support import catalogue, entry

from agentprov.artefacts import (
    DETECTORS,
    ArtefactCatalogueError,
    check_references,
    discover_catalogues,
    families_with_catalogues,
    known_issue_codes,
    known_rule_ids,
    load_catalogue,
    parse_catalogue,
)

HEAD = 'version = 1\nfamily = "tst"\n\n'
GOOD = entry("good", handling="CR", handling_rule="aer.output_after_generator@1")


def parse(text: str, **kwargs):
    return parse_catalogue(text.encode(), source="<test>", family="tst", **kwargs)


# ---------------------------------------------------------------------------------------------------- shipped data


def test_every_shipped_catalogue_validates_and_all_its_references_exist():
    catalogues = discover_catalogues()
    assert "adprov" in [c.family for c in catalogues]
    for c in catalogues:
        assert check_references(c) == [], c.family
        assert c.digest and c.version >= 1 and c.entries


def test_the_adprov_catalogue_covers_both_trees_and_the_documented_seeds():
    c = load_catalogue("adprov")
    ids = {e.id for e in c.entries}
    # D.15.6: the 13 classes of D.10.9 (A1-A13) for the generated tree, adprov.art.reported_calls_exceed, and the
    # converter artefacts of the converted tree.
    for needed in (
        "adprov.art.rerun_passes_lost", "adprov.art.usage_absent", "adprov.art.temperature_not_transmitted",
        "adprov.art.text_tool_call", "adprov.art.calls_pending_at_limit", "adprov.art.abnormal_finish",
        "adprov.art.failed_tool_empty_content", "adprov.art.provider_call_ids", "adprov.art.harness_side_effects",
        "adprov.art.model_display_name", "adprov.art.discarded_attempts_unrecorded", "adprov.art.served_model_unrecorded",
        "adprov.art.reported_calls_exceed", "adprov.art.timing_stub", "adprov.art.dos_polarity",
        "adprov.art.context_taint_used",
    ):  # fmt: skip
        assert needed in ids
    parts = {p for e in c.entries for p in e.parts}
    assert parts == {"release", "converted-legacy"}
    assert all(e.profiles == ("adprov-v1",) for e in c.entries)
    assert all(x.status == "unverified" for e in c.entries for x in e.expected)  # D.15.6 until a full import confirms
    assert {x.count for e in c.entries if e.id == "adprov.art.reported_calls_exceed" for x in e.expected} == {32}


def test_discovery_is_sorted_deterministic_and_imports_no_adapter_module():
    code = (
        "import sys, agentprov.artefacts as a\n"
        "first = [(c.family, c.digest) for c in a.discover_catalogues()]\n"
        "second = [(c.family, c.digest) for c in a.discover_catalogues()]\n"
        "assert first == second and [f for f, _ in first] == sorted(f for f, _ in first)\n"
        "bad = sorted(m for m in sys.modules if m.startswith('agentprov.adapters.') and m != 'agentprov.adapters.types')\n"
        "print(','.join(bad))\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=True)
    assert done.stdout.strip() == ""


def test_families_listed_match_the_loaded_ones():
    assert tuple(c.family for c in discover_catalogues()) == families_with_catalogues()


def test_load_unknown_family_is_refused():
    with pytest.raises(ArtefactCatalogueError) as err:
        load_catalogue("nonesuch")
    assert err.value.code == "artefacts.unavailable"
    with pytest.raises(ArtefactCatalogueError):
        load_catalogue("../adprov")


def test_header_records_family_version_and_digest():
    c = load_catalogue("adprov")
    assert c.header() == {"family": "adprov", "sha256": c.digest, "version": c.version}
    assert len(c.digest) == 64


# ---------------------------------------------------------------------------------------------------- schema


def test_a_minimal_catalogue_parses():
    c = parse(HEAD + GOOD)
    (e,) = c.entries
    assert (e.id, e.cause, e.detector_rule, e.detector_class, e.handling_class) == (
        "tst.art.good", "unknown", "artefact.generic.empty_execution", "O", "CR",
    )  # fmt: skip
    assert e.expected == () and e.manuscript is False and e.refs == () and e.applies_to(None) and e.applies_to("any")


def test_entries_are_sorted_by_id_whatever_the_file_order():
    c = parse(HEAD + entry("b") + entry("a"))
    assert [e.id for e in c.entries] == ["tst.art.a", "tst.art.b"]
    assert c.get("tst.art.a") is c.entries[0] and c.get("tst.art.zzz") is None


def test_every_field_of_d152_is_accepted():
    full = entry(
        "full",
        detector="aer.acc.reported_counts@1",
        cls="D",
        handling="DR",
        handling_rule="aer.acc.reported_counts@1",
        extra=(
            'scope = { profiles = ["p"], parts = ["x"], sources = ["s"] }\n'
            'claims = ["artefact.generic.pass_loss#lost"]\n'
            'recorded_as = { issues = ["no_execution_observed"], notes = ["n"], sem = ["a.b"] }\n'
            'expected = [{ snapshot = "s@1", count = 3, basis = "b", unit = "traces", status = "verified" }]\n'
            'manuscript = true\nrefs = ["r"]\n'
        ),
    )
    (e,) = parse(HEAD + full).entries
    assert e.profiles == ("p",) and e.parts == ("x",) and e.sources == ("s",)
    assert e.claims == ("artefact.generic.pass_loss#lost",) and e.issues == ("no_execution_observed",)
    assert e.expected[0].count == 3 and e.expected[0].unit == "traces" and e.expected[0].status == "verified"
    assert e.manuscript is True and e.refs == ("r",)
    assert e.applies_to("p") and not e.applies_to("q") and not e.applies_to(None)


BAD_ENTRIES = {
    "bad id": entry("good").replace("tst.art.good", "tst.good"),
    "wrong namespace": entry("good").replace("tst.art.good", "zzz.art.good"),
    "bad cause": entry("good").replace('cause = "unknown"', 'cause = "cosmic_rays"'),
    "bad handling class": entry("good", handling="XX"),
    "CR without rule": entry("good", handling="CR"),
    "DR without rule": entry("good", handling="DR"),
    "bad detector class": entry("good", cls="Z"),
    "detector not a rule id": entry("good", detector="not a rule"),
    "empty title": entry("good").replace('title = "good"', 'title = ""'),
    "unknown field": entry("good", extra='colour = "red"\n'),
    "unknown scope key": entry("good", extra='scope = { colour = "red" }\n'),
    "scope not strings": entry("good", extra='scope = { profiles = [1] }\n'),
    "bad claim": entry("good", extra='claims = ["detector.foo"]\n'),
    "negative count": entry("good", extra='expected = [{ snapshot = "s", count = -1, basis = "b" }]\n'),
    "string count": entry("good", extra='expected = [{ snapshot = "s", count = "3", basis = "b" }]\n'),
    "bool count": entry("good", extra='expected = [{ snapshot = "s", count = true, basis = "b" }]\n'),
    "missing basis": entry("good", extra='expected = [{ snapshot = "s", count = 1 }]\n'),
    "bad status": entry("good", extra='expected = [{ snapshot = "s", count = 1, basis = "b", status = "maybe" }]\n'),
    "manuscript not bool": entry("good", extra='manuscript = "yes"\n'),
    "refs not list": entry("good", extra='refs = "x"\n'),
    "duplicate items": entry("good", extra='refs = ["x", "x"]\n'),
    "control character": entry("good").replace('"test entry good"', '"test\\u0007entry"'),
}


@pytest.mark.parametrize("name", sorted(BAD_ENTRIES))
def test_schema_violations_are_refused(name):
    with pytest.raises(ArtefactCatalogueError) as err:
        parse(HEAD + BAD_ENTRIES[name])
    assert err.value.exit_code == 70 and err.value.code == "artefacts.catalogue_invalid"


def test_duplicate_ids_are_refused():
    with pytest.raises(ArtefactCatalogueError, match="duplicate id"):
        parse(HEAD + entry("a") + entry("a"))


@pytest.mark.parametrize(
    "text",
    [
        'family = "tst"\n',  # no version
        'version = 0\nfamily = "tst"\n',
        'version = "1"\nfamily = "tst"\n',
        'version = true\nfamily = "tst"\n',
        "version = 1\n",  # no family
        'version = 1\nfamily = "other"\n',  # does not match its directory
        'version = 1\nfamily = "tst"\ncolour = 1\n',
        'version = 1\nfamily = "tst"\nformat = "x/9"\n',
        'version = 1\nfamily = "tst"\nartefact = 3\n',
        "not toml at all [",
    ],
)
def test_top_level_violations_are_refused(text):
    with pytest.raises(ArtefactCatalogueError):
        parse(text)


def test_non_utf8_is_refused():
    with pytest.raises(ArtefactCatalogueError):
        parse_catalogue(b"\xff\xfe", source="<t>")


def test_all_defects_are_reported_together():
    text = HEAD + entry("a", handling="XX") + entry("b", cls="Q")
    with pytest.raises(ArtefactCatalogueError) as err:
        parse(text)
    assert "tst.art.a" in str(err.value) and "tst.art.b" in str(err.value)


def test_namespaces_default_to_the_family_and_may_be_widened():
    wide = parse_catalogue(
        ('version = 1\nfamily = "tst"\nnamespaces = ["tst", "other"]\n' + entry("a").replace("tst.art.a", "other.art.a")).encode(),
        source="<t>",
    )
    assert wide.entries[0].namespace == "other"


# ---------------------------------------------------------------------------------------------------- rule-id existence


def test_the_rule_universe_holds_core_adapter_and_engine_rules():
    rules = known_rule_ids()
    assert "aer.acc.reported_counts@1" in rules  # aer catalogue
    assert "adprov.timing_stub_is_unknown@1" in rules  # an adapter family's catalogue
    assert "agentdojo.no_execution_observed@1" in rules
    assert any(r.startswith("aprov.") for r in rules)  # the engine catalogue
    codes = known_issue_codes()
    assert "no_execution_observed" in codes and "adprov.tool_timing_overwritten" in codes


def test_unknown_detector_rule_is_reported():
    c = catalogue(entry("x", detector="adprov.no_such_rule@1", cls="D"))
    (problem,) = check_references(c)
    assert (problem.entry, problem.field) == ("tst.art.x", "detector.rule")


def test_unregistered_generic_detector_is_reported():
    c = catalogue(entry("x", detector="artefact.generic.no_such_detector"))
    (problem,) = check_references(c)
    assert problem.field == "detector.rule" and "generic" in problem.message


def test_registered_generic_detectors_pass():
    c = catalogue(*(entry(n.removeprefix("artefact.generic."), detector=n) for n in DETECTORS))
    assert check_references(c) == []


def test_unknown_handling_rule_is_reported():
    c = catalogue(entry("x", handling="CR", handling_rule="adprov.no_such_rule@1"))
    (problem,) = check_references(c)
    assert problem.field == "handling.rule"


def test_a_known_rule_passes_in_either_slot():
    c = catalogue(entry("x", detector="adprov.timing_stub_is_unknown@1", cls="D", handling="CR", handling_rule="aer.acc.reported_counts@1"))
    assert check_references(c) == []


def test_rule_ids_can_be_supplied_by_the_caller():
    c = catalogue(entry("x", detector="zzz.mine@1", cls="D"))
    assert check_references(c, rule_ids={"zzz.mine@1"}) == []
    assert check_references(c, rule_ids=set()) != []


def test_claims_must_name_registered_detectors_and_known_variants():
    ok = entry("a", extra='claims = ["artefact.generic.pass_loss#lost", "artefact.generic.sentinel_time#whatever"]\n')
    assert check_references(catalogue(ok)) == []
    bad_name = catalogue(entry("a", extra='claims = ["artefact.generic.nope"]\n'))
    assert [p.field for p in check_references(bad_name)] == ["claims"]
    bad_variant = catalogue(entry("a", extra='claims = ["artefact.generic.pass_loss#sideways"]\n'))
    assert [p.field for p in check_references(bad_variant)] == ["claims"]


def test_issue_codes_must_be_core_or_declared():
    ok = entry("a", extra='recorded_as = { issues = ["no_execution_observed", "adprov.tool_timing_overwritten"] }\n')
    assert check_references(catalogue(ok)) == []
    bad = catalogue(entry("a", extra='recorded_as = { issues = ["invented_code", "adprov.invented"] }\n'))
    assert [p.field for p in check_references(bad)] == ["recorded_as.issues", "recorded_as.issues"]


def test_problems_are_sorted_and_printable():
    c = catalogue(entry("b", detector="x.y@1", cls="D"), entry("a", detector="x.z@1", cls="D"))
    problems = check_references(c)
    assert [p.entry for p in problems] == ["tst.art.a", "tst.art.b"]
    assert "tst.art.a: detector.rule:" in str(problems[0])
