"""``parse_verified_code`` fails closed on a malformed entry (D.5.4, D-24; CD-2).

A selector that is not a table of glob arrays, or an entry key outside ``{commit, applies, note}``, must raise
``ProfileError``: a string value used to be split into characters (its ``*`` matched every record) and a misspelt
``applies`` was ignored (an empty selector matches every record), so D rules were cited at D for unverified records.
The adprov family has no family schema, so this parser is its only check.
"""

from __future__ import annotations

import tomllib
from importlib import resources

import pytest

from agentprov.adapters.code_verification import VerifiedCode, parse_verified_code
from agentprov.errors import ProfileError

C = "c274885610efaaafec38b6d3eb07152ba7ff3f94"


@pytest.mark.parametrize("entry", [
    {"commit": C, "applies": {"variant": "v1.k14*"}},
    {"commit": C, "applies": {"variant": []}},
    {"commit": C, "applies": {"variant": ["v1", 3]}},
    {"commit": C, "applies": {"variant": [""]}},
    {"commit": C, "applies": {3: ["v1"]}},
    {"commit": C, "apply": {"transcript": ["converted"]}},
    {"commit": C, "note": 5},
])
def test_a_malformed_entry_is_refused(entry):
    with pytest.raises(ProfileError):
        parse_verified_code([entry], "profile 'x'")


def test_a_well_formed_entry_parses_unchanged():
    got = parse_verified_code([{"commit": C, "applies": {"variant": ["v1.k14*"], "transcript": ["converted"]}, "note": "n"},
                               {"commit": C}], "profile 'x'")
    assert got == (VerifiedCode(C, {"variant": ("v1.k14*",), "transcript": ("converted",)}), VerifiedCode(C, {}))
    assert not got[0].matches({"variant": "v0.k11", "transcript": "converted"})


def _profiles():
    root = resources.files("agentprov").joinpath("adapters")
    for family in sorted(root.iterdir(), key=lambda p: p.name):
        profiles = family.joinpath("profiles")
        if not profiles.is_dir():
            continue
        for path in sorted(profiles.iterdir(), key=lambda p: p.name):
            if path.name.endswith(".toml"):
                yield f"{family.name}/{path.name}", tomllib.loads(path.read_text("utf-8"))


def _tables(value):
    if isinstance(value, dict):
        if "verified_code" in value:
            yield value["verified_code"]
        for v in value.values():
            yield from _tables(v)


def test_every_shipped_verified_code_table_still_parses():
    seen = 0
    for name, doc in _profiles():
        for entries in _tables(doc):
            parse_verified_code(entries, name)
            seen += len(entries)
    assert seen
