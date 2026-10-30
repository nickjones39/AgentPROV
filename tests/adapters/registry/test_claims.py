"""The one claims/lint library ``agentprov.adapters.registry.claims`` (I.5.6, I.5.9 item 5; H.9(3)-(4); Q.11b; D-36).

* every I.4 item with tags has a negative ``check_claim`` test (a forbidden tag on its source is a violation);
* ``asr`` needs its derivation; ``coverage_claim`` needs the generated phrase; agent-execution counts need the
  agent-execution scope;
* ``coverage_phrase`` follows the registry and Q.11a;
* ``lint_text``: the bare agnosticism term outside a design-goal block, counts in a block, unqualified "reproducible",
  scope words, a hand-written coverage phrase, a "Live Capture" title;
* ``lint_card``: front matter, literal numbers and the allow-list, unregistered claims;
* the datasheet claims evaluate over manifest values.
"""

from __future__ import annotations

import pytest

from agentprov.adapters.registry import REGISTRY
from agentprov.adapters.registry.claims import (
    ATTRIBUTION_PREFIX,
    CLAIM_TAGS,
    CLAIMS,
    MUST_NOT_CLAIM,
    check_claim,
    coverage_phrase,
    evaluate_claims,
    forbidden_tags,
    lint_card,
    lint_datasheet,
    lint_text,
)

_CONDITIONAL = {"NC-ALL-04", "NC-ALL-05", "NC-ALL-08", "NC-ALL-13", "NC-LIVE-01", "NC-LIVE-02"}


def test_every_tag_is_in_the_closed_vocabulary_and_no_agnostic_tag():
    assert "benchmark_agnostic" not in CLAIM_TAGS
    for item in MUST_NOT_CLAIM:
        assert item.tags and set(item.tags) <= set(CLAIM_TAGS), item.nc_id


@pytest.mark.parametrize("item", [i for i in MUST_NOT_CLAIM if i.nc_id not in _CONDITIONAL], ids=lambda i: i.nc_id)
def test_each_tagged_item_forbids_its_tags_for_its_source(item):
    source = item.source_id or "agentdojo"
    for tag in item.tags:
        if tag in ("asr", "coverage_claim", "agent_execution"):
            continue  # decided by their own rules below
        violations = check_claim([source], [tag])
        assert any(v.nc_id == item.nc_id or v.tag == tag for v in violations), (item.nc_id, tag)
    assert set(item.tags) - {"asr", "coverage_claim", "agent_execution"} <= forbidden_tags(source)


def test_asr_on_stac_is_nc_stac_01_and_asr_needs_a_derivation():
    assert any(v.nc_id == "NC-AUTO-04" for v in check_claim(["rope"], ["asr"]))
    assert check_claim(["rope"], ["asr"], derivation={"labels": "raw", "averaging": "micro"}) == []
    stac = check_claim(["stac"], ["agent_execution"])
    assert any(v.nc_id in ("NC-ALL-13", "NC-STAC-01") for v in stac)


def test_an_unknown_tag_is_a_violation():
    assert check_claim(["rope"], ["benchmark_agnostic"])


def test_agent_execution_counts_need_the_agent_execution_scope():
    assert check_claim(["rope"], ["agent_execution"])
    assert check_claim(["rope"], ["agent_execution"], agent_executions_only=True) == []


def test_coverage_phrase_follows_the_registry():
    phrase = coverage_phrase()
    assert phrase is not None and phrase.startswith("adapter-based core; demonstrated on ")
    assert phrase.endswith("formats (single-agent, tool-calling traces)")
    no_inspect = tuple(r for r in REGISTRY if not any("inspect.eval" in c.dialects for c in r.capabilities))
    assert coverage_phrase(no_inspect) is None  # Q.11a not passed without a supported Inspect part
    assert check_claim([], ["coverage_claim"], phrase=phrase) == []
    assert check_claim([], ["coverage_claim"], phrase="demonstrated on many sources")


def test_a_part_served_through_another_source_does_not_count_its_registration():
    """D-481 (CD-4): AutoDojo's ``rope-slice`` part is imported, owned and counted under ROPE (``via = "rope"``;
    NC-AUTO-01), so it does not make AutoDojo a demonstrated source; the count is the same with and without it."""
    via_only = {
        r.source_id for r in REGISTRY
        if any(c.via for c in r.capabilities)
        and not any(c.role == "source" and c.import_status in ("supported", "partial") and c.via is None
                    for c in r.capabilities)
    }  # fmt: skip
    assert "autodojo" in via_only
    without = tuple(r for r in REGISTRY if r.source_id not in via_only)
    assert coverage_phrase() == coverage_phrase(without)


@pytest.mark.parametrize(
    ("text", "nc_id"),
    [
        ("AgentPROV is benchmark-agnostic.", "NC-ALL-08"),
        ("The corpus is reproducible.", "AR-12"),
        ("A lossless capture of every run.", "NC-ALL-03"),
        ("We give a faithful record.", "NC-ALL-03"),
        ("adapter-based core; demonstrated on 99 sources in 1 formats", "NC-ALL-08"),
        ("# Live Capture of agent runs", "NC-LIVE-02"),
        ("<!-- agentprov:design-goal -->\nThe core is benchmark-agnostic over 5 sources.\n<!-- agentprov:end-design-goal -->",
         "NC-ALL-08"),
    ],
)
def test_lint_text_rules(text, nc_id):
    assert any(v.nc_id == nc_id for v in lint_text("doc.md", text))


@pytest.mark.parametrize(
    "text",
    [
        "The corpus is derivation-reproducible; execution reproducibility is never claimed.",
        "<!-- agentprov:design-goal -->\nThe core is benchmark-agnostic by design.\n<!-- agentprov:end-design-goal -->",
        "% agentprov:design-goal\nThe core is framework-agnostic.\n% agentprov:end-design-goal",
        "{{claim:raw_included}} is lossless for the stated scope.",
    ],
)
def test_lint_text_accepts(text):
    assert lint_text("doc.md", text) == []


def test_lint_card_front_matter_numbers_and_claims():
    good = "---\nmode: import\n---\nVersion `aer/0.1`, spec agentprov-prov/0.1, DOI 10.5281/zenodo.12528188, arXiv:2406.13352, " \
           "commit c274885, 2026-10-11, H.1.5(4), §8.3, D-27, `gpt-4o-2024-05-13`, rule `agentdojo.x@1`, {{v:/counts/executions}}.\n"
    assert lint_card(good) == []
    assert any(v.nc_id == "H.9(5)" for v in lint_card("No front matter.\n"))
    assert any(v.nc_id == "H.9(3)" for v in lint_card("---\nmode: import\n---\nWe have 648 cells.\n"))
    assert any(v.nc_id == "H.9(3)" for v in lint_card("---\nmode: import\n---\nA 52-minute window.\n"))
    assert any(v.nc_id == "H.9(3)" for v in lint_card("---\nmode: import\n---\nIn `648` cells.\n"))  # a bare number in code
    assert any(v.nc_id == "H.9(4)" for v in lint_card("---\nmode: import\n---\n{{claim:not_registered}}\n"))


def _manifest(**counts):
    base = {"issues_by_code": {}, "execution_observed": {"true": 3, "false": 0}, "by_completeness": {"unverifiable": 3},
            "executions": 3, "by_status": {"failed": 0}, "by_unit": {"outcome_only": 0, "scenario": 0},
            "generic_types": {"activity": {}, "artefact": {}}, "selection_excluded_by_code": {}, "members": None}
    base.update(counts)
    return {"counts": base, "sources": [{"snapshots": [{"raw_policy": "include"}]}], "validation": {"mode": "strict", "checks": []},
            "licences": {"restrictions": []}, "oracle_specs": []}


def test_datasheet_claims_evaluate_over_the_manifest():
    results, violations = evaluate_claims(["all_unverifiable", "raw_included", "no_restrictions"], _manifest())
    assert violations == [] and all(r["holds"] for r in results)
    results, violations = evaluate_claims(["restricted_use", "unknown_claim"], _manifest())
    assert len(violations) == 2 and results == [{"holds": False, "id": "restricted_use"}]
    assert set(CLAIMS) >= {"no_execution_observed_nonzero", "all_unverifiable"}  # the H.9(4) examples


def test_lint_datasheet_requires_the_untrusted_content_section():
    section = "## Untrusted content\n\nprompt-injection payloads; treat as data; no model receives content.\n"
    assert lint_datasheet("# D\n\n" + section) == []
    assert lint_datasheet("# D\n")


_SECTION = "## Untrusted content\n\nprompt-injection payloads; treat as data; no model receives content.\n"
_TITLE = "\"A, Reproduction Artifact for 'Benchmarks: A Reproducible Study' (CC-BY-4.0)\"; \"B, a faithful port\""


def test_lint_datasheet_skips_word_rules_on_the_quoted_attribution_line_d910():
    quoted = f"{ATTRIBUTION_PREFIX}{_TITLE}.\n"
    assert lint_datasheet("# D\n\n" + quoted + _SECTION) == []
    codes = {v.nc_id for v in lint_datasheet("# D\n\n- Required attribution: " + _TITLE + ".\n" + _SECTION)}
    assert codes == {"AR-12", "NC-ALL-03"}  # the same text on another line
    assert {v.nc_id for v in lint_text("doc.md", quoted)} == {"AR-12", "NC-ALL-03"}  # only a generated datasheet quotes
    outside = "# D\n\n" + quoted + "The corpus is reproducible.\n" + _SECTION
    assert [v.nc_id for v in lint_datasheet(outside)] == ["AR-12"]  # the next line is linted as before


@pytest.mark.parametrize("line", [
    "  " + ATTRIBUTION_PREFIX + _TITLE,  # not at the line start
    "Text " + ATTRIBUTION_PREFIX + _TITLE,  # mid-line
    ATTRIBUTION_PREFIX.rstrip() + _TITLE,  # not the exact prefix
])
def test_only_a_line_that_starts_with_the_exact_prefix_is_exempt(line):
    assert {"AR-12", "NC-ALL-03"} <= {v.nc_id for v in lint_datasheet("# D\n\n" + line + "\n" + _SECTION)}


@pytest.mark.parametrize("text", [ATTRIBUTION_PREFIX + "x", "We note the Required attribution (verbatim) here."])
def test_a_card_or_statement_may_not_hold_the_attribution_phrase(text):
    found = lint_card(f"---\nmode: import\n---\n{text}\n")
    assert any(v.nc_id == "H.9(4)" and "verbatim attribution phrase" in v.detail for v in found)


@pytest.mark.parametrize("stale", [
    "fetch layer cannot address",  # Hugging Face dataset pins are git pins since D-53 (phase 12b)
    "after phase 11",  # phase 11 is merged
    "does not import yet (archive inputs",  # deposit-archive members are archive inputs since D-200 (mapper side D-204)
    "until the runner imports deposit archives",
])
def test_no_caveat_states_a_resolved_blocker_as_open(stale):
    """A caveat is an honesty statement (R-15): a blocker that is resolved on main is not described as open."""
    from agentprov.adapters.registry.render import registry_rows

    assert [r["source"] for r in registry_rows()["parts"] if stale in (r.get("caveat") or "")] == []
