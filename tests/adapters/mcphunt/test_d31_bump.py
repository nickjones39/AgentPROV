"""The D-31 bumps of the mcphunt family: regen items 38-41 (bug pass; user-approved 2026-10-14) and D-1063 (regen-batch
row 176, review UC-40: the lone-surrogate rule).

Catalogue ``mcphunt`` is at version 3 and profile ``mcphunt`` at version 4; every earlier version ships under ``archive/``
with exactly the bytes the stored or sealed corpora recorded (version 2 and profile version 3: the sealed mcphunt-w2b),
so a stored corpus stays recomputable. ``mcphunt.tools@N`` reads catalogue version N (H.2.5: one catalogue version per
corpus), and a freshly mapped AER, its SEM and its PROV agree on version 3 and pass tiers 3 and 4.
"""

from __future__ import annotations

import hashlib
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
#: What the sealed corpus mcphunt-w2b records (derivation.json, aer stage), archived by D-1063.
SEALED_CATALOGUE_V2 = "081a6291ee9db4826573e3b715479d1c4c8487b0b27fad6554bbc7a379b7b2b0"
SEALED_PROFILE_V3 = "22a89afa6e225257d620271da57e4664ee8df0633c6f4a2d09d8b4e16fda5269"
SRC = support.REPO / "src" / "agentprov" / "adapters" / "mcphunt"


def test_catalogue_and_profile_are_current_and_ship_every_recorded_version_unchanged():
    assert load_catalogue("mcphunt").version == 3
    archived = load_catalogue("mcphunt", 1)
    assert archived.version == 1 and archived.digest.startswith(RECORDED_CATALOGUE_V1)
    assert "unplaced_message" in load_catalogue("mcphunt", 2).issue_codes and "unplaced_message" not in archived.issue_codes
    assert load_profile("mcphunt").version == 4  # D-1063; v3 (D-931, the sealed mcphunt-w2b records it) archived
    assert load_profile("mcphunt", 2).sha256.startswith("2c2989b20669")
    old = load_profile("mcphunt", 1)
    assert old.version == 1 and old.sha256.startswith(RECORDED_PROFILE_V1)


def test_d1063_archives_the_sealed_versions_byte_exact_and_only_adds_the_surrogate_rule():
    v2_bytes = (SRC / "rules" / "archive" / "mcphunt.rules.v2.toml").read_bytes()
    assert hashlib.sha256(v2_bytes).hexdigest() == SEALED_CATALOGUE_V2 == load_catalogue("mcphunt", 2).digest
    p3_bytes = (SRC / "profiles" / "archive" / "mcphunt.profile.v3.toml").read_bytes()
    assert hashlib.sha256(p3_bytes).hexdigest() == SEALED_PROFILE_V3 == load_profile("mcphunt", 3).sha256
    v2, v3 = load_catalogue("mcphunt", 2), load_catalogue("mcphunt", 3)
    # the surrogate rule (row 176) and, in place before any corpus records version 3, the not-inlined rule (row 181)
    assert set(v3.rules) - set(v2.rules) == {"mcphunt.lone_surrogate_replaced@1", "mcphunt.content_not_inlined@1"}
    assert all(v3.rules[rid] == rule for rid, rule in v2.rules.items())
    assert v3.issue_codes - v2.issue_codes == {"lone_surrogate_replaced", "content_not_inlined"}
    root = SRC / "semantics"
    assert (root / "mcphunt.tools-2" / "tools.toml").read_bytes() == (root / "mcphunt.tools-3" / "tools.toml").read_bytes()


def test_each_semantics_version_reads_its_own_catalogue_version():
    assert dict(load_semantics_profile("mcphunt.tools", 1).rules) == {"mcphunt": 1}
    assert dict(load_semantics_profile("mcphunt.tools", 2).rules) == {"mcphunt": 2}
    assert dict(load_semantics_profile("mcphunt.tools", 3).rules) == {"mcphunt": 3}


def test_a_new_aer_its_sem_and_prov_agree_on_version_3_and_pass_tiers_3_and_4():
    mapped = support.map_trace(next(iter(support.criteria())), sem=True, prov=True)
    assert mapped.header["rules"]["mcphunt"] == 3
    assert json.loads(dumps_sem(mapped.sem).split(b"\n", 1)[0])["rules"] == {"mcphunt": 3}
    profile = load_semantics_profile("mcphunt.tools", support.SEM_VERSION)
    assert validate_sem_document(mapped.sem, mapped.doc, mode="release", profile=profile).ok
    report = validate_prov(mapped.prov.prov_json, mapped.doc, sems=[mapped.sem])
    assert report.ok, [(o.id, sorted(o.codes())) for o in report.outcomes if o.status == "fail"]
