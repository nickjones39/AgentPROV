"""Phase 10j's R-10j-4 and R-10j-5 (regeneration-batch items 96 and 97), in both AgentDojo-family builds.

- 96: a negative logged ``duration`` (the runner's clock went backwards) is no ``dur_s`` (C.8.3, >= 0): it stays verbatim
  in ``t.raw.dur``, declared ``ambiguous``, and the log is sealed.
- 97: a tool the model called ``none`` keeps its name, declared ``unk ambiguous``, in the DRIFT build as in the TraceLogger
  build (item 87, CD-10).

Synthetic logs and a pinned AgentDyn variant C fixture rewritten in memory."""

from __future__ import annotations

import json
from typing import Any

import pytest
from agentdojo_support import map_log, new_log
from source_support import ok, v1_log
from test_agentdyn import FIXTURES, REPO_URL, _fixture

from agentprov.adapters.runner import aer_bytes, map_artefact_total
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer_bytes
from agentprov.testing import golden

HEAD = "5353cf7615b135cace8d07c8f12dac53a16b6db3"


def _drift(edit: Any, entry: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """An AgentDyn variant C fixture, edited in memory, mapped by the DRIFT build and sealed."""
    entry = entry or _fixture("gpt-5.1-2025-11-13-drift")
    doc: dict[str, Any] = json.loads((FIXTURES / entry["sample_file"]).read_bytes())
    edit(doc)
    raw = json.dumps(doc, indent=4).encode("utf-8")
    origin = Origin.git(REPO_URL, HEAD, entry["original_path"], golden.git_blob_sha1(raw))
    outcome, _unit = map_artefact_total(raw, origin, profile_id="agentdyn", part="c")
    assert not outcome.degenerate
    sealed = load_aer_bytes(aer_bytes(outcome)[0])
    assert "adapter_defect" not in {i["code"] for i in sealed.seal.get("issues", [])}
    return list(sealed.records), doc


def _run(records: list[dict[str, Any]]) -> dict[str, Any]:
    return next(r for r in records if r.get("id") == "run")


# ------------------------------------------------------------------------------------------------ item 96 (R-10j-4)
@pytest.mark.parametrize("duration", [-0.2246, -0.63, -1])
def test_a_negative_duration_is_kept_raw_and_ambiguous(duration):
    m = map_log(new_log(duration=duration))
    ok(m)
    run = m.get("run")
    assert run["t"] == {"raw": {"dur": json.dumps(duration)}} and run["unk"]["/t/dur_s"] == "ambiguous"


def test_a_negative_duration_beside_the_v1_start_keeps_both_raw_values():
    m = map_log(v1_log(duration=-0.63))
    ok(m)
    run = m.get("run")
    assert run["t"]["raw"] == {"dur": "-0.63", "start": "2026-08-17 10:22:40"} and "dur_s" not in run["t"]
    assert run["t"]["start_naive"] == "2026-08-17T10:22:40"


def test_a_positive_duration_is_unchanged():
    run = map_log(new_log(duration=3.0)).get("run")
    assert run["t"] == {"dur_s": 3.0, "dur_clock": "wall"} and "/t/dur_s" not in run["unk"]


def test_a_negative_duration_in_the_drift_build():
    def edit(doc: dict[str, Any]) -> None:
        doc["duration"] = -0.2246

    run = _run(_drift(edit)[0])
    assert run["t"] == {"raw": {"dur": "-0.2246"}} and run["unk"]["/t/dur_s"] == "ambiguous"


# ------------------------------------------------------------------------------------------------ item 97 (R-10j-5)
def _rename(value: Any, old: str) -> Any:
    """Every string equal to ``old`` (the tool's name, wherever the format writes it) becomes ``none``."""
    if isinstance(value, dict):
        return {k: _rename(v, old) for k, v in value.items()}
    if isinstance(value, list):
        return [_rename(v, old) for v in value]
    return "none" if value == old else value


def test_a_tool_called_none_in_the_drift_build_keeps_the_log():
    """On the DRIFT source's own pinned fixtures (test_drift): the first one with a tool execution, its tool renamed."""
    from test_drift import _entries as drift_entries
    from test_drift import _raw, map_drift

    for entry in drift_entries():
        baseline = map_drift(_raw(entry), entry["original_path"])
        name = next((r["name"] for r in baseline.of_kind("tool_execution")), None)
        if name is None:
            continue
        doc = json.loads(_raw(entry))
        doc = _rename(doc, name)
        m = map_drift(json.dumps(doc, indent=4).encode("utf-8"), entry["original_path"])
        assert "adapter_defect" not in m.codes
        named = [r for r in m.of_kind("tool_execution") if r.get("name") == "none"]
        assert named and all(r["unk"]["/name"] == "ambiguous" for r in named)
        return
    pytest.skip("no DRIFT fixture with a tool execution")
