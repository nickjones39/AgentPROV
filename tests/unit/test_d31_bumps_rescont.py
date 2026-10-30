"""D-31 bump of the `rescont` catalogue and the memo-ozdincer-agentdojo profile (bug pass new families, regen items 116 and
118; D-31 ruling of 2026-10-21, option A).

The scratch trial corpora of phase 10q record main's version-1 bytes (main at 93c02c6f, before the bug pass edited the
catalogue in place). The catalogue gained the issue codes ``defence_unrecorded`` (NF-6) and
``exception_row_values_differ`` (NF-8), so it is at version 2 and the profile that declares it at version 2 too; both
version-1 files ship under ``archive/`` byte for byte, so a version-1 trial corpus stays verifiable. The pattern of
tests/unit/test_d31_bumps.py, with full digests.
"""

from __future__ import annotations

import hashlib
from importlib import resources

from agentprov.adapters.profiles import load_profile
from agentprov.aer.rules import load_catalogue
from agentprov.corpus.package import _catalogue_bytes

#: SHA-256 of main's version-1 bytes (``git show 93c02c6f:<path>``), as the trial corpora record them.
RESCONT_1 = "38dce52e56f20d9ec666005dc6d466bcde568f83b678b0e0c49f60bb89a5231f"
PROFILE_1 = "4f95a256debbae6e153b151d14c6c022d4426c1f2a48dd04be2b2ef3222e7de3"
PROFILE = "memo-ozdincer-agentdojo"
NEW_CODES = {"defence_unrecorded", "exception_row_values_differ"}


def _resource_sha256(*parts: str) -> str:
    return hashlib.sha256(resources.files("agentprov").joinpath("adapters", "agentdojo", *parts).read_bytes()).hexdigest()


def test_rescont_is_at_version_2_and_ships_main_s_version_1():
    current = load_catalogue("rescont")
    assert current.version == 2 and NEW_CODES <= current.issue_codes
    archived = load_catalogue("rescont", 1)
    assert archived.version == 1 and archived.digest == RESCONT_1
    assert _resource_sha256("rules", "archive", "rescont.rules.v1.toml") == RESCONT_1
    assert not NEW_CODES & archived.issue_codes
    # the codes are not rules: every rule keeps its id and version (statements unchanged), only the issue codes grew
    assert archived.rules == current.rules
    assert archived.issue_codes | NEW_CODES == current.issue_codes
    # a version-1 trial corpus packages and verifies against the archived bytes
    assert hashlib.sha256(_catalogue_bytes("rescont", 1)).hexdigest() == RESCONT_1


def test_the_memo_ozdincer_profile_is_at_version_2_and_ships_main_s_version_1():
    current = load_profile(PROFILE)
    assert current.version == 2 and load_profile(PROFILE, 2) == current
    assert current.data["import"]["rules"]["rescont"] == 2
    archived = load_profile(PROFILE, 1)
    assert archived.version == 1 and archived.sha256 == PROFILE_1
    assert _resource_sha256("profiles", "archive", f"{PROFILE}.profile.v1.toml") == PROFILE_1
    assert archived.data["import"]["rules"]["rescont"] == 1
