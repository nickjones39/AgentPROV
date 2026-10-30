"""The ``mcphunt.traces`` reader (docs/architecture D.21.1, D.21.2): sniff, streaming parse and the split label."""

from __future__ import annotations

import io
import json

import mcphunt_support as support

from agentprov.adapters.mcphunt.dialect import McpHuntReader, split_of
from agentprov.ingest.limits import IngestLimits


def test_sniff_and_streamed_parse():
    reader = McpHuntReader()
    spec = support.F()["main_benign_success"]
    data = (support.FIXTURES / spec["fixture_file"]).read_bytes()
    result = reader.sniff(data, label="", limits=support.limits())
    assert result.match and result.variant == "v2.0.0"
    items = support.items(spec["fixture_file"])
    assert [i.locator.p for i in items] == [f"/traces/{n}" for n in range(len(items))]
    assert set(items[0].value) == {"envelope", "envelope_spans", "trace"} and "traces" not in items[0].value["envelope"]
    for name, (start, end) in items[0].value["envelope_spans"].items():  # item 149: each span is the member's own value
        assert json.loads(data[start:end]) == items[0].value["envelope"][name]
    assert "labeling_rules_version" in items[0].value["envelope_spans"]
    for other in (b"{}", b"[]", json.dumps({"traces": []}).encode(), b"not json"):
        assert not reader.sniff(other, label="", limits=IngestLimits()).match


def test_element_limit_fails_closed():
    """A trace over the element limit refuses the whole document (D-288): nothing is yielded."""
    spec = support.F()["main_benign_success"]
    data = (support.FIXTURES / spec["fixture_file"]).read_bytes()
    small = IngestLimits().replace(max_json_element_bytes=1024)
    assert not McpHuntReader().sniff_stream(io.BytesIO(data), limits=small).match


def test_split_labels():
    assert split_of("main/gpt_5_2.json") == "main" and split_of("live_guard_defense/x.json") == "live_guard_defense"
    assert split_of("meta/mitigation_results.json") is None and split_of("README.md") is None


def test_an_lfs_pointer_is_registered_not_mapped():
    """A checkout of the pinned tree holds Git LFS pointers for 15 documents: valid input of another kind, registered
    with the detail mcphunt.lfs_pointer (mcphunt.lfs_pointer@1); the R3 pinned object is imported in its place."""
    import pytest

    from agentprov.adapters.runner import NotOfDialect, map_artefact_units
    from agentprov.adapters.types import Origin

    pointer = (b"version https://git-lfs.github.com/spec/v1\n"
               b"oid sha256:" + b"ab" * 32 + b"\nsize 123\n")  # synthetic oid and size
    reader = McpHuntReader()
    for result in (reader.sniff(pointer, label="", limits=IngestLimits()),
                   reader.sniff_stream(io.BytesIO(pointer), limits=IngestLimits())):
        assert not result.match and result.reasons == ("mcphunt.lfs_pointer",)
    assert reader.register_detail(("mcphunt.lfs_pointer",)) == "mcphunt.lfs_pointer"
    assert reader.register_detail(("mcphunt.sniff.envelope_keys",)) is None
    handle = io.BytesIO(b"xx" + pointer)
    handle.seek(2)
    assert reader.sniff_stream(handle, limits=IngestLimits()).reasons == ("mcphunt.lfs_pointer",)
    origin = Origin.from_json({"kind": "hf", "repo": "lihaonan0716/mcphunt-agent-traces", "revision": support.REVISION,
                               "path": "main/x.json"})
    with pytest.raises(NotOfDialect) as refused:
        map_artefact_units(pointer, origin, profile_id=support.PROFILE)
    assert refused.value.detail == "mcphunt.lfs_pointer"
