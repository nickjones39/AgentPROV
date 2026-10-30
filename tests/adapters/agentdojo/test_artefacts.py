"""The ``agentdojo`` artefact catalogue after the corpus pre-check, wave 1 (D-581..D-585; regeneration-batch item 109).

The entries come from the wave-1 dossiers (``docs/reports/precheck/<corpus>.md``) fitted to the D.15.8 schema: no
placeholder detector, a closed cause and handling class, integer counts, and no row for a pre-registered estimate. The
three ROPE entries describe both semantics-profile versions (D-584). The version stays 1 (D-31 owner ruling 2026-10-21:
in place, no corpus records the artefact catalogue). Failures print ids and tokens only."""

from __future__ import annotations

from collections import Counter

import agentdojo_support as ads
import pytest

from agentprov.aer.reader import load_aer_bytes
from agentprov.artefacts import discover_catalogues, scan
from agentprov.artefacts.catalogue import ArtefactEntry, check_references, load_catalogue

#: The documentation entries of wave 1: a recount against a paper, README or design, with no per-trace detector.
WAVE1_NEW = (
    "agentdojo.art.incomplete_arm",
    "agentdyn.art.paper_row_not_in_logs",
    "agentdyn.art.github_it1_checker_prefix",
    "survey.art.readme_error_tasks_mismatch",
    "survey.art.partial_table_unbacked",
)
#: Wave 2 (D-589): two more documentation entries; agentdojo.art.defence_authored_message is a CR entry of its own.
WAVE2_DOC = ("agentdojo.art.reported_rows_unbacked", "geryon.art.author_declared_unusable_arm")


@pytest.fixture(scope="module")
def entries() -> dict[str, ArtefactEntry]:
    return {e.id: e for e in load_catalogue("agentdojo").entries}


def _rows(entry: ArtefactEntry) -> set[tuple[str, int, str, str]]:
    return {(x.snapshot, x.count, x.unit, x.status) for x in entry.expected}


def test_catalogue_validates_in_place_at_version_1():
    cat = load_catalogue("agentdojo")
    assert cat.version == 1  # D-31 owner ruling 2026-10-21: in place, no corpus records the artefact catalogue
    assert [str(p) for p in check_references(cat)] == []
    assert len(cat.entries) == 82  # +3 AgentDyn live backend (D-687), +25 wave-2 artefact scope (D-950)


@pytest.mark.parametrize("entry_id", WAVE1_NEW)
def test_wave1_entries_flag_only_and_go_to_the_manuscript(entries, entry_id):
    e = entries[entry_id]
    assert e.handling_class == "FO" and e.handling_rule is None and e.manuscript
    assert not e.claims and not (e.issues or e.notes or e.sem)  # recorded nowhere per execution; claims nothing
    assert e.expected and all(x.count > 0 for x in e.expected)


def test_incomplete_arm(entries):
    e = entries["agentdojo.art.incomplete_arm"]
    assert (e.cause, e.detector_rule, e.detector_class) == ("upstream_harness", "agentdojo.pipeline_dir_is_model_identity@1", "I")
    assert e.profiles == ("agentdojo-upstream",)
    assert _rows(e) == {("head", 151, "cells", "verified"), ("head", 40, "executions", "verified"),
                        ("2024-06", 40, "executions", "verified"), ("2024-06", 7, "executions", "verified")}


def test_agentdyn_entries(entries):
    paper = entries["agentdyn.art.paper_row_not_in_logs"]
    assert (paper.cause, paper.detector_rule) == ("unknown", "agentdojo.checker_outcome@1")
    assert _rows(paper) == {("agentdyn:a", 4, "directories", "verified")}
    it1 = entries["agentdyn.art.github_it1_checker_prefix"]
    assert (it1.cause, it1.parts) == ("benchmark", ("a", "b", "c"))
    # the 5 completed deletions logged false were not target-matched: a plausible count, so unverified
    assert _rows(it1) == {("agentdyn:a", 31, "executions", "verified"), ("agentdyn:a", 5, "executions", "unverified"),
                          ("agentdyn:b", 2, "executions", "verified"), ("agentdyn:c", 4, "executions", "verified")}


def test_survey_entries(entries):
    readme = entries["survey.art.readme_error_tasks_mismatch"]
    assert (readme.detector_rule, readme.detector_class) == ("survey.internal_server_error_patch@1", "I")
    assert _rows(readme) == {("agent-security-tools-survey:agentdojo-runs", 11, "executions", "verified")}
    partial = entries["survey.art.partial_table_unbacked"]
    assert _rows(partial) == {("agent-security-tools-survey:agentdojo-runs", 315, "cells", "verified")}


def test_validity_defects_cc07_rows(entries):
    e = entries["agentdojo.art.validity_defects"]
    assert "mandate-agentdojo-eval" in e.profiles and "mandate-agentdojo-eval" in e.sources
    rows = _rows(e)
    assert {("mandate-agentdojo-eval:head", 3, "executions", "verified"),
            ("mandate-agentdojo-eval:head", 4, "executions", "verified")} <= rows
    # the survey #181 count is a lower bound (injection task 1 untested): unverified
    assert ("agent-security-tools-survey:agentdojo-runs", 13, "executions", "unverified") in rows
    assert {"https://github.com/ethz-spylab/agentdojo/issues/181",
            "https://github.com/ethz-spylab/agentdojo/issues/161"} <= set(e.refs)


def test_defence_benign_intervention_mandate_rows(entries):
    rows = _rows(entries["agentdojo.art.defence_benign_intervention"])
    assert {("mandate-agentdojo-eval:head", 8, "executions", "verified"),
            ("mandate-agentdojo-eval:head", 1, "executions", "verified")} <= rows


def test_rope_entries_corrected_not_retired(entries):
    """D-584: each keeps its id and states the suites@1 count beside the suites@2 one; @2 counts measured on the stored
    AERs stay unverified until the regenerated corpus confirms them."""
    escaped = entries["rope.art.autodojo_payload_escaped"]
    assert (escaped.handling_class, escaped.handling_rule) == ("CR", "agentdojo.autodojo_payload_unescape@1")
    assert "suites@2" in escaped.description and "suites@1" in escaped.description
    assert _rows(escaped) == {("rope:head", 1166, "executions", "verified"), ("rope:head", 1235, "executions", "verified"),
                              ("rope:head", 1840, "markers", "verified"), ("rope:head", 2528, "executions", "unverified")}
    exposure = entries["rope.art.security_without_exposure"]
    assert (exposure.detector_rule, exposure.detector_class) == ("agentdojo.success_without_visible_payload@1", "D")
    assert "agentdojo.success_without_visible_payload" in exposure.sem
    assert _rows(exposure) == {("rope:head", 22, "executions", "verified"), ("rope:head", 5, "executions", "unverified")}
    tag = entries["rope.art.pipeline_tag_not_identity"]
    assert "qwen3-235b" in tag.description and "gpt-4o-mini" in tag.description
    assert all(e.manuscript for e in (escaped, exposure, tag))


def test_wave1_entries_claim_nothing_on_the_native_fixtures():
    """A documentation entry cites an existing rule as its detector; that must not make it claim safety-net findings."""
    cats = discover_catalogues()
    claimed: Counter[str] = Counter()
    for entry in ads.native_entries():
        aer = load_aer_bytes(ads.map_native(entry).data)
        for finding in scan([*aer.records, aer.seal], cats):
            claimed.update(finding.entries)
    assert claimed and not set(claimed) & set(WAVE1_NEW), sorted(claimed)


@pytest.mark.parametrize("entry_id", WAVE2_DOC)
def test_wave2_documentation_entries(entries, entry_id):
    e = entries[entry_id]
    assert e.handling_class == "FO" and e.manuscript and not e.claims and not (e.issues or e.notes or e.sem)
    assert e.detector_rule == "agentdojo.pipeline_dir_is_model_identity@1" and all(x.status == "verified" for x in e.expected)


def test_defence_authored_message_entry(entries):
    e = entries["agentdojo.art.defence_authored_message"]
    assert (e.detector_rule, e.handling_class, e.handling_rule) == (
        "agentdojo.defence_authored_message@1", "CR", "agentdojo.defence_authored_message@1")
    assert e.profiles == ("melon-agentdojo",) and e.manuscript
    assert _rows(e) == {("melon-agentdojo:head", 910, "executions", "verified"),
                        ("melon-agentdojo:head", 3, "executions", "verified"),
                        ("melon-agentdojo:head", 113, "messages", "verified")}


def test_wave2_entries_claim_nothing_on_the_melon_and_geryon_fixtures():
    import phase10d_support as p10d

    cats = discover_catalogues()
    claimed: Counter[str] = Counter()
    for src in (s for s in p10d.SOURCES if s.name in ("melon", "geryon")):
        for entry in p10d.fixture_entries(src):
            aer = load_aer_bytes(p10d.map_fixture(src, entry).data)
            for finding in scan([*aer.records, aer.seal], cats):
                claimed.update(finding.entries)
    assert not set(claimed) & {*WAVE2_DOC, "agentdojo.art.defence_authored_message"}, sorted(claimed)


def test_seagent_guard_batch_abort_entry(entries):
    """D-591: CR through the guard rule; it claims the version-1 missing_tool_result findings, all of them guard aborts."""
    e = entries["agentdojo.art.seagent_guard_batch_abort"]
    assert (e.detector_rule, e.handling_class, e.handling_rule) == (
        "agentdojo.seagent_guard_block@1", "CR", "agentdojo.seagent_guard_block@1")
    assert e.issues == ("missing_tool_result",) and e.profiles == ("seagent-agentdojo",) and e.manuscript
    assert {(x.count, x.unit) for x in e.expected} == {(960, "calls"), (166, "calls"), (107, "executions"), (94, "executions")}


#: The wave-2 artefact scope (D-950): source-specific entries for the corpus wave-2 profiles.
WAVE2_SCOPE_NEW = (
    "agentdojo.art.model_not_recorded", "agentdojo.art.fork_top_level_keys", "agentdojo.art.system_prompt_unrecognised",
    "agentdojo.art.pipeline_name_differs", "agentdojo.art.unattributed_user_message", "agentdojo.art.orphan_tool_results",
    "agentdojo.art.null_provider_call_ids", "agentdojo.art.positional_link_conflict",
    "agentdojo.art.detector_abort_output_unrecorded",
    "drift.art.agent_prompt_not_recorded", "drift.art.injection_map_not_recorded", "drift.art.calls_in_text_not_executed",
    "drift.art.call_error_unrecognised", "drift.art.benign_security_constant", "drift.art.single_pass",
    "rescont.art.serialised_without_ids_or_times", "rescont.art.last_pass_kept", "rescont.art.benign_security_constant",
    "rescont.art.exception_row_defaults", "rescont.art.request_not_recorded", "rescont.art.injection_map_not_recorded",
    "rescont.art.melon_calls_not_recorded", "rescont.art.defence_unrecorded", "rescont.art.model_identity_from_documents",
    "rescont.art.value_redacted",
)


def test_wave2_scope_entries_are_unverified_and_name_shipped_profiles(entries):
    """D-950: every new entry counts from the wave-2 census (unverified until the sealed import) and is scoped to
    profiles the family ships; the widened generic entries name the wave-2 TraceLogger profiles."""
    shipped = {p.name.removesuffix(".profile.toml") for p in (ads.REPO / "src" / "agentprov" / "adapters" / "agentdojo"
                                                              / "profiles").glob("*.profile.toml")}
    for entry_id in WAVE2_SCOPE_NEW:
        e = entries[entry_id]
        assert e.profiles and set(e.profiles) <= shipped, entry_id
        assert e.expected and all(x.status == "unverified" and x.count > 0 for x in e.expected), entry_id
    for entry_id in ("agentdojo.art.calls_derived_from_messages", "agentdojo.art.naive_timestamp",
                     "agentdojo.art.silent_rerun", "agentdojo.art.benign_security_constant"):
        assert {"gate-agentdojo", "llm-lock-agentdojo", "yockcheng-prompt-injection-harness"} <= set(entries[entry_id].profiles)
    # ResCont rows are not TraceLogger logs: their times, ids and passes have entries of their own
    assert "memo-ozdincer-agentdojo" not in entries["agentdojo.art.naive_timestamp"].profiles
    assert "memo-ozdincer-agentdojo" not in entries["agentdojo.art.silent_rerun"].profiles
