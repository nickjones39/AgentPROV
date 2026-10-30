"""SEC-09 (K.12.1): hostile member and file names. Names are labels, never paths."""

from __future__ import annotations

import unicodedata

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.names import collision_key, logical_name
from agentprov.ingest.quote import escape_untrusted

LIMITS = IngestLimits()


def code_of(name: str) -> str:
    with pytest.raises(IngestError) as info:
        logical_name(name, LIMITS)
    return info.value.code


CONTROLS = [chr(c) for c in (*range(0x00, 0x20), 0x7F, 0x80, 0x85, 0x9B, 0x9F)]


@pytest.mark.parametrize("ch", CONTROLS)
def test_sec09_every_c0_and_c1_control_is_rejected(ch):
    assert code_of("a" + ch + "b") == "ingest.name.invalid"
    assert code_of(ch + "a") == "ingest.name.invalid"


def test_sec09_ansi_sequences_are_rejected():
    assert code_of("run" + chr(0x1B) + "[31mred" + chr(0x1B) + "[0m.json") == "ingest.name.invalid"
    assert code_of("t" + chr(0x1B) + "]0;title" + chr(7) + ".json") == "ingest.name.invalid"


def test_sec09_bidi_and_tag_characters_are_labels_that_are_always_displayed_escaped():
    for cp in (0x202E, 0x2066, 0x200B, 0xE0041, 0xFEFF):
        name = "evil" + chr(cp) + "gnp.json"
        assert logical_name(name, LIMITS) == unicodedata.normalize("NFC", name)
        shown = escape_untrusted(name)
        assert chr(cp) not in shown and f"<U+{cp:04X}>" in shown


@pytest.mark.parametrize("lone", [0xD800, 0xDBFF, 0xDC00, 0xDFFF])
def test_sec09_lone_surrogates_are_rejected(lone):
    assert code_of("a" + chr(lone)) == "ingest.name.invalid"


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_sec09_length_is_checked_in_bytes_before_nfc(delta):
    # U+0344 (4 bytes... 2 bytes in UTF-8) NFC-expands to U+0308 U+0301 (4 bytes), so a name just under the limit before
    # normalisation can exceed it afterwards, and a name over the limit must never be normalised first.
    limit = LIMITS.max_name_bytes
    expander = chr(0x344)
    assert len(expander.encode()) == 2 and len(unicodedata.normalize("NFC", expander).encode()) == 4
    name = "/".join([expander * 60] * 8)  # 8 components of 240 bytes after NFC: only the whole-name check can fire
    assert len(name.encode()) <= limit < len(unicodedata.normalize("NFC", name).encode())
    assert max(len(unicodedata.normalize("NFC", c).encode()) for c in name.split("/")) <= LIMITS.max_component_bytes
    assert code_of(name) == "ingest.name.invalid"  # fits in bytes before NFC, exceeds after: rejected
    over = "a" * (limit + 1)
    assert code_of(over) == "ingest.name.invalid"
    exact = ("a" * 200 + "/") * 4 + "b" * (limit - 804 + delta)
    if delta > 0:
        assert code_of(exact) == "ingest.name.invalid"
    else:
        assert logical_name(exact, LIMITS) == exact


def test_sec09_length_check_counts_bytes_not_characters():
    name = chr(0x20AC) * (LIMITS.max_component_bytes // 3 + 1)  # 3 bytes each: over the component cap in bytes
    assert len(name) < LIMITS.max_component_bytes
    assert code_of(name) == "ingest.name.invalid"


@pytest.mark.parametrize("name", ["CON", "prn", "Aux.txt", "NUL.tar.gz", "com1", "COM9.log", "LPT0", "lpt9.x",
                                  "COM" + chr(0xB9), "COM" + chr(0xB2) + ".txt", "LPT" + chr(0xB3), "d/CON"])
def test_sec09_reserved_device_names(name):
    assert code_of(name) == "ingest.name.invalid"


@pytest.mark.parametrize("name", ["trailing.dot.", "trailing.space ", "d/ends.", "a<b", "a>b", 'a"b', "a|b", "a?b", "a*b"])
def test_sec09_windows_hostile_names(name):
    assert code_of(name) == "ingest.name.invalid"


@pytest.mark.parametrize("name", ["qwen3.6:27b/run.json", "v1.k14/qwen3.6:27b/0001.json", "a/b/tag:latest", "run::1.json",
                                  "x/12:30.json", "ns:name:tag/log.json"])
def test_sec09_a_colon_inside_a_component_is_a_label_character(name):
    """D-91: Figshare 32657856 names directories after Ollama model tags; a label is never a path, so ':' is kept."""
    assert logical_name(name, LIMITS) == name


@pytest.mark.parametrize("name", ["C:x", "c:/x", "d/x:y", "a/C:", "runs/z:tag/x.json", "a:b"])
def test_sec09_a_drive_form_stays_a_traversal_form_in_every_component(name):
    assert code_of(name) == "ingest.archive.traversal"


def test_sec09_confusable_prefixes_of_reserved_names_are_fine():
    for ok in ("CONSOLE", "COM10", "NULL", "auxiliary.txt", "LPT"):
        assert logical_name(ok, LIMITS) == ok


def test_sec09_nfc_nfd_and_case_collisions_share_a_key():
    nfc, nfd = "caf" + chr(0xE9), "cafe" + chr(0x301)
    assert nfc != nfd
    keys = {collision_key(n) for n in (nfc, nfd, nfc.upper(), nfd.upper(), "CAF" + chr(0xC9))}
    assert len(keys) == 1
    assert collision_key("Stra" + chr(0xDF) + "e") == collision_key("STRASSE")
    # logical_name returns NFC, so NFD input never produces a distinct stored label
    assert logical_name(nfd, LIMITS) == nfc


def test_sec09_names_are_labels_so_traversal_forms_are_typed_not_resolved():
    for name in ("../a", "a/../../b", "/abs", "C:\\x", "d:", "a\\b"):
        assert code_of(name) == "ingest.archive.traversal"


def test_sec09_ten_kilobyte_and_hostile_strings_are_bounded_errors():
    assert code_of("x" * 10_000) == "ingest.name.invalid"
    assert code_of("../" * 3000) == "ingest.name.invalid"  # over the length cap before traversal analysis
