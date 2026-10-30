"""``agentprov_backend.agentdyn`` without a benchmark package (D-682, D-683): backend selection by PEP 610 source, the
refusals, the declared instrumentation and the temperature rule. The tests that need AgentDyn installed live in
``backends/agentdyn/tests``."""

from __future__ import annotations

import pytest

from agentprov_backend import runner
from agentprov_backend.agentdyn import (
    AGENTDYN_COMMIT,
    AGENTDYN_REPO,
    REFUSED_DEFENCES,
    AgentDynBackend,
    temperature_transmitted,
)
from agentprov_backend.attacks import UnsupportedConfiguration
from agentprov_backend.identity import AGENTDYN_GUARDED_NAMES, GUARDED_NAMES
from agentprov_backend.runner import AgentConfig, CellSpec


def _source(monkeypatch: pytest.MonkeyPatch, source: dict[str, str]) -> None:
    import agentprov_backend.identity as identity

    monkeypatch.setattr(identity, "installed_source", lambda distribution="agentdojo": source)


def test_select_backend_follows_the_pep610_repository(monkeypatch):
    _source(monkeypatch, {"kind": "git", "repo": AGENTDYN_REPO, "commit": AGENTDYN_COMMIT})
    backend = runner.select_backend()
    assert isinstance(backend, AgentDynBackend) and backend.backend_id == "agentdyn"
    _source(monkeypatch, {"kind": "git", "repo": "https://github.com/xhOwenMa/AutoDojo", "commit": "0" * 40,
                          "subdirectory": "agentdojo"})
    assert runner.select_backend().backend_id == "autodojo"
    _source(monkeypatch, {"kind": "pypi"})
    assert runner.select_backend().backend_id == "agentdojo"


def test_an_agentdyn_source_at_another_commit_is_still_the_agentdyn_backend(monkeypatch):
    # selection is by repository; identity() then refuses the commit (T0 cross-checks it as well)
    _source(monkeypatch, {"kind": "git", "repo": AGENTDYN_REPO, "commit": "f" * 40})
    assert isinstance(runner.select_backend(), AgentDynBackend)


def test_gateway_compat_and_every_agentdyn_defence_are_refused():
    backend = AgentDynBackend()
    with pytest.raises(UnsupportedConfiguration, match="gateway_compat"):
        backend.check_agent(AgentConfig(model_requested="m", llm_element="gateway_compat"))
    backend.check_agent(AgentConfig(model_requested="m"))
    for defence in ("camel", "drift", "progent", "piguard_detector", "prompt_guard_2_detector"):
        cell = CellSpec("k", "shopping", "user_task_0", None, None, defence, "user_task")
        with pytest.raises(UnsupportedConfiguration, match=defence):
            backend.check_cell(cell)
    assert set(REFUSED_DEFENCES) == {"camel", "drift", "progent", "piguard_detector", "prompt_guard_2_detector"}
    backend.check_cell(CellSpec("k", "shopping", "user_task_0", "injection_task_0", "tool_knowledge", None, "attacked"))


@pytest.mark.parametrize(("model", "temperature", "expected"), [
    ("gpt-4o-mini", 0.0, 0.0),
    ("qwen3-max", 0.7, 0.7),
    ("o3-mini", 0.0, None),
    ("GPT-5-nano", 0.0, None),
    ("o4-mini", None, None),
    ("gpt-4o", None, None),
])
def test_temperature_rule_of_chat_completion_request(model, temperature, expected):
    assert temperature_transmitted(model, temperature) == expected


def _ids(items):
    return [i["id"] for i in items]


def test_instrumentation_declares_agentdyn_behaviour_and_drops_the_stock_temperature_item():
    backend = AgentDynBackend()
    items = backend.instrumentation(AgentConfig(model_requested="gpt-4o-mini", transport="scripted"), None, {},
                                    mirror_source_sha256=None, environ={})
    ids = _ids(items)
    assert "agentdojo.temperature_not_transmitted@1" not in ids
    assert {"agentdyn.temperature_transmitted@1", "agentdyn.malformed_tool_calls_dropped@1",
            "agentdyn.json_decode_error_imposes_outcome@1", "agentdyn.model_output_last_assistant@1"} <= set(ids)
    assert "agentdyn.system_role_for_qwen3_max@1" not in ids
    temp = next(i for i in items if i["id"] == "agentdyn.temperature_transmitted@1")
    assert temp["params"]["transmitted"] == 0.0 and temp["kind"] == "harness_policy"
    assert all(i["kind"] == "harness_policy" for i in items if i["id"].startswith("agentdyn."))
    qwen = backend.instrumentation(AgentConfig(model_requested="qwen3-max"), None, {}, mirror_source_sha256=None,
                                   environ={})
    assert "agentdyn.system_role_for_qwen3_max@1" in _ids(qwen)
    o3 = backend.instrumentation(AgentConfig(model_requested="o3"), None, {}, mirror_source_sha256=None, environ={})
    assert next(i for i in o3 if i["id"] == "agentdyn.temperature_transmitted@1")["params"]["transmitted"] is None


def test_declared_semantics_and_guarded_names():
    backend = AgentDynBackend()
    assert "JSONDecodeError" in backend.declared_semantics["run_error"]
    assert backend.declared_semantics["benchmark"].startswith("agentdojo (AgentDyn 5353cf76")
    assert not set(AGENTDYN_GUARDED_NAMES) & set(GUARDED_NAMES)
    assert ("agentdojo.agent_pipeline.agent_pipeline", "load_system_message") in AGENTDYN_GUARDED_NAMES


def test_record_digest_never_stats_the_files_record_lists(tmp_path, monkeypatch):
    """L-DY blocker (2026-10-23): ``Distribution.files`` stats every listed file, and the real-model sandbox denies a
    stat of ``.env.*`` (AgentDyn ships ``agentdojo/defenses/camel/.env.example``). The digest reads RECORD only."""
    import hashlib
    import importlib.metadata
    import os

    from agentprov_backend.identity import record_digest

    info = tmp_path / "agentdojo-0.1.35.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: agentdojo\nVersion: 0.1.35\n", encoding="utf-8")
    record = (b"agentdojo/defenses/camel/.env.example,sha256=x,88\r\n"
              b"agentdojo-0.1.35.dist-info/METADATA,,\r\nagentdojo-0.1.35.dist-info/RECORD,,\r\n")
    (info / "RECORD").write_bytes(record)
    real_stat = os.stat

    def stat(path, *args, **kwargs):
        if os.path.basename(os.fspath(path)).startswith(".env"):
            raise PermissionError(1, "Operation not permitted", os.fspath(path))
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat)
    dist = importlib.metadata.PathDistribution(info)
    with pytest.raises(PermissionError):
        dist.files  # noqa: B018 - the stdlib path this digest must not take
    assert record_digest(dist) == hashlib.sha256(record).hexdigest()
