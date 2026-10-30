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
    assert load_catalogue("agentops").version == 2
    archived = load_catalogue("agentops", 1)
    assert archived.version == 1 and archived.digest.startswith(RECORDED_CATALOGUE_V1)
    assert "payload_outside_adversarial" in load_catalogue("agentops").issue_codes
    assert "payload_outside_adversarial" not in archived.issue_codes
    assert load_profile(support.PROFILE).version == 2
    old = load_profile(support.PROFILE, 1)
    assert old.version == 1 and old.sha256.startswith(RECORDED_PROFILE_V1)


def test_each_semantics_version_reads_its_own_catalogue_version():
    assert dict(load_semantics_profile("agentops.tools", 1).rules) == {"agentops": 1}
    assert dict(load_semantics_profile("agentops.tools", 2).rules) == {"agentops": 2}
