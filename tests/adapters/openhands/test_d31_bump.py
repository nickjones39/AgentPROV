"""The D-31 bumps of the openhands family.

D-606 (bug pass bugpass-perf-10; user-approved 2026-10-21): catalogue ``openhands`` and profile ``openagentsafety`` went
to version 2; version 1 of each ships under ``archive/`` with exactly the bytes the scratch corpora recorded (pinned in
tests/unit/test_d31_bumps.py). ``openhands.tools@1`` keeps reading catalogue version 1 with its recorded digest and
``@2`` reads version 2 (H.2.5).

D-1063 (regen-batch row 176; review UC-40): the rule ``openhands.lone_surrogate_replaced@1`` mints catalogue version 3;
version 2, which the sealed corpora openagentsafety-w2 and redcode-exec-openhands-w2 record, ships under ``archive/``
byte-exact, as do ``openagentsafety`` version 2 and ``redcode-exec-openhands`` version 1. ``openhands.tools@3`` is
``@2``'s tables on catalogue version 3, and both profiles select it.
"""

from __future__ import annotations

import hashlib
from importlib import resources

import openhands_support as support

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue

PACKAGE = "agentprov.adapters.openhands"
#: The digest of openhands.tools@1 the scratch corpora record (stages[1].profiles in derivation.json).
RECORDED_TOOLS_1 = "f7988322c1bd"
#: What the sealed wave-2 corpora record (derivation.json aer stage): catalogue openhands 2 and the two profiles.
SEALED_CATALOGUE_V2 = "e2e1cd2be7bb1c0b445b1137bc3f80cd9d4df3e0e8ea7b89f634323ac650aa28"
SEALED_OAS_V2 = "3bb617ab193942e6da6310cc9fc47450baf7711374ea5dfca196783a496246f4"
SEALED_REDCODE_V1 = "54324b24a775b8b46bbffd046b0d17a8480c77f85bab68207ece07b6e810f76c"


def test_each_semantics_version_reads_its_own_catalogue_version():
    one, two, three = (load_semantics_profile("openhands.tools", v) for v in (1, 2, 3))
    assert dict(one.rules) == {"openhands": 1} and one.sha256.startswith(RECORDED_TOOLS_1)
    assert dict(two.rules) == {"openhands": 2} and dict(three.rules) == {"openhands": 3}
    assert three.tables == two.tables and dict(three.classes) == dict(two.classes)
    root = support.REPO / "src" / "agentprov" / "adapters" / "openhands" / "semantics"
    assert (root / "openhands.tools-2" / "tools.toml").read_bytes() == (root / "openhands.tools-3" / "tools.toml").read_bytes()
    assert "value_redacted" in load_catalogue("openhands").issue_codes
    assert "value_redacted" not in load_catalogue("openhands", 1).issue_codes


def test_catalogue_version_2_is_archived_as_sealed_and_version_3_only_adds_the_surrogate_rule():
    archived = (resources.files(PACKAGE) / "rules" / "archive" / "openhands.rules.v2.toml").read_bytes()
    assert hashlib.sha256(archived).hexdigest() == SEALED_CATALOGUE_V2 == load_catalogue("openhands", 2).digest
    v2, v3 = load_catalogue("openhands", 2), load_catalogue("openhands")
    assert v3.version == 3 and set(v3.rules) - set(v2.rules) == {"openhands.lone_surrogate_replaced@1"}
    assert all(v3.rules[rid] == rule for rid, rule in v2.rules.items())
    assert v3.issue_codes - v2.issue_codes == {"lone_surrogate_replaced"}


def test_the_profiles_select_the_bumped_versions():
    oas = load_profile("openagentsafety")
    assert oas.version == 3 and load_profile("openagentsafety", 1).family_table()["semantics_profile"]["version"] == 1
    assert "redact" not in load_profile("openagentsafety", 1).family_table()
    assert load_profile("openagentsafety", 2).sha256 == SEALED_OAS_V2
    redcode = load_profile("redcode-exec-openhands")
    assert redcode.version == 2 and load_profile("redcode-exec-openhands", 1).sha256 == SEALED_REDCODE_V1
    for profile in (oas, redcode):
        assert dict(profile.family_table()["semantics_profile"]) == {"id": "openhands.tools", "version": 3}
    for old in (load_profile("openagentsafety", 2), load_profile("redcode-exec-openhands", 1)):
        assert dict(old.family_table()["semantics_profile"]) == {"id": "openhands.tools", "version": 2}
