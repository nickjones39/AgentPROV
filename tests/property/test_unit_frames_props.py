"""D-414: the importer's two passes over a map result split it exactly as ``split_unit_frames`` did.

For any sequence of frames (register rows, unit headers, records, seals, ``abort``, ``not_dialect``, ``select``, in any
order), :func:`summarise_unit_frames` gives the same register rows and unit headers and flags a framing error exactly
when ``split_unit_frames`` raises; :func:`iter_unit_frames` then yields the same ``(header, frames)`` pairs, and the
first ``abort``, ``not_dialect`` and ``select`` frames are the ones the old ``next(...)`` scans found.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.adapters.runner import iter_unit_frames, split_unit_frames, summarise_unit_frames
from agentprov.errors import AgentProvError

S = settings(max_examples=500, deadline=None, derandomize=True)

FRAMES = st.one_of(
    st.builds(lambda n: {"register": {"code": "select.out_of_scope", "detail": "", "loc": {"p": f"/{n}"}}}, st.integers(0, 9)),
    st.builds(lambda n: {"unit": {"sha256": "a" * 64, "loc": {"p": f"/{n}"}}}, st.integers(0, 9)),
    st.builds(lambda n: {"record": {"id": f"r{n}"}}, st.integers(0, 9)),
    st.just({"seal": {"ex": "ex_x", "issues": [], "severities": [], "checks": [], "degenerate": False}}),
    st.builds(lambda n: {"abort": {"issue": "adapter_defect", "code": f"c{n}"}}, st.integers(0, 3)),
    st.builds(lambda n: {"not_dialect": f"reason {n}", "detail": "d"}, st.integers(0, 3)),
    st.builds(lambda n: {"select": {"code": "select.variant", "detail": f"{n}"}}, st.integers(0, 3)),
)


def old_split(frames: list[dict[str, Any]]) -> tuple[Any, ...] | None:
    try:
        rows, units = split_unit_frames(frames)
    except AgentProvError as exc:
        assert exc.code == "adapter.job_incomplete"
        return None
    return rows, [(head, list(unit)) for head, unit in units]


@S
@given(st.lists(FRAMES, max_size=14))
def test_the_two_passes_split_like_split_unit_frames(frames: list[dict[str, Any]]) -> None:
    summary = summarise_unit_frames(iter(frames))
    old = old_split(frames)
    assert summary.framing_error is (old is None)
    if old is not None:
        rows, units = old
        assert summary.rows == rows
        assert summary.heads == [head for head, _ in units]
        assert list(iter_unit_frames(iter(frames))) == units
    assert summary.abort == next((dict(f["abort"]) for f in frames if "abort" in f), None)
    assert summary.not_dialect == next((f for f in frames if "not_dialect" in f), None)
    assert summary.select == next((f["select"] for f in frames if "select" in f), None)
