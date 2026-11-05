"""``tools/agentdojo/source_checks.py --source survey`` reports the iteration-capped traces (audit AU-TRS-8).

``survey()`` counted the traces with an ``unexecuted_tool_call`` seal issue and dropped the count, so the cross-check its
docstring lists never ran; it also divided by zero for a model without one of the three task kinds. Synthetic AERs only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "agentdojo"))

import source_checks  # noqa: E402


def _aer(task: str, attack: str | None, capped: bool) -> list[dict[str, object]]:
    return [{"k": "execution", "task": {"task_id": task, "attack_id": attack}, "ext": {}},
            {"k": "actor", "id": "agent", "model": {"requested": "qwen3:14b"}},
            {"k": "judgement", "name": "utility", "value": True}, {"k": "judgement", "name": "security", "value": False},
            {"k": "seal", "issues": [{"code": "unexecuted_tool_call"}] if capped else []}]


def test_survey_reports_the_iteration_capped_traces_and_tolerates_an_empty_task_kind() -> None:
    checks = source_checks.survey([_aer("user_task_0", "important_instructions", True), _aer("user_task_1", None, False)])
    assert checks["iteration_capped"] == {"measured": 1, "investigation": 48, "equal": False, "per_model": {"qwen3:14b": 1}}
    rates = checks["aggregates_per_model"]["measured"]["qwen3:14b"]
    assert rates["solvability_utility"] is None and rates["benign_utility"] == 100.0
