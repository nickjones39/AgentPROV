"""Regeneration-batch items 9 and 11 (D-372): one completeness rule on every path. An AgentDyn retry is inferred under
``agentdyn.last_assistant_content_none_max3_unverified@1`` (class I: AgentDyn's code is not verified, D-24), so it proves
no loss (B6, H.3.2(2)) and the execution is ``unverifiable`` on all three paths that compute the index ``completeness``:

1. the importer's index row (``importer._index``: ``proven_loss_codes`` over the seal issues, then
   ``index_completeness``);
2. a ``derive``/``recompute`` (re-map) row (``corpus/derive.py`` ``_entry``: ``facets.completeness_of``);
3. ``verify --level chain``'s ``index.completeness`` check (``corpus/verify.py``: ``facets.completeness_of``).

They must agree, or a freshly imported item-3 corpus fails ``verify chain``. Synthetic log only."""

from __future__ import annotations

from test_agentdyn import _block, _call, a_log, map_a

from agentprov.adapters.runner import importer
from agentprov.aer.reader import load_aer_bytes
from agentprov.corpus import derive, facets, verify


def _retry_log() -> dict:
    call = _call("get_shopping_account_user_information", {}, "call_1")
    return a_log(messages=[
        {"role": "system", "content": _block("You are a helpful assistant.")},
        {"role": "user", "content": _block("Show my account.")},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "content": _block("{'Email': 'x'}"), "tool_call_id": "call_1", "tool_call": call, "error": None},
        {"role": "assistant", "content": None, "tool_calls": []},
    ])


def _importer_completeness(m) -> str:
    """What ``importer._index`` writes for this unit (the same expressions, over the sealed unit)."""
    accounting = m.info.accounting.to_json()
    checks = accounting.get("checks")
    seal_codes = {str(i["code"]) for i in m.info.issues}
    unproven = (seal_codes & importer._LOSS_CODES) - importer.proven_loss_codes(m.info.issues)
    return importer.index_completeness(degenerate=False, accounting=str(accounting.get("status")),
                                       checks_evaluated=len(checks) if isinstance(checks, list) else 0,
                                       unit_kind=str(m.header.get("unit")), seal_codes=seal_codes - unproven)


def test_an_inferred_retry_is_unverifiable_on_every_path():
    m = map_a(_retry_log())
    retry = m.issues("retry_passes_inferred")
    assert retry and all(i["rule"].startswith("agentdyn.last_assistant_content_none_max3_unverified@1") for i in retry)
    aer = load_aer_bytes(m.data)
    assert _importer_completeness(m) == facets.completeness_of(aer) == "unverifiable"
    # derive/recompute and verify chain compute the row with the one shared function
    assert derive.completeness_of is facets.completeness_of and verify.completeness_of is facets.completeness_of


def test_a_proven_loss_is_known_incomplete_on_every_path():
    """The same log under a profile whose code is verified would cite the D rule: simulated on the seal issues."""
    issues = [{"code": "retry_passes_inferred", "ids": ["att0"], "rule": "agentdyn.last_assistant_content_none_max3@1"}]
    assert importer.proven_loss_codes(issues) == facets.proven_loss_codes(issues, importer.rule_class) \
        == frozenset({"retry_passes_inferred"})
