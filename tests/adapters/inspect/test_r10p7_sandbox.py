"""R-10p-7 (routed from phase 10p): a sandbox event without an ``output`` string (``write_file``, or an ``exec`` whose
output is null) maps to its activity only. An ``inspect:sandbox_output`` artefact asserting only D fields under
``by = source`` is refused by the writer (AER-V12 ``by_without_bare_O``) and degenerated every control-arena sample.
Synthetic samples only."""

from __future__ import annotations

from typing import Any

import inspect_support as s
import pytest

from agentprov.aer.reader import load_aer_bytes


def _map(tmp_path, action: str, **fields: Any) -> list[dict[str, Any]]:
    def tune(smp: s.Sample, sample: dict[str, Any]) -> None:
        # placed right after the tool event, inside its span and its time (event order and times stay consistent)
        k, tool = next((k, e) for k, e in enumerate(smp.events) if e["event"] == "tool")
        smp.events.insert(k + 1, {"uuid": "E-sandbox", "span_id": tool["span_id"], "timestamp": tool["completed"],
                                  "working_start": smp.clock, "event": "sandbox", "action": action,
                                  "completed": tool["completed"], **fields})
        sample["events"] = smp.events

    data = s.build_eval(s.synthetic_header(), {"s1_epoch_1.json": s.basic_sample(tune=tune)})
    (u,) = s.import_log(data, tmp_path).units
    assert not u.outcome.degenerate, u.outcome.error_code
    doc = load_aer_bytes(u.data)
    assert "adapter_defect" not in {i["code"] for i in doc.seal.get("issues", [])}
    return list(doc.records)


@pytest.mark.parametrize(("action", "fields"), [
    ("write_file", {"file": "/workspace/synthetic.txt", "input": "synthetic", "result": None, "output": None}),
    ("write_file", {"file": "/workspace/synthetic.txt", "input": "synthetic"}),
    ("exec", {"cmd": "true", "result": 0, "output": None}),
], ids=["write-null", "write-absent", "exec-null"])
def test_a_sandbox_event_without_output_maps_to_its_activity_only(tmp_path, action, fields):
    records = _map(tmp_path, action, **fields)
    (ac,) = [r for r in records if r["k"] == "activity" and r["type"] == f"inspect:sandbox_{action}"]
    assert not [r for r in records if r["k"] == "artefact" and r.get("generated_by") == ac["id"]]
    assert not [r for r in records if r["k"] == "artefact" and r.get("type") == "inspect:sandbox_output"]


@pytest.mark.parametrize("output", ["synthetic\n", ""], ids=["text", "empty"])
def test_a_recorded_output_string_is_still_an_artefact(tmp_path, output):
    records = _map(tmp_path, "exec", cmd="echo synthetic", result=0, output=output)
    (ac,) = [r for r in records if r["k"] == "activity" and r["type"] == "inspect:sandbox_exec"]
    (af,) = [r for r in records if r["k"] == "artefact" and r.get("generated_by") == ac["id"]]
    assert af["type"] == "inspect:sandbox_output" and af["content"] == output and af["by"] == "source"
