"""logical_name / collision_key (G.3.6)."""

from __future__ import annotations

import unicodedata

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.names import collision_key, logical_name

LIMITS = IngestLimits()


def code_of(name: str, **kw) -> str:
    with pytest.raises(IngestError) as info:
        logical_name(name, LIMITS, **kw)
    return info.value.code


@pytest.mark.parametrize("name", ["a.json", "dir/sub/file.eval", "runs/gpt-4o-2024-05-13/user_task_1.json", "x" * 255])
def test_accepts_ordinary_labels(name):
    assert logical_name(name, LIMITS) == name


def test_returns_nfc():
    decomposed = "e" + chr(0x301)
    assert logical_name(decomposed + ".txt") == unicodedata.normalize("NFC", decomposed + ".txt")


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_total_length_cap_is_in_bytes(delta):
    comp = 200
    parts = []
    total = 0
    limit = LIMITS.max_name_bytes
    while total + comp + 1 <= limit - comp:
        parts.append("a" * comp)
        total += comp + 1
    last = "b" * (limit - total + delta)
    name = "/".join([*parts, last])
    assert len(name.encode()) == limit + delta
    if delta > 0:
        assert code_of(name) == "ingest.name.invalid"
    else:
        assert logical_name(name) == name


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_component_length_cap(delta):
    name = "c" * (LIMITS.max_component_bytes + delta)
    if delta > 0:
        assert code_of(name) == "ingest.name.invalid"
    else:
        assert logical_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", "a//b", "a/./b", "./a", "a/", "a" + chr(0) + "b", "a" + chr(0x1B) + "b", "a" + chr(0x85) + "b", "a" + chr(0xD800)],
)
def test_invalid_names(name):
    assert code_of(name) == "ingest.name.invalid"


@pytest.mark.parametrize("name", ["../x", "a/../b", "a/..", "/etc/passwd", "C:\\x", "c:x", "a\\b", "x/a:b"])
def test_traversal_forms(name):
    assert code_of(name) == "ingest.archive.traversal"


@pytest.mark.parametrize(
    "name",
    ["a<b", "a>b", 'a"b', "a|b", "a?b", "a*b", "name.", "name ", "CON", "con.txt", "dir/NUL", "COM1", "LPT9.log",
     "COM" + chr(0xB9), "LPT" + chr(0xB2), "AUX.tar.gz"],
)
def test_windows_hostile_names(name):
    assert code_of(name) == "ingest.name.invalid"


def test_non_portable_mode_keeps_posix_names_but_nothing_else():
    assert logical_name("a:b", LIMITS, portable=False) == "a:b"
    assert logical_name("CON", LIMITS, portable=False) == "CON"
    assert code_of("../x", portable=False) == "ingest.archive.traversal"
    assert code_of("a" + chr(0) + "b", portable=False) == "ingest.name.invalid"


def test_collision_key_folds_case_and_normalisation():
    assert collision_key("Caf" + chr(0xE9) + ".JSON") == collision_key("cafe" + chr(0x301) + ".json")
    assert collision_key("Stra" + chr(0xDF) + "e") == collision_key("STRASSE")
    assert collision_key("a") != collision_key("b")


def test_error_messages_do_not_echo_the_name():
    marker = "SECRET-NAME-" + "z" * 8
    for name in (marker + chr(0), "../" + marker, marker + "?"):
        with pytest.raises(IngestError) as info:
            logical_name(name)
        assert marker not in str(info.value)


def test_collision_key_is_the_canonical_caseless_match():
    """Pre-round review D #9: ``NFC(casefold(name))`` missed APFS collisions such as ALPHA WITH PROSGEGRAMMENI plus a
    diaeresis against alpha, diaeresis, iota (one file on APFS, two keys before)."""
    from agentprov.ingest.names import collision_key

    a = "\N{GREEK CAPITAL LETTER ALPHA WITH PROSGEGRAMMENI}\N{COMBINING DIAERESIS}.json"
    b = "\N{GREEK SMALL LETTER ALPHA}\N{COMBINING DIAERESIS}\N{GREEK SMALL LETTER IOTA}.json"
    assert collision_key(a) == collision_key(b)
    assert collision_key("A.json") == collision_key("a.json")
    assert collision_key("e\N{COMBINING ACUTE ACCENT}.json") == collision_key("\N{LATIN SMALL LETTER E WITH ACUTE}.json")
    assert collision_key("a.json") != collision_key("b.json")


def test_a_zip_with_an_apfs_colliding_pair_rejects_both():
    import io
    import zipfile

    from agentprov.ingest.archives import iter_zip_members, open_zip

    a = "\N{GREEK CAPITAL LETTER ALPHA WITH PROSGEGRAMMENI}\N{COMBINING DIAERESIS}.json"
    b = "\N{GREEK SMALL LETTER ALPHA}\N{COMBINING DIAERESIS}\N{GREEK SMALL LETTER IOTA}.json"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(a, b"{}")
        z.writestr(b, b"{}")
        z.writestr("ok.json", b"{}")
    with open_zip(io.BytesIO(buf.getvalue()), release=False) as opened:
        members = {m.label: (m.disposition, m.code) for m in iter_zip_members(opened)}
    assert members["ok.json"][0] == "selected"
    others = [v for k, v in members.items() if k != "ok.json"]
    assert len(others) == 2 and all(d != "selected" for d, _ in others), members
