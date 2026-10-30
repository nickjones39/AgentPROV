"""R-10p-2 and D-182 with R-10p-3 (routed from phases 10p and 10h; user-confirmed 2026-10-13).

* R-10p-2: an agent whose model events all name one model role gets that role's model from ``eval.model_roles`` as its
  requested model (control-arena's ``none/none`` logs);
* D-182: a profile's ``[[family.inspect.redact]]`` rules replace whole observed model ids that hold an account path
  (scope ``model_id``) and account segments in harness-written fields (scope ``harness_text``: the sample error and its
  traceback, kept events, ``sample_metadata``, ...), never in content; the original is not recorded anywhere in the AER.
Synthetic samples with a made-up account only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import inspect_support as support
import pytest
from test_item12 import PRODUCER, run

from agentprov.adapters.inspect.redact import parse_redact_rules
from agentprov.adapters.profiles import parse_profile
from agentprov.errors import ProfileError

REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / "src" / "agentprov" / "adapters" / "inspect" / "profiles" / "survey-agentharm.profile.toml"
ACCOUNT = "madeupaccount"
CHECKPOINT = "vllm//workspace/shared/outputs/job7/run3/merged"
REDACT = '''
[[family.inspect.redact]]
id = "local_checkpoint_path"
scope = "model_id"
pattern = '/workspace/shared/outputs/[^\\s"]+'
replacement = "<local-checkpoint:{span12}/{leaf}>"
leaf = '^(merged|lora)$'

[[family.inspect.redact]]
id = "home_account"
scope = "harness_text"
pattern = '(?<=/Users/)[^/\\s"]+(?=/)'
replacement = "<account>"
'''


def _profile_with_redact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``test_item12.band_profile`` return the AgentHarm profile with a redact table (a test variant)."""
    import test_item12

    def band(producer: str):
        text = PROFILE.read_text(encoding="utf-8") + REDACT
        return parse_profile(text.encode("utf-8"), source="test-variant")
    monkeypatch.setattr(test_item12, "band_profile", band)


# ------------------------------------------------------------------------------------------------ R-10p-2
def _roles_sample(role: str | None) -> dict[str, Any]:
    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for e in sample["events"]:
            if e["event"] == "model" and e["model"].endswith("agent:1b"):
                e["role"] = role
    return support.basic_sample(tune=tune)


def test_the_agent_model_comes_from_its_role(tmp_path, monkeypatch):
    import test_item12

    def header_with_roles(producer: str = PRODUCER, version: int = 2) -> dict[str, Any]:
        h = original(producer, version)
        h["eval"]["model"] = "none/none"
        h["eval"]["model_roles"] = {"untrusted": {"model": "ollama/synthetic-agent:1b", "config": {"temperature": 0.5}},
                                    "trusted": {"model": "ollama/synthetic-judge:1b"}}
        return h
    original = support.synthetic_header
    monkeypatch.setattr(test_item12.support, "synthetic_header", header_with_roles)
    u, _prov = run(tmp_path / "a", _roles_sample("untrusted"))
    agent = next(a for a in u.of_kind("actor") if a["id"] == "agent")
    assert agent["model"] == {"requested": "ollama/synthetic-agent:1b"} and agent["params"] == {"temperature": 0.5}
    assert agent["evf"]["/model"] == "D" and "inspect.agent_model_from_role@1#/model" in agent["rule"]
    u, _prov = run(tmp_path / "b", _roles_sample(None))  # no role on the events: eval.model as before
    agent = next(a for a in u.of_kind("actor") if a["id"] == "agent")
    assert agent["model"] == {"requested": "none/none"} and not any("agent_model_from_role" in r for r in agent.get("rule", []))


# ------------------------------------------------------------------------------------------------ D-182
def _account_sample() -> dict[str, Any]:
    trace = f'Traceback (most recent call last):\n  File "/Users/{ACCOUNT}/proj/run.py", line 3\nValueError: x'

    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        for e in sample["events"]:
            if e["event"] == "model" and e["model"].endswith("agent:1b"):
                e["model"] = CHECKPOINT
        for m in sample["messages"]:
            if m["role"] == "assistant" and m["content"] == "Synthetic final answer.":
                m["content"] = f"I looked in /Users/{ACCOUNT}/notes for you."  # model output: content, never redacted
        for m in sample["events_data"]["messages"]:
            if m["role"] == "assistant" and m["content"] == "Synthetic final answer.":
                m["content"] = f"I looked in /Users/{ACCOUNT}/notes for you."
        for e in sample["events"]:
            for c in (e.get("output") or {}).get("choices", []):
                if c["message"]["content"] == "Synthetic final answer.":
                    c["message"]["content"] = f"I looked in /Users/{ACCOUNT}/notes for you."
        sample["error"] = {"message": "ValueError: x", "traceback": trace, "traceback_ansi": trace}
        sample["metadata"]["carrier_query_path"] = f"/Users/{ACCOUNT}/data/q.json"
    return support.basic_sample(tune=tune)


def test_model_ids_and_harness_text_are_redacted(tmp_path, monkeypatch):
    import test_item12

    def header_with_checkpoint(producer: str = PRODUCER, version: int = 2) -> dict[str, Any]:
        h = original(producer, version)
        h["eval"]["model"] = CHECKPOINT
        return h
    original = support.synthetic_header
    monkeypatch.setattr(test_item12.support, "synthetic_header", header_with_checkpoint)
    _profile_with_redact(monkeypatch)
    u, _prov = run(tmp_path, _account_sample())
    text = u.data.decode("utf-8")
    assert "/workspace/shared/outputs" not in text  # the checkpoint path, everywhere
    outside_content = [json.dumps(r) for r in u.of_kind("execution") + u.of_kind("scope") + u.of_kind("actor")]
    assert not any(f"/Users/{ACCOUNT}/" in line for line in outside_content)
    outputs = [p.get("text") for m in u.of_kind("message") if m["role"] == "assistant" for p in m["parts"]]
    assert f"I looked in /Users/{ACCOUNT}/notes for you." in outputs  # model output stays verbatim
    agent = next(a for a in u.of_kind("actor") if a["id"] == "agent")
    label = agent["model"]["requested"]
    assert label.startswith("vllm/<local-checkpoint:") and label.endswith("/merged>")
    assert agent["evf"]["/model/requested"] == "D" and "inspect.value_redacted@1#/model/requested" in agent["rule"]
    version = parse_profile(PROFILE.read_bytes(), source="shipped").version  # the rule ids carry the profile version
    assert {"p": "/model/requested", "rule": f"survey-agentharm@{version}#local_checkpoint_path"} in agent["ext"]["inspect"]["redacted"]
    run_scope = next(r for r in u.of_kind("scope") if r["id"] == "run")
    assert "/Users/<account>/proj/run.py" in run_scope["ext"]["inspect"]["error"]["traceback"]
    assert any(e["rule"] == f"survey-agentharm@{version}#home_account" for e in run_scope["ext"]["inspect"]["redacted"])
    issues = [i for i in u.info.issues if i["code"] == "inspect.value_redacted"]
    assert len(issues) == 1 and "run" in issues[0]["ids"] and "agent" in issues[0]["ids"]


def test_the_same_span_gets_the_same_label_in_another_log(tmp_path, monkeypatch):
    import test_item12

    def header_with_checkpoint(producer: str = PRODUCER, version: int = 2) -> dict[str, Any]:
        h = original(producer, version)
        h["eval"]["model"] = CHECKPOINT
        return h
    original = support.synthetic_header
    monkeypatch.setattr(test_item12.support, "synthetic_header", header_with_checkpoint)
    _profile_with_redact(monkeypatch)
    labels = []
    for sub in ("a", "b"):
        u, _prov = run(tmp_path / sub, _account_sample())
        labels.append(next(a for a in u.of_kind("actor") if a["id"] == "agent")["model"]["requested"])
    assert labels[0] == labels[1]


@pytest.mark.parametrize("entry", [
    {"id": "x", "scope": "everywhere", "pattern": "a", "replacement": "b"},
    {"id": "x", "scope": "model_id", "pattern": "a", "replacement": "{original}"},
    {"id": "x", "scope": "model_id", "pattern": "a", "replacement": "{leaf}"},  # {leaf} without a leaf pattern
    {"id": "x", "scope": "model_id", "pattern": "a*", "replacement": "b"},  # matches the empty string
    {"id": "x", "scope": "model_id", "pattern": "a", "replacement": "b", "extra": 1},
])
def test_malformed_redact_rules_are_refused(entry):
    with pytest.raises(ProfileError):
        parse_redact_rules([entry], "test")


def test_a_model_id_as_an_object_key_is_redacted_bf21():
    """Bug pass BF-21: ``ext.inspect.model_usage`` (and ``role_usage``) are keyed by model id; the key is redacted like
    a value, and so is the id inside a JSON Pointer (an ``ext.lex`` key-order pointer, an evf key)."""
    from agentprov.adapters.inspect.redact import Redactor

    rules = parse_redact_rules([{"id": "ckpt", "scope": "model_id", "pattern": r"/workspace/shared/outputs/[^ ]+",
                                 "replacement": "/local-checkpoint-{span12}"}], "p")
    r = Redactor("prof", 1, rules, [CHECKPOINT])
    run_scope = {"k": "scope", "id": "run", "ext": {"inspect": {"model_usage": {CHECKPOINT: {"input_tokens": 10}}},
                                                     "lex": {"ord": {"/ext/inspect/model_usage/vllm~1~1workspace~1shared"
                                                                     "~1outputs~1job7~1run3~1merged": ["b", "a"]}}}}
    done = r.apply(run_scope, lambda p: "inspect.value_redacted@1#" + p)
    blob = json.dumps(run_scope)
    assert "/workspace/shared/outputs" not in blob and "~1workspace~1shared~1outputs" not in blob, blob
    assert {p.split("/")[2] for p, _ in done} == {"inspect", "lex"}  # the model_usage key and the ext.lex pointer key


def test_model_usage_keys_are_redacted_end_to_end_bf21(tmp_path, monkeypatch):
    import test_item12

    def header_with_checkpoint(producer: str = PRODUCER, version: int = 2) -> dict[str, Any]:
        h = original(producer, version)
        h["eval"]["model"] = CHECKPOINT
        return h
    original = support.synthetic_header
    monkeypatch.setattr(test_item12.support, "synthetic_header", header_with_checkpoint)
    _profile_with_redact(monkeypatch)
    sample = _account_sample()
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    sample["model_usage"] = {CHECKPOINT: usage, "ollama/synthetic-judge:1b": usage}
    sample["role_usage"] = {"agent": usage}
    u, _prov = run(tmp_path, sample)
    text = u.data.decode("utf-8")
    assert "/workspace/shared/outputs" not in text and "~1workspace~1shared~1outputs" not in text
    run_scope = next(r for r in u.of_kind("scope") if r["id"] == "run")
    keys = list(run_scope["ext"]["inspect"]["model_usage"])
    assert any(k.startswith("vllm/<local-checkpoint:") for k in keys) and "ollama/synthetic-judge:1b" in keys
