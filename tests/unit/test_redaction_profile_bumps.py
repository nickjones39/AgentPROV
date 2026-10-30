"""Regeneration-batch items 106 and 107 bump three profiles to version 2 and archive version 1 byte for byte, because
scratch corpora record version 1 (the D-31 owner's ruling, 2026-10-21). Version 1 predates the redaction: corpora
recording it must never be sealed or deposited."""

from __future__ import annotations

import pytest

from agentprov.adapters.profiles import load_profile

#: The v1 digests the scratch corpora record (origin/main 37be83cd's files).
ARCHIVED_V1 = {
    "environmentoptim-agentdojo": "f55a44bd89b2",
    "kexin-xu-01-agentharm": "df445ef1dac5",
    "fragfuse-agentharm": "1943f6f39974",
}


@pytest.mark.parametrize("profile_id", sorted(ARCHIVED_V1))
def test_version_2_is_current_and_version_1_is_archived_byte_for_byte(profile_id):
    assert load_profile(profile_id).version == 2
    archived = load_profile(profile_id, 1)
    assert archived.version == 1 and archived.sha256.startswith(ARCHIVED_V1[profile_id])


@pytest.mark.parametrize("profile_id", sorted(ARCHIVED_V1))
def test_version_1_declares_no_redaction_and_version_2_does(profile_id):
    family = load_profile(profile_id).data["profile"]["family"]
    assert load_profile(profile_id).data["family"][family].get("redact")
    assert not load_profile(profile_id, 1).data["family"][family].get("redact")
