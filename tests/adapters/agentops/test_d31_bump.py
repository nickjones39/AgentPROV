"""The D-31 bump of the agentops family with regen items 34-37 (bug pass; user-approved 2026-10-14, held for the round).

Catalogue ``agentops`` and profile ``agentops-bench-pilot`` are at version 2; version 1 of each ships under ``archive/``
with exactly the bytes the stored corpora recorded. ``agentops.tools@1`` keeps reading catalogue version 1 and ``@2``
reads version 2 (H.2.5).
"""

from __future__ import annotations

import agentops_support as support

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue

#: The digests version 1 had on main before the bump (what a stored corpus records).
RECORDED_CATALOGUE_V1 = "5a9e6a03bf42"
RECORDED_PROFILE_V1 = "6e109f28477a"  # phase 10i's in-place v1 change (04e9540d)


def test_catalogue_and_profile_are_at_version_2_and_ship_version_1_unchanged():
    assert load_catalogue("agentops", 2).version == 2  # archived since D-1063 (version 3)
    archived = load_catalogue("agentops", 1)
    assert archived.version == 1 and archived.digest.startswith(RECORDED_CATALOGUE_V1)
    assert "payload_outside_adversarial" in load_catalogue("agentops", 2).issue_codes
    assert "payload_outside_adversarial" not in archived.issue_codes
    assert load_profile(support.PROFILE, 2).version == 2
    old = load_profile(support.PROFILE, 1)
    assert old.version == 1 and old.sha256.startswith(RECORDED_PROFILE_V1)


def test_each_semantics_version_reads_its_own_catalogue_version():
    assert dict(load_semantics_profile("agentops.tools", 1).rules) == {"agentops": 1}
    assert dict(load_semantics_profile("agentops.tools", 2).rules) == {"agentops": 2}


#: D-1063 (regen-batch row 176): the bytes the sealed corpus agentops-bench-w2 records (derivation.json aer stage).
SEALED_CATALOGUE_V2 = "4bb412504d1c04e79708c5b0e456fdbc6593d0bf3f3155f436228cef297588fb"
SEALED_PROFILE_V2 = "9c9dad74ff9f36187043d526dd8853e4ddd5b5d103d5387f7d9e605a777cac6e"


def test_d1063_version_3_is_current_and_version_2_ships_byte_exact():
    import hashlib

    src = support.REPO / "src" / "agentprov" / "adapters" / "agentops"
    archived = (src / "rules" / "archive" / "agentops.rules.v2.toml").read_bytes()
    assert hashlib.sha256(archived).hexdigest() == SEALED_CATALOGUE_V2 == load_catalogue("agentops", 2).digest
    profile = (src / "profiles" / "archive" / "agentops-bench-pilot.profile.v2.toml").read_bytes()
    assert hashlib.sha256(profile).hexdigest() == SEALED_PROFILE_V2 == load_profile(support.PROFILE, 2).sha256
    v2, v3 = load_catalogue("agentops", 2), load_catalogue("agentops")
    assert v3.version == 3 and load_profile(support.PROFILE).version == 3
    # row 182 (AU-RC-3) adds agentops.payload_marker_not_inlined@1 to the unreleased version 3
    assert set(v3.rules) - set(v2.rules) == {"agentops.lone_surrogate_replaced@1", "agentops.content_not_inlined@1",
                                             "agentops.payload_marker_not_inlined@1"}
    assert all(v3.rules[rid] == rule for rid, rule in v2.rules.items())
    assert v3.issue_codes - v2.issue_codes == {"lone_surrogate_replaced", "content_not_inlined"}
    assert dict(load_semantics_profile("agentops.tools", 3).rules) == {"agentops": 3}
    root = src / "semantics"
    assert (root / "agentops.tools-2" / "tools.toml").read_bytes() == (root / "agentops.tools-3" / "tools.toml").read_bytes()
