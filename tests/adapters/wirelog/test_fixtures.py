"""The committed Zenodo 21944598 fixtures (docs/architecture D.20.12): byte-identical members chosen by criterion, no
secret-like strings; the deposit's LICENSE-DATA is committed beside them. Prints nothing of their content."""

from __future__ import annotations

import hashlib
import re
import zlib

import wirelog_support as support


def test_every_fixture_is_the_pinned_member_byte_for_byte():
    entries = support.source_entries()
    labels = {e["label"] for e in entries}
    for crit in support.F:
        assert support.label_of(crit) in labels and support.label_of(crit, "request.json") in labels, crit
    assert {"results.csv", "attacks.json"} <= labels
    for e in entries:
        data = (support.FIXTURES / e["sample_file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e["sha256"] and len(data) == e["size"], e["sample_file"]
        assert f"{zlib.crc32(data):08x}" == e["crc32"] and e["container_sha256"] == support.ZIP_SHA256


def test_no_fixture_carries_a_secret_like_string_and_the_licence_is_present():
    pattern = re.compile(rb"\b(AKIA|ASIA)[0-9A-Z]{16}\b|arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:|\bsk-[A-Za-z0-9_-]{20,}"
                         rb"|(?i:bearer\s+[A-Za-z0-9._-]{20,})|/(?:Users|home)/[A-Za-z0-9_-]{2,}/")
    for e in support.source_entries():
        assert not pattern.search((support.FIXTURES / e["sample_file"]).read_bytes()), e["sample_file"]
    licence = (support.REPO / "tests" / "fixtures" / "LICENSES" / "WhatSurrounds-LICENSE-DATA.txt").read_text(encoding="utf-8")
    assert "Creative Commons Attribution 4.0" in licence
