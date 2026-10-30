"""IngestLimits defaults, validation and recording (G.3.2)."""

from __future__ import annotations

import dataclasses

import pytest

from agentprov.ingest.limits import GIB, KIB, MIB, IngestLimits

# The one place that pins the G.3.2 table verbatim; every other test reads values from IngestLimits().
G32_DEFAULTS = {
    "max_artefact_bytes": 2 * GIB,
    "max_json_bytes": 64 * MIB,
    "max_jsonl_line_bytes": 16 * MIB,
    "max_json_depth": 256,
    "max_int_digits": 1000,
    "max_stream_bytes": GIB,
    "max_tar_stream_bytes": 16 * GIB,
    "max_zstd_frames": 1_024,
    "max_pax_header_bytes": 64 * KIB,
    "max_ratio": 200,
    "ratio_floor_bytes": MIB,
    "max_member_bytes": 256 * MIB,
    "max_total_bytes": 4 * GIB,
    "max_members": 100_000,
    "max_cd_bytes": 32 * MIB,
    "max_archive_depth": 2,
    "max_name_bytes": 1024,
    "max_component_bytes": 255,
    "xz_memlimit": 256 * MIB,
    "zstd_window_log_max": 27,
    "max_json_stream_bytes": GIB,
    "max_json_element_bytes": 16 * MIB,
    "max_json_elements": 1_000_000,
    "max_split_parts": 32,
    "max_split_bytes": 8 * GIB,
    "max_yaml_bytes": MIB,
    "max_csv_field_bytes": MIB,
    "max_literal_bytes": MIB,
    "display_chars": 500,
}


def test_defaults_match_the_g32_table():
    limits = IngestLimits()
    for name, expected in G32_DEFAULTS.items():
        assert getattr(limits, name) == expected, name
    assert limits.zip_methods == {0, 8, 93}


def test_every_field_is_covered_by_the_table():
    names = {f.name for f in dataclasses.fields(IngestLimits)}
    assert names == set(G32_DEFAULTS) | {"zip_methods"}


def test_frozen_and_hashable_defaults():
    limits = IngestLimits()
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.max_members = 1  # type: ignore[misc]


def test_replace_validates_and_records_overrides():
    limits = IngestLimits()
    assert limits.overrides() == {}
    smaller = limits.replace(max_members=10, zip_methods={0})
    assert smaller.overrides() == {"max_members": 10, "zip_methods": [0]}
    assert smaller.max_members == 10
    assert IngestLimits().max_members == limits.max_members  # the original is untouched


def test_to_json_is_complete_and_serialisable():
    import json

    record = IngestLimits().to_json()
    assert set(record) == {f.name for f in dataclasses.fields(IngestLimits)}
    assert record["zip_methods"] == [0, 8, 93]
    json.dumps(record)


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "7"])
def test_rejects_non_positive_or_non_integer_limits(bad):
    with pytest.raises(ValueError):
        IngestLimits(max_members=bad)


@pytest.mark.parametrize("bad", [0, -2, True, "x"])
def test_rejects_bad_ratio(bad):
    with pytest.raises(ValueError):
        IngestLimits(max_ratio=bad)


@pytest.mark.parametrize("bad", [set(), {True}, {"8"}])
def test_rejects_bad_zip_methods(bad):
    with pytest.raises(ValueError):
        IngestLimits(zip_methods=bad)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_a_non_finite_nested_ratio_is_refused(value: float) -> None:
    """Pre-round review D #1: ``max_ratio = nan`` (TOML allows it) passed both bound checks and turned the nested ratio
    gate off (``max(nan, 200)`` is nan, and ``size / compressed > nan`` is never true); inf did the same."""
    from agentprov.ingest.limits import nested_raises

    with pytest.raises(ValueError, match="finite"):
        nested_raises({"max_ratio": value})


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_a_non_finite_global_ratio_is_refused(value: float) -> None:
    from agentprov.ingest.limits import IngestLimits

    with pytest.raises(ValueError, match="finite"):
        IngestLimits(max_ratio=value)
