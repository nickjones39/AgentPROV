"""Identity resolution from the run directory and the profile's identity table (docs/architecture D.4.3, D.4.5)."""

from __future__ import annotations

from agentprov.adapters.agentdojo.identity import resolve_identity
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.profiles import load_profile

TABLE = family_table(load_profile("agentdojo-upstream")).identity


def test_model_and_defence_from_the_directory():
    ident = resolve_identity("gpt-4o-2024-05-13-transformers_pi_detector", "gpt-4o-2024-05-13-transformers_pi_detector", TABLE)
    assert ident.model == "gpt-4o-2024-05-13" and ident.defences == ("transformers_pi_detector",)
    assert ident.model_rule == "agentdojo.pipeline_dir_is_model_identity@1" and not ident.pipeline_name_mismatch
    plain = resolve_identity("claude-3-opus-20240229", "claude-3-opus-20240229", TABLE)
    assert plain.model == "claude-3-opus-20240229" and plain.defences == ()
    both = resolve_identity("m-tool_filter-repeat_user_prompt", "m-tool_filter-repeat_user_prompt", TABLE)
    assert both.model == "m" and both.defences == ("repeat_user_prompt", "tool_filter")  # sorted by name (E6)
    mismatch = resolve_identity("gpt-4o-2024-05-13", "local", TABLE)
    assert mismatch.pipeline_name_mismatch and mismatch.model == "gpt-4o-2024-05-13"  # pipeline_name never wins
    assert resolve_identity(None, "gpt-4o", TABLE).model is None


def test_identity_table_rows():
    llama = resolve_identity("meta-llama_Llama-3-70b-chat-hf", "meta-llama_Llama-3-70b-chat-hf", TABLE)
    assert llama.model == "meta-llama/Llama-3-70b-chat-hf" and llama.row is not None
    mixtral = resolve_identity("mistralai_Mixtral-8x7B-Instruct-v0.1", "mistralai_Mixtral-8x7B-Instruct-v0.1", TABLE)
    assert mixtral.model == "mistralai/Mixtral-8x7B-Instruct-v0.1"
    local = resolve_identity("Meta-SecAlign-70B-repeat_user_prompt", "local-repeat_user_prompt", TABLE)
    assert local.model == "facebook/Meta-SecAlign-70B" and local.model_rule == "agentdojo.local_dir_model_identity@1"
    assert local.defences == ("repeat_user_prompt",) and not local.pipeline_name_mismatch
    assert resolve_identity("Meta-SecAlign-70B", "gpt", TABLE).pipeline_name_mismatch
