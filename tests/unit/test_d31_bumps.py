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
#: agentdyn 4: D-933; dtap-bench 3: D-934/D-935, dtap-bench 4: UC-40 (v3, which dtap-bench-w2c records, is archived)
CURRENT_PROFILES = {"agentdyn": 5, "survey-runs": 4, "dtap-bench": 4,
                    # D-1063 (regen-batch row 176): version 3 of the wave-2 families' profiles
                    "autogen-guard-placement": 3, "openagentsafety": 3, "code-agent-misalignment-geminicli": 3,
                    "credleak-p15b": 3,
                    # D-1063 (regen-batch row 179, group V1): one more for every profile declaring catalogue agentdojo
                    "agentdojo-upstream": 3, "interbolt-agentdojo": 3, "mandate-agentdojo-eval": 3, "rope": 3}
#: Catalogues bumped again since D-31 (dtap 3: dtap.content_not_inlined@1, D-934; dtap 4: dtap.lone_surrogate_replaced@1,
#: UC-40); their v2 (and dtap v3) is archived. credleak 3, openhands 3: D-1063 (row 176).
CURRENT_CATALOGUES = {"dtap": 4, "credleak": 3, "openhands": 3,
                      "adprov": 3,  # adprov 3: D-1063 (row 180; AU-RB-6, UC-41)
                      "agentdojo": 3, "agentdyn": 3}  # V1: row 179
#: Versions after 2 that a sealed corpus records, with their digests (derivation.json): archived byte for byte.
RECORDED_LATER = {("dtap-bench", 3): "b769b6be569a19bae1e9913895bd597c9bd64a19609405a636a445ab2085cbda"}  # dtap-bench-w2c


def test_a_later_profile_version_a_sealed_corpus_records_is_archived():
    for (profile_id, version), digest in RECORDED_LATER.items():
        archived = load_profile(profile_id, version)
        assert archived.version == version and archived.sha256.removeprefix("sha256:") == digest


#: D-1063 (regen-batch row 176; review UC-39..UC-41): the catalogue and profile versions the sealed wave-2 corpora
#: record (derivation.json aer stage: rules_sha256, profile_sha256; read 2026-11-05), each archived byte-exact when
#: the lone-surrogate and not-inlined rules bumped it. (namespace or profile id, version) -> digest prefix.
SEALED_CATALOGUES = {
    ("agentops", 2): "4bb412504d1c", ("autogen", 1): "2b7fb400c09b", ("credleak", 2): "2059d34551d5",
    ("geminicli", 1): "96dda696e9b8", ("mcphunt", 2): "081a6291ee9d", ("openhands", 2): "e2e1cd2be7bb",
    ("qwencode", 2): "0366477b79d4", ("wirelog", 1): "7a473ef1f8d5",
    ("adprov", 2): "92a4071ef26b",  # adprov-v1-release-rg2 (D-1063, regen-batch row 180)
    # V1 (regen-batch row 179): every agentdojo-family corpus records agentdojo 2; AgentDyn's agentdyn 2, memo-ozdincer's
    # rescont 2
    ("agentdojo", 2): "5837bf2fef8c", ("agentdyn", 2): "a34bc45f6fe0", ("rescont", 2): "1c1f91410d63",
}
SEALED_PROFILES = {
    ("agentops-bench-pilot", 2): "9c9dad74ff9f", ("autogen-guard-placement", 2): "0f3469c8b4fb",
    ("code-agent-misalignment-geminicli", 2): "7e807cff6ea3", ("credleak-p15b", 2): "44a5c13d3c8d",
    ("mcphunt", 3): "22a89afa6e22", ("openagentsafety", 2): "3bb617ab1939", ("redcode-exec-openhands", 1): "54324b24a775",
    ("redcode-exec-qwencode", 2): "cd8895111ad7", ("what-surrounds", 1): "ed4849b26a47",
    # V1 (regen-batch row 179): the agentdojo-family profile versions the 34 sealed corpora of the family record
    ("agentdojo-upstream", 2): "ab0ccd4f8e55", ("agentdyn", 4): "c110848c54a0", ("aiauthz-agentdojo", 1): "6aab7926254e",
    ("authority-caps-agentdojo", 1): "e691d4be6c82", ("bookkeeper-agentdojo", 1): "ed9e8fdd66fd",
    ("ceferisbarov-agentdojo", 1): "26567f5cca50", ("craibench-agentdojo", 1): "77787056ba3e",
    ("dca-agentdojo", 1): "a8194b19c154", ("drift", 1): "50cacc9c4186", ("drift1-agentdojo", 1): "3df46db9ad3d",
    ("gate-agentdojo", 1): "cf2c70ccc2cc", ("geryon-agentdojo", 2): "edf246e4c3d5", ("glitch-agentdojo", 1): "32ccefc8e223",
    ("hilarytorn-trajectory-poisoning", 1): "eadaf8892409", ("interbolt-agentdojo", 2): "8c21564ac752",
    ("ipi-defenses-agentdojo", 1): "904eb7c38357", ("kavach-agentdojo", 1): "c7002b1d1821",
    ("kongminos-agentdojo", 2): "fb06626f80cf", ("linyxus-agentdojo", 1): "9901b7d36424",
    ("llm-lock-agentdojo", 1): "3a35e8f40ca4", ("mandate-agentdojo-eval", 2): "044e96431a4d",
    ("melon-agentdojo", 2): "45408056c6bd", ("memo-ozdincer-agentdojo", 2): "3391c5bd3294",
    ("menelaus29-ipi-multidomain", 1): "349323d6c9ea", ("mohameduk-agentdojo", 1): "1e89d7f19e50", ("rope", 2): "4cd87b53d8ff",
    ("seagent-agentdojo", 2): "1fe1c62a1088", ("sentry-agentdojo", 1): "a2ec1024fde2",
    ("shreeyavarma-llm-safety", 1): "208cd7eb4378", ("survey-runs", 3): "ad3bb3414056", ("tacit-agentdojo", 2): "f053577d53d2",
    ("yockcheng-prompt-injection-harness", 1): "2bda7d01b119",
}
#: V1 (regen-batch row 179): profiles bumped with catalogue agentdojo 3 whose previous version no sealed corpus records
#: (the live profiles and the retired environmentoptim-agentdojo); archived byte-exact all the same (full digests).
UNSEALED_ARCHIVED = {
    ("agentdojo-live", 3): "29a4d916ec27e5cfe1780d08fe27f194d735481ec7d4effad09da6319c09456f",
    ("agentdyn-live", 1): "b580d470ff40857e13ecdd89e47078e65f38349ab219e032e0c21b44fdd0dd29",
    ("autodojo-live", 3): "c0c47580e772e75cc5234098e733847164b711a45561a3ef822e452181db71c2",
    ("environmentoptim-agentdojo", 2): "f582dc79b11358755cd99f156fd57f1d2162ca0decce85e19e35c084952ea8cd",
}
#: The semantics profile each D-1063 bump selects, and the catalogue version it declares (H.2.5).
SEALED_SEMANTICS = {"agentops.tools": (3, "agentops", 3), "autogen.tools": (2, "autogen", 2),
                    "credleak.tools": (3, "credleak", 3), "geminicli.tools": (2, "geminicli", 2),
                    "mcphunt.tools": (3, "mcphunt", 3), "openhands.tools": (3, "openhands", 3),
                    "qwencode.tools": (3, "qwencode", 3), "wirelog.tools": (2, "wirelog", 2)}
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


@pytest.mark.parametrize(("namespace", "version"), sorted(SEALED_CATALOGUES))
def test_a_catalogue_a_sealed_corpus_records_is_archived_byte_exact(namespace, version):
    """D-1063: the sealed version stays loadable with its recorded bytes; the current one is the next version."""
    assert load_catalogue(namespace).version == version + 1
    archived = load_catalogue(namespace, version)
    assert archived.version == version and archived.digest.startswith(SEALED_CATALOGUES[(namespace, version)])


@pytest.mark.parametrize(("profile_id", "version"), sorted(SEALED_PROFILES))
def test_a_profile_a_sealed_corpus_records_is_archived_byte_exact(profile_id, version):
    assert load_profile(profile_id).version == version + 1
    archived = load_profile(profile_id, version)
    assert archived.version == version and archived.sha256.startswith(SEALED_PROFILES[(profile_id, version)])


@pytest.mark.parametrize("profile_id", sorted(SEALED_SEMANTICS))
def test_the_bumped_semantics_profile_declares_the_bumped_catalogue(profile_id):
    version, namespace, catalogue = SEALED_SEMANTICS[profile_id]
    assert dict(load_semantics_profile(profile_id, version).rules) == {namespace: catalogue}
    assert dict(load_semantics_profile(profile_id, version - 1).rules) == {namespace: catalogue - 1}


@pytest.mark.parametrize(("profile_id", "version"), sorted(UNSEALED_ARCHIVED))
def test_a_profile_bumped_with_agentdojo_3_ships_its_previous_version(profile_id, version):
    assert load_profile(profile_id).version == version + 1
    archived = load_profile(profile_id, version)
    assert archived.version == version and archived.sha256 == UNSEALED_ARCHIVED[(profile_id, version)]


def test_every_profile_declaring_an_agentdojo_family_catalogue_declares_its_current_version():
    """V1 (D-1063): one catalogue version per corpus (H.2.5) needs every current profile on the shipped version."""
    import tomllib  # noqa: PLC0415

    for path in sorted((REPO / "src" / "agentprov" / "adapters").glob("*/profiles/*.profile.toml")):
        pid = tomllib.loads(path.read_text(encoding="utf-8"))["profile"]["id"]
        declared = dict((load_profile(pid).data.get("import") or {}).get("rules") or {})
        for ns in ("agentdojo", "agentdyn", "rescont"):
            if ns in declared:
                assert declared[ns] == load_catalogue(ns).version == 3, (pid, ns)


def test_a_version_that_is_not_shipped_is_refused():
    with pytest.raises(ProfileError, match="version 7 is not shipped"):
        load_profile("agentdyn", 7)
    with pytest.raises(ProfileError):
        load_profile("agentdyn", 0)


def test_the_semantics_profiles_declare_the_catalogue_version_of_option_b():
    assert {v: dict(load_semantics_profile("agentdojo.suites", v).rules) for v in (1, 2, 3, 4, 5)} == \
        {1: {"agentdojo": 1}, 2: {"agentdojo": 2}, 3: {"agentdojo": 2}, 4: {"agentdojo": 3}, 5: {"agentdojo": 3}}
    # V1 (D-1063): @4 and @5 are @2 and @3 on catalogue agentdojo 3, every data file but profile.toml a byte copy
    for old, new in ((2, 4), (3, 5)):
        a, b = load_semantics_profile("agentdojo.suites", old), load_semantics_profile("agentdojo.suites", new)
        assert a.tables == b.tables and a.classes == b.classes
    assert load_semantics_profile("agentdojo.suites", 1).sha256 == SUITES_1  # unchanged: the stored corpora's
    assert {v: dict(load_semantics_profile("inspect.agentharm", v).rules) for v in (1, 2)} == \
        {1: {"inspect": 1}, 2: {"inspect": 2}}
    assert {v: dict(load_semantics_profile("dtap.tools", v).rules) for v in (1, 2, 3, 4)} == \
        {1: {"dtap": 1}, 2: {"dtap": 2}, 3: {"dtap": 3}, 4: {"dtap": 4}}  # D-607; 3: D-934; 4: UC-40


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
    assert not {"agentdojo.suites@2", "agentdojo.suites@3"} & selected  # V1 (D-1063): @4 and @5 on catalogue 3
    pair = v1.PAIRS[0]
    outcome, _ = map_artefact(v1._source(pair), v1._origin(pair), profile_id="adprov-v1")
    data, _info = aer_bytes(outcome)
    doc = load_aer_bytes(data)
    assert doc.header["rules"]["agentdojo"] == 3  # V1 (D-1063)
    two = load_semantics_profile("agentdojo.suites", 4)
    sem = annotate(doc, two)
    assert json.loads(dumps_sem(sem).split(b"\n", 1)[0])["rules"] == {"agentdojo": 3}
    result = derive(doc, [sem], sem_profiles={(two.id, two.version): two})
    report = validate_prov(result.prov_json, doc, migration=True, sems=[sem])
    assert report.ok, [(o.id, sorted(o.codes())) for o in report.outcomes if o.status == "fail"]


def test_limits_sha256_is_not_a_declared_version():
    stage = {"stage": "aer", "fn": "map", "adapter": "x", "limits_sha256": "sha256:" + "0" * 64, "fn_digest": "sha256:1"}
    other = {**stage, "limits_sha256": "sha256:" + "f" * 64}
    assert declared_identity(stage) == declared_identity(other)
    assert declared_identity(stage) != declared_identity({**stage, "adapter": "y"})
