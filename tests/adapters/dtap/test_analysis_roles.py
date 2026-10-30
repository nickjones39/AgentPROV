"""The analysis tools read DTap's verbatim role ``agent`` as model output (sample check §9.1 b4; D-28; D.16.17 item 3).

A01 (arguments), A03 (empty turns), SA07 (text-format markers) and the marker probes keyed on role ``assistant`` and
saw nothing in a DTap corpus. They now share one grouping, ``tools/analysis/message_roles.py``, which mirrors phase 11's
``stats/field_groups.toml`` ``[message_roles]``. These tests run the tools' per-execution functions on mapped DTap
fixtures. No fixture text is printed.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any

import dtap_support as support
import pytest

TOOLS = support.REPO / "tools"


def _load(path: Path) -> ModuleType:
    name = f"_tool_{path.stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def roles() -> ModuleType:
    return _load(TOOLS / "analysis" / "message_roles.py")


def test_one_grouping_assistant_and_agent():
    r = roles()
    assert dict(r.MESSAGE_ROLES) == {"assistant": ("assistant", "agent")}
    assert r.role_group("agent") == r.role_group("assistant") == "assistant"
    assert [r.role_group(x) for x in ("user", "tool", "system", None)] == ["user", "tool", "system", None]
    assert r.is_assistant("agent") and r.is_assistant("assistant") and not r.is_assistant("user")
    assert r.group_counts({"agent": 3, "assistant": 1, "user": 2}) == {"assistant": 4, "user": 2}


def test_grouping_equals_the_stats_field_groups_when_present():
    """Phase 11's ``stats/field_groups.toml`` is the product grouping; once it is on main the two must agree."""
    node = resources.files("agentprov") / "stats" / "field_groups.toml"
    if not node.is_file():
        pytest.skip("stats/field_groups.toml is not on this branch yet (phase 11)")
    table = tomllib.loads(node.read_text(encoding="utf-8"))["message_roles"]
    assert {k: tuple(v) for k, v in table.items()} == dict(roles().MESSAGE_ROLES)


def _agent_fixture(mapped) -> tuple[str, Any]:
    for fid in sorted(mapped):
        m = mapped[fid]
        msgs = [r for r in m.records if r.get("k") == "message"]
        if msgs and msgs[-1].get("role") == "agent" and any(p.get("t") == "tool_call" for r in msgs for p in r["parts"]):
            return fid, m
    raise AssertionError("no fixture ends in an agent message after a tool call")


def test_exam2_scan_a01_a03_read_role_agent(mapped):
    scan = _load(TOOLS / "analysis2" / "exam2_scan.py")
    fid, m = _agent_fixture(mapped)
    acc = scan.Acc(m.header["ex"])
    scan.aer_semantics(acc, [*m.records, m.doc.seal], {})
    n_calls = sum(1 for r in m.records if r.get("k") == "message" for p in r["parts"] if p.get("t") == "tool_call")
    assert acc.c["a03|executions_with_assistant"] == 1, fid  # was 0: role agent was not read
    assert sum(v for k, v in acc.c.items() if k.startswith("a01|args_type|")) == n_calls > 0, fid


def test_phase10_extract_reads_role_agent_and_keeps_roles_verbatim(mapped):
    extract = _load(TOOLS / "analysis" / "phase10_extract.py")
    fid, m = _agent_fixture(mapped)
    f: dict[str, Any] = {}
    extract.aer_facts(m.doc, f)
    assert f["final_role"] == "agent" and "assistant" not in f["roles"] and f["roles"]["agent"] > 0, fid
    assert f["final_assistant_calls"] is not None, fid  # the final agent message is read as model output
    assert any(k.startswith("calls_form:") for k in f["fmt"]), fid  # SA07's per-message screen ran on agent messages


def test_phase10_aggregate_groups_verbatim_roles():
    aggregate = _load(TOOLS / "analysis" / "phase10_aggregate.py")
    assert aggregate.is_assistant("agent") and aggregate.group_counts({"agent": 2})["assistant"] == 2
