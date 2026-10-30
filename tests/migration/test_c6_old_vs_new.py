"""Gate C6, comparer half (docs/architecture J.3.4 row C6; K.9.2; marker ``old_package``).

Reads the work directory the backend producer (``backends/agentdojo/tests/test_c6_old_vs_new.py``) wrote under
``$AGENTPROV_C6_WORK`` and compares the baseline generator's outputs with the new side's mapped sessions through
:func:`agentprov.migration.c6.compare_work` and the register ``migration/expected_differences.toml``. Without the
variable (or with an empty work directory) it skips with the reason: gate C runs in the ``old-vs-new`` job, never in
the default suites. Failures name scenarios, check ids, XD ids and JSON Pointers only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agentprov.migration.c6 import compare_work, summary
from agentprov.migration.xd import load_register

pytestmark = pytest.mark.old_package

ENV_WORK = "AGENTPROV_C6_WORK"


def _work() -> Path:
    value = os.environ.get(ENV_WORK, "").strip()
    if not value:
        pytest.skip(f"{ENV_WORK} is not set: run the backend producer of gate C6 first (old_package gate)")
    work = Path(value).expanduser()
    if not any(work.glob("*/scenario.json")):
        pytest.skip(f"{ENV_WORK} holds no C6 scenario")
    return work


def test_c6_old_vs_new() -> None:
    work = _work()
    result = compare_work(work, load_register())
    rows = summary(result)
    (work / "c6-summary.json").write_text(json.dumps({"ok": result.ok, "rows": rows,
                                                      "listed": result.scenarios, "missing": result.missing,
                                                      "extra": result.extra,
                                                      "xd_counts": result.register.counts_by_entry(),
                                                      "register_failures": result.register.failures()},
                                                     indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert result.scenarios is not None, "manifest.json is absent or not agentprov-c6-work/1"
    assert not result.missing and not result.extra, {"missing": result.missing, "extra": result.extra}
    failing = [(r["scenario"], r["category"], r["errors"], r["observations"]) for r in rows if r["verdict"] != "pass"]
    assert result.ok, failing
