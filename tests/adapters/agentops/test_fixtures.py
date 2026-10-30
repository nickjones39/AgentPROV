"""The committed AgentOps-Bench fixtures (docs/architecture D.18.12; D-199): byte-identical members, chosen by criterion,
none carrying the operator account path; the licence text is committed beside them. Prints nothing of their content."""

from __future__ import annotations

import hashlib
import re
import zlib

import agentops_support as support


def test_every_fixture_is_the_pinned_member_byte_for_byte():
    entries = support.source_entries()
    assert len([e for e in entries if e["sample_file"].startswith("runs/")]) == len(support.F)
    assert {e["label"] for e in entries if e["sample_file"].startswith("runs/")} == set(support.F.values())
    for e in entries:
        data = (support.FIXTURES / e["sample_file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == e["sha256"] and len(data) == e["size"], e["sample_file"]
        assert f"{zlib.crc32(data):08x}" == e["crc32"], e["sample_file"]
        assert e["container_sha256"] in (support.TAR_SHA256, support.ZIP_SHA256)


def test_no_fixture_carries_a_workstation_path_and_the_licence_is_present():
    for e in support.source_entries():
        data = (support.FIXTURES / e["sample_file"]).read_bytes()
        assert not re.search(rb"/(?:Users|home)/[A-Za-z0-9._-]+", data), e["sample_file"]
    licence = (support.REPO / "tests" / "fixtures" / "LICENSES" / "AgentOps-Bench-Apache-2.0.txt").read_text(encoding="utf-8")
    assert "Apache License" in licence and "Version 2.0" in licence
