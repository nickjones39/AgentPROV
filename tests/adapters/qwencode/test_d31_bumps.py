"""D-31 strict integer bumps of the ``qwencode`` family (docs/architecture D.24.7-D.24.9; the twins owner's ruling of
2026-10-21, option A; the pattern of tests/unit/test_d31_bumps.py).

Scratch trial corpora recorded main's bytes at 93c02c6f (before regen items 120-127). Every file those items changed is at
version 2 and its version 1 ships byte for byte: ``rules/archive/qwencode.rules.v1.toml``,
``profiles/archive/redcode-exec-qwencode.profile.v1.toml`` and the directory ``semantics/qwencode.tools-1/`` (unchanged,
still on the catalogue version 1). ``qwencode.tools@2`` carries item 127 and declares the catalogue version 2.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources

import qwencode_support as support
import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue

PACKAGE = "agentprov.adapters.qwencode"
#: The sha256 of the bytes the scratch trials recorded (git show 93c02c6f:<path>).
RECORDED_CATALOGUE = "db5c7cd7533ab0347260cb961344ad05504347a52bc2f87abeb8bb55dafc6cce"
RECORDED_PROFILE = "40e8732e01e71644af7f2fa933e79594bad722b2fd1e66ab53bbdda9c9c12927"
#: The sha256 of profile version 2 as it lands (with D-602's [withhold], the D-578 amendment); a change needs a ruling
CURRENT_PROFILE = "cd8895111ad7b139c5ea23139d19f03e6c92a1e9b4729a9e7ad770c21eb31b05"
#: The profile digest (agentprov.sem.profiles.profile_digest) of semantics/qwencode.tools-1/ at 93c02c6f.
TOOLS_1 = "34eb0b7958840fcc84f810b9077d0112e764ce78ad34f1cff39d69750be971d5"


def _bytes(*parts: str) -> bytes:
    return resources.files("agentprov").joinpath("adapters", "qwencode", *parts).read_bytes()


def test_the_catalogue_is_at_version_2_and_ships_its_recorded_version_1():
    assert load_catalogue("qwencode").version == 2 and load_catalogue("qwencode", 2).version == 2
    archived = load_catalogue("qwencode", 1)
    assert archived.version == 1 and archived.digest == RECORDED_CATALOGUE
    assert hashlib.sha256(_bytes("rules", "archive", "qwencode.rules.v1.toml")).hexdigest() == RECORDED_CATALOGUE


def test_the_profile_is_at_version_2_and_ships_its_recorded_version_1():
    current = load_profile(support.PROFILE)
    assert current.version == 2 and load_profile(support.PROFILE, 2).version == 2
    assert hashlib.sha256(_bytes("profiles", f"{support.PROFILE}.profile.toml")).hexdigest() == CURRENT_PROFILE
    assert current.data["import"]["rules"] == {"aer": 1, "qwencode": 2}
    assert current.family_table()["semantics_profile"] == {"id": "qwencode.tools", "version": 2}
    archived = load_profile(support.PROFILE, 1)
    assert archived.version == 1 and archived.sha256 == RECORDED_PROFILE
    assert archived.data["import"]["rules"] == {"aer": 1, "qwencode": 1}
    path = ("profiles", "archive", f"{support.PROFILE}.profile.v1.toml")
    assert hashlib.sha256(_bytes(*path)).hexdigest() == RECORDED_PROFILE


def test_the_semantics_versions_declare_their_catalogue_versions():
    one, two = load_semantics_profile("qwencode.tools", 1), load_semantics_profile("qwencode.tools", 2)
    assert one.sha256 == TOOLS_1  # unchanged: the scratch trials' bytes
    assert (dict(one.rules), dict(two.rules)) == ({"qwencode": 1}, {"qwencode": 2})
    assert two.tables.outcomes["non_informative"] == [1] and "non_informative" not in one.tables.outcomes


def test_the_registry_selects_version_2():
    from agentprov.adapters.registry import get_source

    (part,) = get_source(support.PROFILE).capabilities
    assert part.semantics == ("qwencode.tools@2",)


@pytest.mark.parametrize(("value", "one", "two"), [
    (2, {"claim": "qwencode.non_informative", "holds": True}, None),  # version 1's catch-all, item 127 at version 2
    (1, {"claim": "qwencode.non_informative", "holds": True}, {"claim": "qwencode.non_informative", "holds": True}),
    (3, {"claim": "attack_succeeded", "holds": True}, {"claim": "attack_succeeded", "holds": True}),
])
def test_version_1_reads_scores_as_at_93c02c6f_and_version_2_per_item_127(value, one, two):
    from agentprov.adapters.qwencode.dialect import parse_label
    from agentprov.sem.engine import annotate

    f = parse_label(support.by_criterion("python"))
    assert f is not None
    member = f"results/Qwen/{f.model}/{f.target}/{f.language}/conversation_log/index{f.scenario}.json"
    entries = [dict(e, score=value) if e["index"] == f.case_key else e for e in json.loads(support.tree()[1][member])]
    m = support.modified("python", supp={member: json.dumps(entries).encode()})
    for version, expected in ((1, one), (2, two)):
        sem = annotate(m.doc, load_semantics_profile("qwencode.tools", version))
        assert [a["value"] for a in sem.annotations if a["type"] == "outcome"] == ([] if expected is None else [expected])


def test_version_1_builds_without_the_item_127_key():
    from agentprov.adapters.qwencode.semantics.tools import ProfileDataError, parse_tables

    files = {n: _bytes("semantics", "qwencode.tools-1", n) for n in ("profile.toml", "tools.toml")}
    assert b"non_informative = [" not in files["profile.toml"]
    assert "non_informative" not in parse_tables(files, 1).outcomes
    with pytest.raises(ProfileDataError):
        parse_tables(files, 2)  # the version 2 header and outcomes table are required at version 2
