"""Finding AU-RA-5 (2026-11-05; 0.2.0 change batch D-1063, regen-batch row 179): the results-container mapper cites
``agentdojo.unexecuted_trailing_calls@1`` for ``missing_tool_result`` and ``unexecuted_tool_call`` through the D.5.4
policy, as the TraceLogger and DRIFT mappers do, so a results profile that verifies no code infers the lost result. All
content is synthetic."""

from __future__ import annotations

from test_rescont import _call, container, ok, one, row

from agentprov.adapters.runner.importer import proven_loss_codes


def test_a_results_row_missing_tool_result_cites_the_twin():
    """A row whose non-final turn has an unanswered call (memo-ozdincer verifies no code): inferred, not proven."""
    r = row()
    r["messages"][2]["tool_calls"] = [_call("read_file", file_path="bill.txt"), _call("read_file", file_path="memo.txt")]
    m = one(container([r]))
    ok(m)
    rules = [i["rule"] for i in m.info.issues if i["code"] in ("missing_tool_result", "unexecuted_tool_call")]
    assert "missing_tool_result" in m.codes, m.codes
    assert rules and set(rules) == {"agentdojo.unexecuted_trailing_calls_unverified@1"}, m.codes
    assert "missing_tool_result" not in proven_loss_codes(m.info.issues)
