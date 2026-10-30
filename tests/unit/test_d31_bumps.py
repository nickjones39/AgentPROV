"""D-31 strict integer bumps (regeneration-batch item 30; user decisions 2026-10-13: option B and regen-plan F-1(b)).

Every catalogue and source profile whose bytes changed since the version the stored corpora recorded is at version 2,
and version 1 ships under ``rules/archive/`` or ``profiles/archive/`` with exactly the recorded bytes, so a stored
corpus stays recomputable. Option B (H.2.5: one catalogue version per corpus): ``agentdojo.suites@1`` and
``inspect.agentharm@1`` keep declaring the catalogue version 1 for the stored corpora; regenerated corpora read
``agentdojo.suites@2`` (``@3`` for AgentDyn), which declare version 2 and carry item 1, and ``inspect.agentharm@2``,
``@1`` on version 2 (user decisions 2026-10-13).
``limits_sha256`` is a notice, not a declared version.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.reader import load_aer, load_aer_bytes
from agentprov.aer.rules import load_catalogue
from agentprov.corpus.derive import declared_identity
from agentprov.errors import ProfileError
from agentprov.prov.engine import derive
from agentprov.sem.engine import annotate, dumps_sem
from agentprov.sem.validate import validate_sem_document
from agentprov.validate import validate_prov

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "d31"

#: The digests the stored (-p10) corpora record in derivation.json for version 1 (the D-31 scan, 2026-10-13).
#: credleak (D-605, 2026-10-21): the digests the scratch corpora and the gui-build sealed copy record for version 1 (older
#: scratch corpora record earlier version-1 bytes, listed in DECISIONS D-605; they are reproduced at their building commit).
RECORDED_CATALOGUES = {
    "adprov": "28d877bca837", "agentdojo": "acd77579e522", "agentdyn": "7cb7ac1ada70", "credleak": "d355a2725e17",
    "inspect": "42fc5ed95c70", "rope": "ce17e9d4a900",
    "openhands": "9bc984f73823",  # D-606 (2026-10-21): recorded by the scratch openagentsafety corpora
    "dtap": "b4df2cb43941",  # D-607: the dtap-bench scratch corpora (pre-check L2, phase-10i remap) record dtap 1
}
RECORDED_PROFILES = {
    "adprov-v1": "00dc7981356b", "agentdojo-upstream": "a13b76ba7e22", "agentdyn": "afa4090ecc3c",
    "credleak-p15b": "1dce158a57ad", "mandate-agentdojo-eval": "e5bcd8db43cf", "rope": "a17aeb470fd3",
    "survey-runs": "db5cd1e79cd4",
    # D-456: v1 as the two pre-check scratch corpora recorded it (derivation.json aer profile_sha256; twins, 2026-10-15)
    "interbolt-agentdojo": "bfb6ef3a50b9",

    "whistlebench": "2275688dea24",  # D-601: the precheck scratch partials (l2-final-runs-j1/j2)

    # D-603: [withhold] added; version 1 as the phase-10n and pre-check scratch corpora record it
    "autogen-guard-placement": "1a7573f4e88a",
    "openagentsafety": "b5be1d99df75",  # D-606 (2026-10-21): precheck l2-head-j1/j2 and phase-10g oas-* record it
    "dtap-bench": "04d7c3275399",  # D-607: recorded by the dtap-bench scratch corpora
    # D-609: version 1 as the scratch trial and pre-check corpora record it (phase10o/trial/cam-j4, precheck l2 j1/j2)
    "code-agent-misalignment-geminicli": "965b84dc288b",
    # D-811: [withhold] added; version 1 as the stored corpora and the round's kept ast-survey-agentharm-rg1 record it
    "survey-agentharm": "b303208a27fc",
}
#: Profiles bumped again since D-31 (agentdyn 3: the part `history`, regeneration-batch item 95; survey-runs 3: the
#: [withhold] table, D-771, regeneration-batch item 171); their v2 is archived.
CURRENT_PROFILES = {"agentdyn": 4, "survey-runs": 3, "dtap-bench": 3}  # agentdyn 4: D-933; dtap-bench 3: D-934/D-935
#: Catalogues bumped again since D-31 (dtap 3: dtap.content_not_inlined@1, D-934); their v2 is archived.
CURRENT_CATALOGUES = {"dtap": 3}
SUITES_1 = "2193df73d60b960a43af8d7ad2e157b79e754804e45a274d8a3c4ddc239bd017"


@pytest.mark.parametrize("namespace", sorted(RECORDED_CATALOGUES))
def test_a_bumped_catalogue_ships_its_recorded_version_1(namespace):
    assert load_catalogue(namespace).version == CURRENT_CATALOGUES.get(namespace, 2) and load_catalogue(namespace, 2).version == 2
    archived = load_catalogue(namespace, 1)
    assert archived.version == 1 and archived.digest.startswith(RECORDED_CATALOGUES[namespace])


@pytest.mark.parametrize("profile_id", sorted(RECORDED_PROFILES))
def test_a_bumped_profile_ships_its_recorded_version_1(profile_id):
    assert load_profile(profile_id).version == CURRENT_PROFILES.get(profile_id, 2) and load_profile(profile_id, 2).version == 2
    archived = load_profile(profile_id, 1)
    assert archived.version == 1 and archived.sha256.startswith(RECORDED_PROFILES[profile_id])


def test_a_version_that_is_not_shipped_is_refused():
    with pytest.raises(ProfileError, match="version 7 is not shipped"):
        load_profile("agentdyn", 7)
    with pytest.raises(ProfileError):
        load_profile("agentdyn", 0)


def test_the_semantics_profiles_declare_the_catalogue_version_of_option_b():
    assert {v: dict(load_semantics_profile("agentdojo.suites", v).rules) for v in (1, 2, 3)} == \
        {1: {"agentdojo": 1}, 2: {"agentdojo": 2}, 3: {"agentdojo": 2}}
    assert load_semantics_profile("agentdojo.suites", 1).sha256 == SUITES_1  # unchanged: the stored corpora's
    assert {v: dict(load_semantics_profile("inspect.agentharm", v).rules) for v in (1, 2)} == \
        {1: {"inspect": 1}, 2: {"inspect": 2}}
    assert {v: dict(load_semantics_profile("dtap.tools", v).rules) for v in (1, 2, 3)} == \
        {1: {"dtap": 1}, 2: {"dtap": 2}, 3: {"dtap": 3}}  # D-607; 3: D-934


def test_a_stored_suites_1_sem_recomputes_byte_identically_against_the_archived_catalogue():
    """A stored AER and its stored suites@1 SEM (tests/fixtures/d31, written with agentdojo@1 and adprov-v1@1): the SEM is
    rebuilt byte for byte (the catalogue version 1 now comes from rules/archive/) and passes tier 3."""
    doc = load_aer(FIXTURES / "r01.aer.jsonl")
    assert doc.header["rules"] == {"adprov": 1, "aer": 1, "agentdojo": 1}
    assert doc.header["profile"]["version"] == 1
    profile = load_semantics_profile("agentdojo.suites", 1)
    sem = annotate(doc, profile)
    assert dumps_sem(sem) == (FIXTURES / "r01.sem.jsonl").read_bytes()
    assert validate_sem_document(sem, doc, mode="release", profile=profile).ok


def test_a_regenerated_corpus_reads_one_catalogue_version_and_passes_tier_4():
    """Option B with item 1: a freshly mapped AER declares agentdojo@2, the registry gives its corpus suites@2, whose SEM
    declares agentdojo@2 too (H.2.5), and PROV passes tier 4. The stored corpora's suites@1 is selected by none."""
    import sys  # noqa: PLC0415

    from agentprov.adapters.registry import REGISTRY  # noqa: PLC0415

    sys.path.insert(0, str(REPO / "tests" / "golden"))
    import test_v1_round_trip as v1  # noqa: PLC0415 - the golden helpers live with the golden tests

    selected = {s for r in REGISTRY for c in r.capabilities for s in c.semantics}
    assert "agentdojo.suites@1" not in selected and "inspect.agentharm@1" not in selected
    pair = v1.PAIRS[0]
    outcome, _ = map_artefact(v1._source(pair), v1._origin(pair), profile_id="adprov-v1")
    data, _info = aer_bytes(outcome)
    doc = load_aer_bytes(data)
    assert doc.header["rules"]["agentdojo"] == 2
    two = load_semantics_profile("agentdojo.suites", 2)
    sem = annotate(doc, two)
    assert json.loads(dumps_sem(sem).split(b"\n", 1)[0])["rules"] == {"agentdojo": 2}
    result = derive(doc, [sem], sem_profiles={(two.id, two.version): two})
    report = validate_prov(result.prov_json, doc, migration=True, sems=[sem])
    assert report.ok, [(o.id, sorted(o.codes())) for o in report.outcomes if o.status == "fail"]


def test_limits_sha256_is_not_a_declared_version():
    stage = {"stage": "aer", "fn": "map", "adapter": "x", "limits_sha256": "sha256:" + "0" * 64, "fn_digest": "sha256:1"}
    other = {**stage, "limits_sha256": "sha256:" + "f" * 64}
    assert declared_identity(stage) == declared_identity(other)
    assert declared_identity(stage) != declared_identity({**stage, "adapter": "y"})
