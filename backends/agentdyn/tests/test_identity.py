"""The environment is AgentDyn at its pin (identity from PEP 610, never the version string; D-680, D-682), and the
harness selects the AgentDyn backend for it."""

import hashlib
import importlib.metadata
import importlib.util
import json

import pytest

from support import AGENTDOJO_SYSTEM_PROMPT_SHA256, PIN, REPO, SYSTEM_PROMPT_SHA256

pytestmark = pytest.mark.backend_agentdyn


def test_agentdyn_commit_from_pep610_direct_url():
    raw = importlib.metadata.distribution("agentdojo").read_text("direct_url.json")
    assert raw is not None, "agentdojo was not installed from a direct URL"
    info = json.loads(raw)
    assert info["vcs_info"]["vcs"] == "git" and info["vcs_info"]["commit_id"] == PIN
    assert info["url"] == REPO and "subdirectory" not in info


def test_agentdyn_shares_the_stock_name_and_version():
    assert importlib.metadata.version("agentdojo") == "0.1.35"


def test_agentprov_core_is_not_importable():
    assert importlib.util.find_spec("agentprov") is None


def test_the_worker_selects_the_agentdyn_backend():
    from agentprov_backend.agentdyn import AgentDynBackend
    from agentprov_backend.identity import AGENTDYN_GUARDED_NAMES
    from agentprov_backend.runner import select_backend

    backend = select_backend()
    assert isinstance(backend, AgentDynBackend) and backend.backend_id == "agentdyn"
    ident = backend.identity()
    assert ident.source == {"kind": "git", "repo": REPO, "commit": PIN}
    for module, name in AGENTDYN_GUARDED_NAMES:
        assert f"{module}.{name}" in ident.guarded_sources
    assert ident.lock_source == "project_lock"
    assert ident.suite_set == ("workspace", "travel", "banking", "slack", "shopping", "github", "dailylife")


def test_the_default_system_prompt_is_agentdyns_not_agentdojos():
    """Design F-1: the hello identity reports AgentDyn's default (the auto-complete line), the digest the source
    profile pins for the imported variant-A logs."""
    from agentdojo.agent_pipeline.agent_pipeline import load_system_message

    from agentprov_backend.agentdyn import AgentDynBackend

    text = load_system_message(None)
    assert text.rstrip().endswith("Complete all tasks automatically without requesting user confirmation.")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == SYSTEM_PROMPT_SHA256 != AGENTDOJO_SYSTEM_PROMPT_SHA256
    assert AgentDynBackend().identity().default_system_prompt_sha256 == SYSTEM_PROMPT_SHA256


def test_the_temperature_rule_mirrors_agentdyns_code():
    """``agentdyn.temperature_transmitted@1`` is computed by the backend's own copy of the rule; it must agree with
    AgentDyn's ``_supports_temperature`` (whose source digest is guarded)."""
    from agentdojo.agent_pipeline.llms.openai_llm import _supports_temperature

    from agentprov_backend.agentdyn import temperature_transmitted

    for model in ("gpt-4o-mini", "o1", "o3-mini", "O4-mini", "gpt-5", "gpt-5-nano", "qwen3-max", "claude-x", "go1"):
        assert (temperature_transmitted(model, 0.0) is not None) == _supports_temperature(model), model


def test_another_commit_is_refused(monkeypatch):
    from agentprov_backend import identity
    from agentprov_backend.agentdyn import AgentDynBackend
    from agentprov_backend.attacks import UnsupportedConfiguration

    real = identity._dist_source
    monkeypatch.setattr(identity, "_dist_source", lambda d: {**real(d), "commit": "0" * 40})
    with pytest.raises(UnsupportedConfiguration, match="not AgentDyn"):
        AgentDynBackend().identity()
