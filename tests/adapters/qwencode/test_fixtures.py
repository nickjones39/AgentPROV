"""The committed qwencode fixtures (docs/architecture D.24.10; D-578): byte-identical members of the two pinned zips,
chosen by criterion, within the recorded D-360 exception, none holding a credential shape or a non-generic home path.
Prints nothing of their content."""

from __future__ import annotations

import hashlib
import json
import re
import zlib

import qwencode_support as support

KEY_SHAPES = re.compile(rb"AIza[0-9A-Za-z_\-]{35}|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}")
HOME = re.compile(rb"/(?:Users|home)/(?!user/)[A-Za-z0-9._-]+/")


def test_every_fixture_is_the_pinned_member_byte_for_byte():
    total = 0
    for e in support.source_entries():
        data = support.file_bytes(e)
        loc = e["record_locator"]
        assert hashlib.sha256(data).hexdigest() == e["sha256"] and len(data) == e["size_bytes"] == loc["size"], e["label"]
        assert f"{zlib.crc32(data):08x}" == loc["crc32"] and e["licence"] == "CC-BY-4.0" and e["synthetic"] is False
        assert loc["container_sha256"] == (support.RUNS_SHA256 if e["pin_role"] == "runs" else support.SUPP_SHA256)
        total += len(data)
    caps = json.loads((support.REPO / "tests" / "FIXTURES.json").read_text(encoding="utf-8"))
    (exception,) = [x for x in caps["source_exceptions"] if x["source"] == "qwencode"]
    assert total <= exception["budget_bytes"]


def test_fixtures_cover_every_criterion():
    crits = {c for e in support.run_entries() for c in support.criteria(e)}
    assert {"s1_dataset_request", "s2_s3_prompt_request", "python", "bash_suffix", "executed_score_3", "refused_score_0",
            "score_1_ambiguous", "tool_error", "multi_block_message", "usage_above_logged", "soft_cap_exceeded",
            "subagent", "user_text", "truncated_capture", "empty_output"} <= crits


def test_no_fixture_holds_a_credential_shape_or_a_home_path():
    for e in support.source_entries():
        data = support.file_bytes(e)
        assert not KEY_SHAPES.search(data) and not HOME.search(data), e["label"]
