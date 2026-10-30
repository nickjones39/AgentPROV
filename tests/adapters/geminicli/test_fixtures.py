"""The committed gemini-cli fixtures (docs/architecture D.23.11; D-336): byte-identical members, rollout directories
chosen by criterion, within the per-source budget, none holding a credential-shaped value or a home path. Prints nothing of
their content."""

from __future__ import annotations

import hashlib
import re
import zlib

import geminicli_support as support

from agentprov.adapters.geminicli.dialect import parse_label

BUDGET = 512 * 1024
KEY_SHAPE = re.compile(rb"AIza[0-9A-Za-z_\-]{35}")
HOME = re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]+")


def test_every_fixture_is_the_pinned_member_byte_for_byte():
    total = 0
    for e in support.source_entries():
        data = support.file_bytes(e["label"])
        loc = e["record_locator"]
        assert hashlib.sha256(data).hexdigest() == e["sha256"] and len(data) == e["size_bytes"] == loc["size"], e["label"]
        assert f"{zlib.crc32(data):08x}" == loc["crc32"] and loc["container_sha256"] == support.TAR_SHA256
        assert e["licence"] == "CC-BY-4.0" and e["synthetic"] is False
        facets = parse_label(e["label"])
        assert facets is not None and facets.scaffold == "gemini_cli", e["label"]
        total += len(data)
    assert total <= BUDGET


def test_fixtures_cover_every_criterion_and_cell():
    crits = {c for cs in support.directories().values() for c in cs}
    assert {"ok_with_text_and_calls", "error_result", "cli_notice", "aborted_unanswered_call", "aborted_after_result",
            "parallel_calls", "tool_error_status", "success_without_output", "subagent_counter_differs", "web_search",
            "elicited", "empty_stream", "no_stream_with_harness_events"} <= crits
    assert {c for c in crits if c.startswith("cell:")} == {
        "cell:MiniMax-M2", "cell:claude-sonnet-4-6", "cell:gemini-2.5-pro", "cell:glm-4.7-probe", "cell:gpt-5.3-codex"}


def test_no_fixture_holds_a_credential_shape_or_a_home_path():
    for e in support.source_entries():
        data = support.file_bytes(e["label"])
        assert not KEY_SHAPE.search(data) and not HOME.search(data), e["label"]
