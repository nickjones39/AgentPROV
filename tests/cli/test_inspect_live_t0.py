"""inspect-live-t0 (D-663): T0's ingest identity check accepts an Inspect worker's session, and stays exactly as before
for the AgentDojo family (the new members are absent on both sides there)."""

from __future__ import annotations

import json

import pytest

from agentprov.cli.live.staging import check_capture_identity
from agentprov.errors import IdentityMismatch

AGENTDOJO_HELLO = {"distribution": "agentdojo", "version_reported": "0.1.35", "source": {"kind": "pypi"},
                   "record_digest": "a" * 64, "guarded_sources": {"x": "b" * 64}, "suite_set": ["banking"],
                   "benchmark_version": "v1.2.2", "default_system_prompt_sha256": "c" * 64,
                   "tool_definitions_sha256": "d" * 64, "python": "3.12.14", "lock_sha256": "e" * 64}
INSPECT_HELLO = {"distribution": "inspect-ai", "version_reported": "0.3.263", "source": {"kind": "pypi"},
                 "record_digest": "f" * 64, "python": "3.12.14", "lock_sha256": "e" * 64,
                 "benchmark": {"distribution": "inspect_evals", "version": "0.20.0", "source": {"kind": "pypi"},
                               "record_digest": "1" * 64},
                 "task_files_sha256": "sha256:" + "2" * 64,
                 "dataset": {"repo": "ai-safety-institute/AgentHarm", "revision": "3" * 40, "files": {"b/x.json": "4" * 64}}}


def _log(backend: str, ns: str, note: dict, identity: dict) -> bytes:
    events = [
        {"type": "session.start", "data": {"backend": {"id": backend, "version": "0.1.0"}}},
        {"type": "identity", "data": identity},
        {"type": "note", "data": {"ns": ns, "kind": "identity_digests", "payload": note}},
    ]
    return b"".join(json.dumps(e).encode() + b"\n" for e in events)


AGENTDOJO_EVENT = {"benchmark": {"dist": "agentdojo", "dist_version": "0.1.35", "name": "agentdojo",
                                 "tool_definitions_sha256": "d" * 64}}
INSPECT_EVENT = {"benchmark": {"dist": "inspect_evals", "dist_version": "0.20.0", "name": "agentharm"}}


def test_an_agentdojo_session_is_checked_exactly_as_before():
    """Byte-neutrality for the AgentDojo family: the Inspect members are absent in both the note and hello_ok."""
    check_capture_identity(_log("agentdojo", "agentdojo", AGENTDOJO_HELLO, AGENTDOJO_EVENT), AGENTDOJO_HELLO,
                           backend="agentdojo")
    for key in ("task_files_sha256", "dataset", "benchmark"):
        assert key not in AGENTDOJO_HELLO
    with pytest.raises(IdentityMismatch):  # a stray Inspect member on one side only is a mismatch
        check_capture_identity(_log("agentdojo", "agentdojo", {**AGENTDOJO_HELLO, "task_files_sha256": "x"},
                                    AGENTDOJO_EVENT), AGENTDOJO_HELLO, backend="agentdojo")
    with pytest.raises(IdentityMismatch):
        check_capture_identity(_log("agentdojo", "agentdojo", AGENTDOJO_HELLO, {"benchmark": {
            **AGENTDOJO_EVENT["benchmark"], "dist_version": "0.1.34"}}), AGENTDOJO_HELLO, backend="agentdojo")


def test_an_inspect_session_is_checked_against_its_own_identity():
    check_capture_identity(_log("inspect-agentharm", "inspect", INSPECT_HELLO, INSPECT_EVENT), INSPECT_HELLO,
                           backend="inspect-agentharm")
    for key, value in (("task_files_sha256", "sha256:" + "9" * 64), ("dataset", {"repo": "other/x"}),
                       ("benchmark", {**INSPECT_HELLO["benchmark"], "version": "0.19.0"})):
        with pytest.raises(IdentityMismatch):
            check_capture_identity(_log("inspect-agentharm", "inspect", {**INSPECT_HELLO, key: value}, INSPECT_EVENT),
                                   INSPECT_HELLO, backend="inspect-agentharm")
    with pytest.raises(IdentityMismatch):  # the identity event's benchmark version is the benchmark distribution's
        check_capture_identity(_log("inspect-agentharm", "inspect", INSPECT_HELLO, {"benchmark": {
            **INSPECT_EVENT["benchmark"], "dist_version": "0.3.263"}}), INSPECT_HELLO, backend="inspect-agentharm")


def test_an_unknown_note_namespace_does_not_count_as_the_identity_note():
    with pytest.raises(IdentityMismatch, match="no identity_digests note"):
        check_capture_identity(_log("inspect-agentharm", "other", INSPECT_HELLO, INSPECT_EVENT), INSPECT_HELLO,
                               backend="inspect-agentharm")


def _identity(primary: str, dists: dict[str, tuple[str, dict]]) -> object:
    from agentprov.cli.live.envs import DistIdentity, EnvIdentity

    return EnvIdentity("0" * 64, {n: DistIdentity(n, v, "a" * 64, src, 1) for n, (v, src) in dists.items()}, {},
                       primary)


def test_profile_pins_use_the_primary_distribution():
    import types

    from agentprov.cli.run import _check_profile_pins

    project = types.SimpleNamespace(commit=None)
    agentdojo = _identity("agentdojo", {"agentdojo": ("0.1.35", {"kind": "pypi"})})
    _check_profile_pins({"pins": {"distribution": "agentdojo", "version": "0.1.35"}}, agentdojo, project)
    inspect_id = _identity("inspect-ai", {"inspect-ai": ("0.3.263", {"kind": "pypi"}),
                                          "inspect-evals": ("0.20.0", {"kind": "pypi"})})
    live = {"pins": {"distribution": "inspect-ai", "version": "0.3.263"},
            "distribution_pins": [{"distribution": "inspect-evals", "version": "0.20.0"}]}
    _check_profile_pins(live, inspect_id, project)
    for bad in ({**live, "pins": {"distribution": "inspect-ai", "version": "0.3.264"}},
                {**live, "distribution_pins": [{"distribution": "inspect-evals", "version": "0.19.0"}]},
                {**live, "distribution_pins": [{"distribution": "nonesuch", "version": "1"}]},
                {**live, "distribution_pins": "inspect-evals"}):
        with pytest.raises(IdentityMismatch):
            _check_profile_pins(bad, inspect_id, project)


def _args(**kw):
    import argparse

    from agentprov.cli.run import _CELL_OPTIONS, _INSPECT_OPTIONS

    base = {k: None for k in (*_CELL_OPTIONS, *_INSPECT_OPTIONS)}
    base.update(plan=None, model_display_name=None)
    base.update(kw)
    return argparse.Namespace(**base)


SCRIPTED_AGENT = {"model_requested": "scripted-fake", "provider": "openai", "endpoint": "scripted", "api_key_env": None,
                  "params": {}, "llm_element": "native", "transport": "scripted", "script": "llm-script.json",
                  "base_url": None}


def test_an_inspect_plan_document_from_the_command_line():
    import tomllib

    from agentprov.cli.run import _plan_document, toml_dumps

    args = _args(task="inspect_evals/agentharm", task_param=["split=test_public", "n_irrelevant_tools=2",
                                                             "detailed_behaviors=true"],
                 samples="limit:4", message_limit=20, token_limit=60000, time_limit=600, cell_size=2,
                 judge=["refusal_judge=scripted-judge", "semantic_judge=scripted-judge"])
    doc = _plan_document(args, SCRIPTED_AGENT, backend="inspect-agentharm")
    assert doc["plan"] == {"format": "agentprov-run-plan/0.1", "backend": "inspect-agentharm"}
    assert doc["inspect"]["params"] == {"split": "test_public", "n_irrelevant_tools": 2, "detailed_behaviors": True}
    assert doc["inspect"]["samples"] == {"limit": 4} and doc["inspect"]["cell_size"] == 2
    assert doc["inspect"]["limits"] == {"message_limit": 20, "token_limit": 60000, "time_limit_s": 600}
    assert doc["judges"]["refusal_judge"]["model_requested"] == "scripted-judge"
    assert doc["judges"]["refusal_judge"]["endpoint"] == "scripted" and "api_key_env" not in doc["agent"]
    assert tomllib.loads(toml_dumps(doc)) == doc  # what the worker parses


def test_inspect_and_cell_options_never_mix():
    from agentprov.cli.common import CliUsageError
    from agentprov.cli.run import _plan_document

    with pytest.raises(CliUsageError, match="Inspect-plan options"):
        _plan_document(_args(task="t", samples="1-1", suite="banking"), SCRIPTED_AGENT, backend="inspect-agentharm")
    with pytest.raises(CliUsageError, match="need an Inspect backend"):
        _plan_document(_args(task="t", suite="banking"), SCRIPTED_AGENT, backend="agentdojo")
    with pytest.raises(CliUsageError, match="--task and --samples"):
        _plan_document(_args(task="t"), SCRIPTED_AGENT, backend="inspect-agentharm")
    for bad in (["x"], ["a b=1"], ["k=1.5"]):
        with pytest.raises(CliUsageError):
            _plan_document(_args(task="t", samples="1-1", task_param=bad), SCRIPTED_AGENT, backend="inspect-agentharm")
    with pytest.raises(CliUsageError, match="ROLE=MODEL"):
        _plan_document(_args(task="t", samples="1-1", judge=["Refusal=x"]), SCRIPTED_AGENT, backend="inspect-agentharm")

