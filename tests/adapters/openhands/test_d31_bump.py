"""The D-31 bump of the openhands family with D-606 (bug pass bugpass-perf-10; user-approved 2026-10-21, held).

Catalogue ``openhands`` and profile ``openagentsafety`` are at version 2; version 1 of each ships under ``archive/`` with
exactly the bytes the scratch corpora recorded (pinned in tests/unit/test_d31_bumps.py). ``openhands.tools@1`` keeps
reading catalogue version 1 with its recorded digest and ``@2`` reads version 2 (H.2.5). ``redcode-exec-openhands`` is
recorded by no corpus, so it is edited in place at version 1.
"""

from __future__ import annotations

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue

#: The digest of openhands.tools@1 the scratch corpora record (stages[1].profiles in derivation.json).
RECORDED_TOOLS_1 = "f7988322c1bd"


def test_each_semantics_version_reads_its_own_catalogue_version():
    one, two = load_semantics_profile("openhands.tools", 1), load_semantics_profile("openhands.tools", 2)
    assert dict(one.rules) == {"openhands": 1} and one.sha256.startswith(RECORDED_TOOLS_1)
    assert dict(two.rules) == {"openhands": 2}
    assert "value_redacted" in load_catalogue("openhands").issue_codes
    assert "value_redacted" not in load_catalogue("openhands", 1).issue_codes


def test_the_profiles_select_the_bumped_versions():
    oas = load_profile("openagentsafety")
    assert oas.version == 2 and load_profile("openagentsafety", 1).family_table()["semantics_profile"]["version"] == 1
    assert "redact" not in load_profile("openagentsafety", 1).family_table()
    redcode = load_profile("redcode-exec-openhands")
    assert redcode.version == 1  # recorded by no corpus: edited in place (D-31)
    for profile in (oas, redcode):
        assert dict(profile.family_table()["semantics_profile"]) == {"id": "openhands.tools", "version": 2}
