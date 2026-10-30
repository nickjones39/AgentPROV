"""The D-31 bump of the mcphunt family with regen items 38-41 (bug pass; user-approved 2026-10-14, held for the round).

Catalogue ``mcphunt`` and profile ``mcphunt`` are at version 2; version 1 of each ships under ``archive/`` with exactly
the bytes the stored corpora recorded, so a stored corpus stays recomputable. ``mcphunt.tools@1`` keeps reading
catalogue version 1 and ``@2`` reads version 2 (H.2.5: one catalogue version per corpus), and a freshly mapped AER, its
SEM and its PROV agree on version 2 and pass tiers 3 and 4.
"""

from __future__ import annotations

import json

import mcphunt_support as support

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue
from agentprov.sem.engine import dumps_sem
from agentprov.sem.validate import validate_sem_document
from agentprov.validate import validate_prov

#: The digests version 1 had on main before the bump (what a stored corpus records).
RECORDED_CATALOGUE_V1 = "e41b2eb12794"
RECORDED_PROFILE_V1 = "c43ae1e0805b"


def test_catalogue_and_profile_are_at_version_2_and_ship_version_1_unchanged():
    assert load_catalogue("mcphunt").version == 2
    archived = load_catalogue("mcphunt", 1)
    assert archived.version == 1 and archived.digest.startswith(RECORDED_CATALOGUE_V1)
    assert "unplaced_message" in load_catalogue("mcphunt").issue_codes and "unplaced_message" not in archived.issue_codes
    assert load_profile("mcphunt").version == 3  # D-931: the map cap; v2 (the failed wave-2 tree records it) archived
    assert load_profile("mcphunt", 2).sha256.startswith("2c2989b20669")
    old = load_profile("mcphunt", 1)
    assert old.version == 1 and old.sha256.startswith(RECORDED_PROFILE_V1)


def test_each_semantics_version_reads_its_own_catalogue_version():
    assert dict(load_semantics_profile("mcphunt.tools", 1).rules) == {"mcphunt": 1}
    assert dict(load_semantics_profile("mcphunt.tools", 2).rules) == {"mcphunt": 2}


def test_a_new_aer_its_sem_and_prov_agree_on_version_2_and_pass_tiers_3_and_4():
    mapped = support.map_trace(next(iter(support.criteria())), sem=True, prov=True)
    assert mapped.header["rules"]["mcphunt"] == 2
    assert json.loads(dumps_sem(mapped.sem).split(b"\n", 1)[0])["rules"] == {"mcphunt": 2}
    profile = load_semantics_profile("mcphunt.tools", support.SEM_VERSION)
    assert validate_sem_document(mapped.sem, mapped.doc, mode="release", profile=profile).ok
    report = validate_prov(mapped.prov.prov_json, mapped.doc, sems=[mapped.sem])
    assert report.ok, [(o.id, sorted(o.codes())) for o in report.outcomes if o.status == "fail"]
