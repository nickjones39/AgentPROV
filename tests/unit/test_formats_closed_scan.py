"""CA-23: every ``agentprov-*/<major>.<minor>`` format id the code writes is in the closed set (HL L.1.1, L.1.2).

``formats.FORMATS`` is the one closed set; a writer that names an id outside it would make a reader that follows the
module contract refuse the corpus's own documents (the stored split descriptor among them, HL H.2.3).
"""

from __future__ import annotations

import re
from pathlib import Path

import agentprov
from agentprov import api, formats
from agentprov.cli.inspect import FORMAT as INSPECT_FORMAT
from agentprov.migration.reconcile import REPORT_FORMAT
from agentprov.raw.members import SPLIT_FORMAT
from agentprov.testing.fixture_caps import FORMAT as FIXTURE_CAPS_FORMAT

SRC = Path(agentprov.__file__).resolve().parent
#: A quoted ``<name>/<major>.<minor>`` id (L.1.2). Integer-versioned ids (detectors, compat, package data) do not match.
FORMAT_ID = re.compile(r"[\"'](agentprov-[a-z0-9-]+/[0-9]+\.[0-9]+)[\"']")
#: Spec versions and reserved ids, deliberately not formats (formats.py docstring).
NOT_FORMATS = {"agentprov-prov/0.1"} | set(formats.RESERVED_FORMATS)


def test_the_stored_split_descriptor_format_is_closed():
    assert formats.require_supported(SPLIT_FORMAT) == SPLIT_FORMAT
    assert SPLIT_FORMAT in api.FORMATS


def test_the_named_as_built_constants_are_closed():
    for format_id in (REPORT_FORMAT, INSPECT_FORMAT, FIXTURE_CAPS_FORMAT, "agentprov-sem-profile/0.1",
                      "agentprov-artefact-table/0.1"):
        assert formats.is_supported(format_id), format_id


def test_every_format_id_in_src_is_in_the_closed_set():
    found: set[str] = set()
    for path in sorted(SRC.rglob("*")):
        if path.suffix in {".py", ".toml", ".json"} and path.is_file() and "__pycache__" not in path.parts:
            found |= set(FORMAT_ID.findall(path.read_text(encoding="utf-8", errors="replace")))
    assert found, "the scan found no format ids at all"
    missing = sorted(found - formats.FORMATS - NOT_FORMATS)
    assert not missing, missing
