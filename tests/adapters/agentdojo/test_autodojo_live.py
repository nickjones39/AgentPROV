"""The ``autodojo`` · ``live`` registry part and the ``autodojo-live`` profile (docs/architecture D.11, D.11.4; phase 9 core).

* The registration is the D.11 live part: gated ``planned``, no import capability, the shared capture mapper and reader,
  the backend descriptor and the MIT licence of the fork. The ROPE import part is phase 10 and is not registered.
* The profile loads through the generic loader, conforms to the family's closed schema (both checkers), pins the fork
  commit exactly as the cache check does, declares the D.11.4 refusals and instrumentation, and every quirk rule exists in
  the shipped catalogue.
* The ``run`` status gate admits a scripted run of a ``planned`` part and refuses a real one.
"""

from __future__ import annotations

import json
import pytest

from agentprov.adapters.agentdojo.profile import check_against_schema, family_schema, family_table
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.registry import BACKENDS, MAPPERS, READERS, REGISTRY, get_source
from agentprov.adapters.runner import resolve_factory
from agentprov.aer.rules import load_catalogue
from agentprov.cli.common import CommandResult
from agentprov.cli.live.autodojo_cache import AUTODOJO_COMMIT, AUTODOJO_REPO


def _part():
    return {c.part: c for c in get_source("autodojo").capabilities}["live"]


def test_registration_is_the_partial_live_part_and_the_rope_slice():
    source = get_source("autodojo")
    assert source.family == "agentdojo" and [c.part for c in source.capabilities] == ["live", "rope-slice"]
    part = _part()
    assert part.role == "source" and part.evidence == "n/a" and part.import_status is None
    assert part.live_status == "partial" and part.target_import_status is None  # D-720
    # D-722 step 2: the approved pilot's record, the local run only; the rule-3 phrase is gone
    assert "real-model pilot 2026-10-22" in (part.caveat or "") and "local qwen3-8b-abliterated-v2 (2 cells)" in part.caveat
    assert "no real-model run" not in part.caveat and "OpenRouter" not in part.caveat and "cannot be sealed" in part.caveat
    assert part.dialects == ("agentprov.capture", "agentdojo.tracelogger") and part.variants == ("0.1", "v1.k14")
    assert part.backend == "autodojo" and part.profile == "autodojo-live" and part.requires == ("backend:autodojo",)
    assert part.semantics == ("agentdojo.suites@3",) and part.corpus_id is None and part.via is None  # item 27 (b)
    # phase 10 (D.6.13): the ROPE-hosted slice is a separate import part served by source rope
    slice_ = {c.part: c for c in source.capabilities}["rope-slice"]
    assert slice_.via == "rope" and slice_.owner == "rope" and slice_.profile == "autodojo-via-rope"
    assert slice_.import_status == "partial" and slice_.live_status is None and slice_.corpus_id == "rope"
    assert not any(c.part == "autodojo-via-rope" for r in REGISTRY for c in r.capabilities)
    caveat = part.caveat or ""
    assert "pilot 2026-10-22" in caveat and "U-18" in caveat and "ROPE" in caveat and "--max-cost-usd" in caveat


def test_factories_are_the_shared_capture_reader_and_mapper():
    part = _part()
    assert part.reader == READERS["agentprov.capture"] and part.mapper == MAPPERS["agentdojo.capture"]
    assert part.reader == _agentdojo_live().reader and part.mapper == _agentdojo_live().mapper
    assert callable(resolve_factory(part.reader)) and callable(resolve_factory(part.mapper))


def _agentdojo_live():
    return {c.part: c for c in get_source("agentdojo").capabilities}["live"]


def test_backend_descriptor():
    descriptor = BACKENDS["autodojo"]
    assert descriptor.project == "backends/autodojo" and descriptor.capture_mapper == "agentdojo.capture"
    assert descriptor.profile == "autodojo-live" and descriptor.protocol == "agentprov-backend/0.1"


def test_licence_is_the_forks_mit_notice():
    licence = get_source("autodojo").licence
    assert licence.spdx == "MIT" and licence.policy == "include" and licence.data_licence == "none"
    assert licence.holders == ("Xinhang Ma", "Taoran Li", "Chaowei Xiao", "Zhiyuan Yu", "Ning Zhang", "Yevgeniy Vorobeychik")
    assert licence.attribution == ("LICENSE (MIT)",) and not licence.restrictions
    assert get_source("autodojo").evidence_refs == ("sources/autodojo.md", "verify/autodojo.md")


def test_profile_is_package_data_with_a_digest_and_no_status():
    profile = load_profile("autodojo-live")
    assert profile.version == 3 and len(profile.sha256) == 64 and profile.family == "agentdojo"  # v2: D-656; v3: D-670/D-677
    assert profile.source_id == "autodojo" and profile.parts == ("live",) and "status" not in profile.data
    assert profile.sha256 != load_profile("agentdojo-live").sha256
    imp = profile.data["import"]
    assert imp["dialect"] == "agentprov.capture" and imp["mapper"] == "agentdojo.capture"
    assert tuple(imp["native"]["variants"]) == ("v1.k14", "v1.k14.incomplete")
    # agentdyn: the suite benchmark of an AgentDyn cell (regeneration-batch item 27 (a))
    assert dict(imp["rules"]) == {ns: load_catalogue(ns).version
                                  for ns in ("aer", "agentdojo", "agentdyn", "anthropic_messages", "cap")}


def test_profile_pins_the_fork_like_the_cache_check():
    profile = load_profile("autodojo-live")
    (pin,) = profile.data["source"]["pins"]
    assert pin["kind"] == "git" and pin["repo"] == AUTODOJO_REPO and pin["commit"] == AUTODOJO_COMMIT
    live = family_table(profile).data["live"]
    assert dict(live["pins"]) == {"repo": AUTODOJO_REPO, "commit": AUTODOJO_COMMIT, "subdirectory": "agentdojo"}
    assert tuple(profile.data["licence"]["holders"]) == get_source("autodojo").licence.holders


def test_family_part_conforms_to_the_closed_schema_both_checkers():
    jsonschema = pytest.importorskip("jsonschema")
    table = family_table(load_profile("autodojo-live"))
    jsonschema.validate(table.data, family_schema())
    assert check_against_schema(table.data, family_schema()) == []
    bad = json.loads(json.dumps(table.data))
    bad["live"]["unknown"] = 1
    assert check_against_schema(bad, family_schema())


def test_live_table_declares_d114():
    live = family_table(load_profile("autodojo-live")).data["live"]
    assert live["backend"] == "autodojo" and live["project"] == "backends/autodojo" and live["llm_element_default"] == "native"
    assert live["asserts"] == ["ToolsExecutionLoop.max_input_tokens is None or recorded"]
    assert live["refuse"] == ["defense in ['drift','progent','camel','camel_nopolicy']", "optimiser runs (variant_generation)"]
    assert live["instrumentation_extra"] == [
        "autodojo.fork_temperature_transmitted@1", "autodojo.fork_malformed_json_retry@1", "autodojo.env_nltk_preprovisioned@1",
        "autodojo.fork_system_role@1", "autodojo.fork_openrouter_extras@1", "autodojo.attack_cache_replay@1",
    ]  # fmt: skip  (D.11.4's three plus the items of D.11.7 item 9)
    assert dict(live["attack_cache"]) == {"attack": "autodojo", "sha256_param": "autodojo_cache_sha256",
                                          "variant_param": "autodojo_variant", "label": "raw/attack/autodojo-cache.json",
                                          "media": "application/json"}
    # the shared harness items are the AgentDojo live profile's, so one capture mapper serves both backends
    assert live["instrumentation_accepted"] == family_table(load_profile("agentdojo-live")).data["live"]["instrumentation_accepted"]


def test_run_error_quirk_has_the_forks_values():
    table = family_table(load_profile("autodojo-live"))
    quirk = table.quirk("agentdojo.run_error_imposes_outcome")
    assert quirk is not None and dict(quirk.params) == {"utility": False, "security": False, "extra_key": "error_type"}
    assert quirk.rules == ("agentdojo.run_error_imposed_outcome@1",)
    upstream = family_table(load_profile("agentdojo-live")).quirk("agentdojo.run_error_imposes_outcome")
    assert upstream is not None and upstream.params["security"] is True


def test_every_quirk_rule_exists_in_the_shipped_catalogue():
    catalogue = load_catalogue("agentdojo")
    table = family_table(load_profile("autodojo-live"))
    for quirk in table.quirks:
        for rule in quirk.rules:
            assert catalogue.get(rule) is not None, (quirk.id, rule)
    for rule in table.outcomes["origin_rules"]:
        assert catalogue.get(rule) is not None, rule


def test_agentdyn_suites_are_named_apart_from_agentdojo_suites():
    suites = family_table(load_profile("autodojo-live")).benchmark["suites"]
    assert {suites[s] for s in ("workspace", "travel", "banking", "slack")} == {"agentdojo"}
    assert {suites[s] for s in ("github", "shopping", "dailylife")} == {"agentdyn"}


# ---------------------------------------------------------------------------------------------- the run status gate


def test_run_gate_admits_scripted_and_real_runs_of_the_partial_part():
    """D-720: a ``partial`` live part admits both, with its caveat as a notice; what a real run then needs (endpoint
    class, consent, caps) is checked later (D-721, D-725; tests/integration/test_run_policy.py)."""
    from agentprov.cli.run import _live_capability

    for scripted in (True, False):
        result = CommandResult()
        capability = _live_capability("autodojo", result, scripted=scripted)
        assert capability.part == "live" and capability.backend == "autodojo"
        assert any(n.startswith("autodojo · live (partial): partial: real-model runs") for n in result.notices)

