"""The D-31 bump of the geminicli family with D-1063 (regen-batch row 176; review UC-40/UC-41).

Catalogue ``geminicli`` is at version 2, the source profile at version 3 and ``geminicli.tools`` at version 2. Catalogue
version 1 and profile version 2, which the sealed corpus code-agent-misalignment-w2 records (derivation.json), ship under
``archive/`` byte for byte, so the corpus stays recomputable; ``geminicli.tools@1`` keeps reading catalogue version 1
and ``@2`` (version 1's tables) reads version 2 (H.2.5: one catalogue version per corpus).
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources

import geminicli_support as support

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue
from agentprov.sem.engine import dumps_sem

PACKAGE = "agentprov.adapters.geminicli"
#: The sha256 of the bytes the sealed corpus code-agent-misalignment-w2 records (rules_sha256, profile_sha256).
SEALED_CATALOGUE = "96dda696e9b81712f8dca2bd93aea25db4a3dec58a3ab685e226d40edc9d70db"
SEALED_PROFILE = "7e807cff6ea36b5773101bab6e97c5bd8a6fe264b7fce0d0cd00605b1a349aa0"


def _bytes(*parts: str) -> bytes:
    return resources.files(PACKAGE).joinpath(*parts).read_bytes()


def test_catalogue_version_1_is_archived_as_sealed_and_version_2_only_adds_the_d1063_rules():
    assert hashlib.sha256(_bytes("rules", "archive", "geminicli.rules.v1.toml")).hexdigest() == SEALED_CATALOGUE
    v1, v2 = load_catalogue("geminicli", 1, package=PACKAGE), load_catalogue("geminicli", package=PACKAGE)
    assert v1.digest == SEALED_CATALOGUE and (v1.version, v2.version) == (1, 2)
    assert set(v2.rules) - set(v1.rules) == {"geminicli.lone_surrogate_replaced@1", "geminicli.content_not_inlined@1"}
    assert all(v2.rules[rid] == rule for rid, rule in v1.rules.items())
    assert v2.issue_codes - v1.issue_codes == {"lone_surrogate_replaced", "content_not_inlined"}


def test_profile_version_2_is_archived_as_sealed():
    path = ("profiles", "archive", f"{support.PROFILE}.profile.v2.toml")
    assert hashlib.sha256(_bytes(*path)).hexdigest() == SEALED_PROFILE
    sealed, current = load_profile(support.PROFILE, 2), load_profile(support.PROFILE)
    assert sealed.sha256 == SEALED_PROFILE and current.version == 3
    assert sealed.data["import"]["rules"] == {"aer": 1, "geminicli": 1}
    assert current.data["import"]["rules"] == {"aer": 1, "geminicli": 2}
    assert current.family_table()["semantics_profile"] == {"id": "geminicli.tools", "version": 2}


def test_each_semantics_version_reads_its_own_catalogue_version():
    one, two = load_semantics_profile("geminicli.tools", 1), load_semantics_profile("geminicli.tools", 2)
    assert (dict(one.rules), dict(two.rules)) == ({"geminicli": 1}, {"geminicli": 2})
    assert one.tables == two.tables and dict(one.classes) == dict(two.classes)
    assert _bytes("semantics", "geminicli.tools-1", "tools.toml") == _bytes("semantics", "geminicli.tools-2", "tools.toml")


def test_a_new_aer_and_its_sem_agree_on_version_2():
    mapped = support.map_dir(support.by_criterion("ok_with_text_and_calls"), sem=True)
    assert mapped.header["rules"]["geminicli"] == 2
    assert json.loads(dumps_sem(mapped.sem).split(b"\n", 1)[0])["rules"] == {"geminicli": 2}
