"""GUI review GR-30: the job queue's budgets never reach a queued job as a value the queue misreads. A memory budget
of ``nan``, ``inf`` or ``1e999`` turned off the queue's memory admission (D-432), a negative one made every GUI job
wait to run alone, and a non-ASCII digit passed ``str.isdigit()`` and crashed the queue at start.

D-700, D-704: the budgets are ``agentprov settings`` keys (``compute.cpu_budget``, ``compute.mem_gib_budget``) that
``agentprov jobs start`` gives queued jobs; the Compute pane leaves out a typed value the schema would refuse, and the
schema refuses it anyway."""

from __future__ import annotations

from typing import Any

import pytest
from agentprov import settings


@pytest.fixture
def compute(qapp: Any) -> Any:
    from agentprov_gui.ui.settings_panes import ComputePane

    pane = ComputePane(None)  # no CLI: nothing is read or written
    yield pane
    pane.deleteLater()


@pytest.mark.parametrize("value", ["na" + "n", "in" + "f", "-in" + "f", "1e" + "999", "-" + "3", "0", "0.0", " "])
def test_invalid_mem_budget_is_left_out(compute: Any, value: str) -> None:
    compute.mem_budget.setText(value)
    assert "compute.mem_gib_budget" not in compute.values()
    with pytest.raises(settings.SettingsError):
        settings.coerce("compute.mem_gib_budget", value)


@pytest.mark.parametrize("value", [chr(0xB2), chr(0x663), chr(0xFF18), "0", "00", "-" + "1", "8.5", "", " 8x"])
def test_invalid_cpu_budget_is_left_out(compute: Any, value: str) -> None:
    compute.cpu_budget.setText(value)
    assert "compute.cpu_budget" not in compute.values()


def test_valid_budgets_are_saved(compute: Any) -> None:
    compute.cpu_budget.setText("8")
    compute.mem_budget.setText("16")
    assert {k: v for k, v in compute.values().items() if "budget" in k} == {"compute.cpu_budget": 8,
                                                                          "compute.mem_gib_budget": 16.0}
