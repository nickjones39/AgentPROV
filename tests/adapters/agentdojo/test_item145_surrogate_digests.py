"""Regeneration-batch item 145 (item-7 follow-up; found by artefact catalogues): the system-prompt variant digest and
the autodojo payload digests encode with ``surrogatepass``, so a lone UTF-16 surrogate in the source (C.11.4) gives no
match instead of a whole-log ``adapter_defect``. Synthetic logs."""

from __future__ import annotations

from source_support import final, log_with, map_synthetic, ok

from agentprov.adapters.agentdojo.hooks.autodojo import slot_cells, table_of

LONE = "\ud800"


def _survey(doc):
    attack = doc.get("attack_type") or "none"
    return (f"agentdojo/results/runs_qwen3_14b/openai-compatible/{doc['suite_name']}/{doc['user_task_id']}/{attack}/"
            f"{doc.get('injection_task_id') or 'none'}.json")


def test_a_lone_surrogate_system_prompt_is_unrecognised_not_a_defect():
    """survey-runs pins system-prompt variants; a system text holding a lone surrogate matches none of them."""
    doc = log_with([final("Done.")], pipeline_name="openai-compatible", benchmark_version="v1.2.2")
    system = doc["messages"][0]
    assert system["role"] == "system"
    if isinstance(system["content"], list):
        system["content"][0]["content"] += LONE
    else:
        system["content"] += LONE
    m = map_synthetic("survey-runs", doc, _survey(doc))
    assert not m.outcome.degenerate, m.outcome.error_code
    ok(m)
    assert m.issues("agentdojo.system_prompt_unrecognised")


def test_a_lone_surrogate_payload_finds_no_cache_cell():
    table, _prov, _header = table_of("autodojo-via-rope")
    assert slot_cells(table, "banking", "user_task_0", "injection_bill_text", f"payload {LONE}") == ("none", ())
