"""``AttackFactory`` (no hidden ``MODEL_NAMES`` mutation; D.10.5), run-plan expansion (``agentprov-run-plan/0.1``;
D.10.1) and the worker-side identity report (D.10.6)."""

from __future__ import annotations

import pytest
from agentdojo.models import MODEL_NAMES
from agentdojo.task_suite.load_suites import get_suites

from agentprov_backend.attacks import AttackFactory, RecordingAttack, UnsupportedConfiguration, scoped_model_name
from agentprov_backend.identity import GUARDED_NAMES, LockDigestUnavailable, benchmark_identity, lock_digest
from agentprov_backend.runner import PLAN_FORMAT, enumerate_cells, expand_plan, load_plan


class _Pipe:
    def __init__(self, name):
        self.name = name


def _suite():
    return get_suites("v1.2.2")["banking"]


def test_scoped_registration_restores_the_table_even_on_error():
    before = list(MODEL_NAMES.items())
    with pytest.raises(RuntimeError):
        with scoped_model_name("my-model", "My Model"):
            assert MODEL_NAMES["my-model"] == "My Model"
            raise RuntimeError("boom")
    assert list(MODEL_NAMES.items()) == before
    with scoped_model_name("gpt-4o-2024-05-13", "Other"):
        pass
    assert list(MODEL_NAMES.items()) == before


def test_factory_uses_the_stock_name_or_a_declared_display_name():
    before = dict(MODEL_NAMES)
    stock = AttackFactory(_suite(), _Pipe("gpt-4o-2024-05-13")).create("important_instructions", {})
    assert stock.attack.model_name == "GPT-4" and stock.instrumentation == ()
    named = AttackFactory(_suite(), _Pipe("acme/model-x")).create("important_instructions",
                                                                     {"model_display_name": "Model X"})
    assert named.attack.model_name == "Model X"
    (item,) = named.instrumentation
    assert item["id"] == "agentdojo.attack_model_display_name@1" and item["kind"] == "attack_parameter"
    assert dict(MODEL_NAMES) == before
    # an attack that names no model needs nothing
    assert AttackFactory(_suite(), _Pipe("acme/model-x")).create("direct", {}).instrumentation == ()
    with pytest.raises(UnsupportedConfiguration, match="model_display_name"):
        AttackFactory(_suite(), _Pipe("acme/model-x")).create("important_instructions", {})
    with pytest.raises(UnsupportedConfiguration, match="contradicts"):
        AttackFactory(_suite(), _Pipe("gpt-4o-2024-05-13")).create("important_instructions",
                                                                   {"model_display_name": "Not GPT"})
    with pytest.raises(UnsupportedConfiguration, match="unknown attack"):
        AttackFactory(_suite(), _Pipe("x")).create("no_such_attack", {})
    assert dict(MODEL_NAMES) == before


def test_display_name_preset_reproduces_the_baseline_title_case_rule():
    """F-13: the v2.3 ``MODEL_NAMES[model_id] = model_id.replace("-", " ").title()`` becomes a declared preset."""
    before = dict(MODEL_NAMES)
    pipe = _Pipe("deepseek/deepseek-chat+prov")
    built = AttackFactory(_suite(), pipe).create(
        "important_instructions", {"model_display_name_preset": "adprov-v2.3-title-case"}, model_id="deepseek-chat")
    assert built.attack.model_name == "Deepseek Chat"
    (item,) = built.instrumentation
    assert item["kind"] == "attack_parameter"
    assert item["params"] == {"display_name": "Deepseek Chat", "attack": "important_instructions", "checked": True,
                              "preset": "adprov-v2.3-title-case"}
    assert dict(MODEL_NAMES) == before  # never mutated beyond construction
    # a stock entry still wins (the baseline's substring lookup found stock keys first): no preset applied
    stock = AttackFactory(_suite(), _Pipe("gpt-4o-2024-05-13")).create(
        "important_instructions", {"model_display_name_preset": "adprov-v2.3-title-case"}, model_id="gpt-4o-2024-05-13")
    assert stock.attack.model_name == "GPT-4" and stock.instrumentation == ()
    with pytest.raises(UnsupportedConfiguration, match="contradicts preset"):
        AttackFactory(_suite(), pipe).create("important_instructions", {
            "model_display_name_preset": "adprov-v2.3-title-case", "model_display_name": "Other"},
            model_id="deepseek-chat")
    with pytest.raises(UnsupportedConfiguration, match="unknown"):
        AttackFactory(_suite(), pipe).create("important_instructions", {"model_display_name_preset": "nope"},
                                             model_id="deepseek-chat")
    with pytest.raises(UnsupportedConfiguration, match="model id"):
        AttackFactory(_suite(), pipe).create("important_instructions",
                                             {"model_display_name_preset": "adprov-v2.3-title-case"})
    assert dict(MODEL_NAMES) == before


def test_recording_attack_is_transparent():
    built = AttackFactory(_suite(), _Pipe("gpt-4o-2024-05-13")).create("important_instructions", {})
    seen = []

    class Hooks:
        def fixture(self, kind, vector, content):
            seen.append((kind, vector, content))

    proxy = RecordingAttack(built.attack, Hooks())
    suite = _suite()
    ut, it = suite.get_user_task_by_id("user_task_1"), suite.get_injection_task_by_id("injection_task_0")
    injections = proxy.attack(ut, it)
    assert injections == built.attack.attack(ut, it)
    assert proxy.name == "important_instructions" and proxy.is_dos_attack is False
    assert [(k, v) for k, v, _ in seen] == [("injection_payload", v) for v in injections]


PLAN = f"""
[plan]
format = "{PLAN_FORMAT}"
suites = ["banking"]
user_tasks = "0-2"
injection_tasks = ["injection_task_0", "injection_task_1"]
attacks = ["important_instructions", "dos"]

[agent]
model_requested = "acme/model-x"
endpoint = "openrouter"
api_key_env = "OPENROUTER_API_KEY"

[attack_params]
model_display_name = "Model X"
"""


def test_plan_expansion_and_digest():
    plan = load_plan(PLAN)
    kinds = [c.kind for c in plan.cells]
    assert kinds == ["user_task"] * 3 + ["attacked"] * 6 + ["dos"] * 3
    assert plan.cells[0].cell_key == "banking/user_task_0/none/none"
    assert {c.injection_task_id for c in plan.cells if c.kind == "dos"} == {"injection_task_0"}
    assert all(c.attack_params == {"model_display_name": "Model X"} for c in plan.cells if c.attack)
    assert load_plan(PLAN).plan_sha256 == plan.plan_sha256 and len(plan.plan_sha256) == 64
    assert load_plan(PLAN.replace('"0-2"', '"0-1"')).plan_sha256 != plan.plan_sha256
    assert plan.to_json()["format"] == PLAN_FORMAT


@pytest.mark.parametrize("bad", [
    PLAN.replace(PLAN_FORMAT, "run-plan/0.1"),
    PLAN.replace('format = ', 'formats = '),
    PLAN + '\n[plan.extra]\n',
    PLAN.replace('suites = ["banking"]', 'suites = ["banking"]\ndefence = "no_such_defence"'),  # not in the registry
    PLAN.replace('suites = ["banking"]', 'suites = ["slack"]\ndefence = "mandate_intent"'),  # outside its suites
    PLAN.replace('suites = ["banking"]', 'suites = ["banking"]\ntool_output_format = "json"'),
    PLAN.replace('suites = ["banking"]', 'suites = ["nope"]'),
    PLAN.replace('"0-2"', '"0-99"'),
    PLAN.replace('model_requested = "acme/model-x"', ''),
    "not toml [",
])
def test_bad_plans_are_refused(bad):
    with pytest.raises(UnsupportedConfiguration):
        load_plan(bad)


def test_benign_only_and_pre_pass_cells():
    cells = enumerate_cells("v1.2.2", ["slack"], user_tasks=["user_task_0"], injection_tasks="0",
                            attacks=["important_instructions"], benign="only", injection_tasks_as_user_tasks=True)
    assert [(c.kind, c.user_task_id) for c in cells] == [("injection_task_as_user_task", "injection_task_1"),
                                                         ("user_task", "user_task_0")]
    with pytest.raises(UnsupportedConfiguration):
        expand_plan({"plan": {"format": PLAN_FORMAT, "suites": ["banking"]}, "agent": {}})


def test_identity_report():
    ident = benchmark_identity()
    assert ident.distribution == "agentdojo" and ident.version_reported == "0.1.35"
    assert ident.source == {"kind": "pypi"}
    assert set(ident.guarded_sources) == {f"{m}.{p}" for m, p in GUARDED_NAMES}
    assert ident.suite_set == ("workspace", "travel", "banking", "slack")
    assert all(len(v) == 64 for v in (ident.record_digest, ident.tool_definitions_sha256, ident.lock_sha256,
                                      ident.default_system_prompt_sha256))
    assert ident.lock_source in ("marker", "project_lock")


def test_lock_digest_sources(tmp_path):
    import hashlib
    import json

    env = tmp_path / "envs" / "agentdojo-12345678"
    env.mkdir(parents=True)
    with pytest.raises(LockDigestUnavailable):
        lock_digest(env)
    (env / "AGENTPROV_ENV.json").write_text(json.dumps({"lock_sha256": "a" * 64}))
    assert lock_digest(env) == ("a" * 64, "marker")
    (env / "AGENTPROV_ENV.json").write_text(json.dumps({"lock_sha256": "nope"}))
    with pytest.raises(LockDigestUnavailable):
        lock_digest(env)
    venv = tmp_path / "proj" / ".venv"
    venv.mkdir(parents=True)
    (tmp_path / "proj" / "uv.lock").write_bytes(b"lock")
    assert lock_digest(venv) == (hashlib.sha256(b"lock").hexdigest(), "project_lock")
