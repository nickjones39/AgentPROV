"""Review UC-39 in the adprov mapper (2026-11-01; 0.2.0 change batch D-1063, regeneration-batch item 174):
``meta.wall_clock_s`` negative or beyond the I-JSON range reached the typed ``t.dur_s``, so the AER writer refused the
transcript (``adapter_defect``). As D-1011 does for a time outside the AER's ranges, such a transcript is refused as
malformed: ``wall_clock_s`` has no other place in the AER from which the transcript/v1 view could rebuild it byte for
byte. Synthetic documents only."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.parametrize("wall", [-0.25, -1, 2**53, 2**60, 9.1e15])
def test_a_wall_clock_outside_the_aer_range_is_malformed_not_a_mapper_defect(v1: Any, wall: float):
    m = v1.map(v1.dump(v1.released(wall_clock_s=wall)))
    assert m.outcome.degenerate and m.outcome.error_code == "adapter.malformed_artefact", m.outcome.error_code
    assert "adapter_defect" not in m.issue_codes()


@pytest.mark.parametrize("wall", [0, 0.0, 7.0, 2**53 - 1])
def test_a_wall_clock_in_range_is_the_typed_duration(v1: Any, wall: float):
    m = v1.map(v1.dump(v1.released(wall_clock_s=wall)))
    assert not m.outcome.degenerate
    assert m.by_id()["run"]["t"]["dur_s"] == wall
