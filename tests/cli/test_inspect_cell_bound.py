"""D-740: the per-cell call bound of an Inspect cell under the D-725 caps (``docs/reports/inspect-harness/cell-bound.md``,
option (a), user-approved 2026-10-22).

* ``_inspect_cell_calls`` computes ``n x E x ((M - 1) x (1 + a) + j) x (1 + K)`` from T0's own plan document and refuses
  (``cli.refused.api_caps``) a task without a recorded bound, an environment whose task code differs from the code the
  bound was derived from, a judge on another model than the agent, and a plan without the limits it needs.
* ``Budget`` reserves and records that bound instead of the AgentDojo constant (AgentDojo runs are unchanged).
* Under caps an Inspect plan defaults to ``cell_size = 1``.
* T0's retry constant equals the worker's (the backend's own test re-derives ``j`` from the pinned grading code).
* D-741: a real-model Inspect run needs an OpenAI-chat endpoint (the worker has no other provider).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentprov.cli.live import envs
from agentprov.cli.live.policy import CELL_CALL_BOUND, Budget, Caps, LogBilling
from agentprov.cli.run import LiveRefused, _check_inspect_endpoint, _inspect_cell_calls, _inspect_document

REPO = Path(__file__).resolve().parents[2]
DIGEST = envs.BACKEND_KINDS["inspect-agentharm"].call_bounds["inspect_evals/agentharm"].task_files_sha256
IDENTITY = SimpleNamespace(task_files={"inspect_evals/agentharm": DIGEST})
AGENT = {"model_requested": "gpt-4o-mini", "endpoint": "openai"}


def _doc(*, task="inspect_evals/agentharm", message_limit=10, epochs=None, cell_size=1, judge="gpt-4o-mini"):
    inspect = {"task": task, "limits": {"message_limit": message_limit, "token_limit": 60000, "time_limit_s": 600}}
    if epochs is not None:
        inspect["epochs"] = epochs
    if cell_size is not None:
        inspect["cell_size"] = cell_size
    return {"inspect": inspect, "judges": {"refusal_judge": {"model_requested": judge},
                                            "semantic_judge": {"model_requested": "gpt-4o-mini"}}}


@pytest.mark.parametrize(("message_limit", "epochs", "cell_size", "calls"), [
    (10, None, 1, 42), (20, None, 1, 82), (10, None, 4, 168), (20, None, 4, 328), (10, 2, 1, 84),
])
def test_the_bound_follows_the_formula(message_limit, epochs, cell_size, calls):
    """The worked figures of cell-bound.md section 4 (K = 1): option (a) is M = 10, n = 1, 42 calls."""
    doc = _doc(message_limit=message_limit, epochs=epochs, cell_size=cell_size)
    assert _inspect_cell_calls("inspect-agentharm", doc, AGENT, IDENTITY) == calls
    assert _inspect_cell_calls("inspect-agentharm", {**doc, "inspect": {**doc["inspect"],
                                                                         "task": "inspect_evals/agentharm_benign"}},
                               AGENT, IDENTITY) == calls


@pytest.mark.parametrize(("doc", "identity", "why"), [
    (_doc(task="inspect_evals/other"), IDENTITY, "no call bound is recorded"),
    (_doc(), SimpleNamespace(task_files={"inspect_evals/agentharm": "sha256:" + "0" * 64}), "not the code"),
    (_doc(judge="gpt-4o"), IDENTITY, "every judge must use the agent's model"),
    (_doc(message_limit=None), IDENTITY, "no message_limit"),
    (_doc(cell_size=None), IDENTITY, "no cell_size"),
    (_doc(epochs=0), IDENTITY, "no epochs"),
])
def test_a_cell_the_caps_cannot_bound_is_refused(doc, identity, why):
    with pytest.raises(LiveRefused) as refused:
        _inspect_cell_calls("inspect-agentharm", doc, AGENT, identity)
    assert refused.value.code == "cli.refused.api_caps" and why in str(refused.value)


def test_the_budget_reserves_and_records_the_cell_bound():
    caps = Caps(max_calls=200, max_cost_usd=0.5, price_in=0.15, price_out=0.6)
    agentdojo = Budget(caps)
    assert agentdojo.cell_bound()[0] == CELL_CALL_BOUND and agentdojo.record()["cell_call_bound"] == CELL_CALL_BOUND
    inspect = Budget(caps, cell_calls=42)
    calls, usd = inspect.cell_bound()
    assert calls == 42 and round(usd, 3) == 0.305 and inspect.record()["cell_call_bound"] == 42
    assert inspect.refusal(0) is None  # $0.305 fits the $0.50 probe cap; a second in-flight cell would not
    assert inspect.refusal(1) is not None and "cap_reached" in inspect.refusal(1)
    inspect.charge(LogBilling(billed_calls=43, input_tokens=10, output_tokens=10), label="cell-1")
    assert "cap_bound_exceeded" in (inspect.refusal(0) or "")


def _args(**kw):
    base = dict(task="inspect_evals/agentharm", task_param=None, samples="limit:4", epochs=None, message_limit=10,
                token_limit=60000, time_limit=600, max_connections=None, cell_size=None, judge=None, plan=None,
                max_calls=None, max_cost_usd=None, suite=None, benchmark_version=None, user_tasks=None, attack=None,
                injection_tasks=None, benign=None, defence=None, spec=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_under_caps_an_inspect_plan_defaults_to_one_sample_per_cell(tmp_path):
    assert "cell_size" not in _inspect_document(_args(), AGENT, "inspect-agentharm")["inspect"]
    assert _inspect_document(_args(max_cost_usd=0.5), AGENT, "inspect-agentharm")["inspect"]["cell_size"] == 1
    assert _inspect_document(_args(max_calls=200, cell_size=3), AGENT, "inspect-agentharm")["inspect"]["cell_size"] == 3
    plan = tmp_path / "plan.toml"
    plan.write_text('[inspect]\ntask = "inspect_evals/agentharm"\n')
    from_file = _inspect_document(_args(plan=str(plan), task=None, samples=None, message_limit=None, token_limit=None,
                                        time_limit=None, max_calls=200), AGENT, "inspect-agentharm")
    assert from_file["inspect"]["cell_size"] == 1


def test_t0_and_the_worker_agree_on_the_retries():
    models = (REPO / "backends/inspect/src/agentprov_backend_inspect/models.py").read_text(encoding="utf-8")
    (value,) = re.findall(r"^MAX_RETRIES = (\d+)$", models, re.MULTILINE)
    assert int(value) == envs.INSPECT_MAX_RETRIES == 1
    worker = (REPO / "backends/inspect/src/agentprov_backend_inspect/worker.py").read_text(encoding="utf-8")
    assert '"inspect.harness_settings@2"' in worker and "max_retries=MAX_RETRIES" in worker


def test_an_inspect_backend_needs_an_openai_chat_endpoint():
    """D-741: the worker speaks only Inspect's OpenAI-compatible provider; AgentDojo backends keep both providers."""
    _check_inspect_endpoint("inspect-agentharm", {**AGENT, "provider": "openai_compatible"})
    _check_inspect_endpoint("agentdojo", {**AGENT, "provider": "anthropic"})
    for provider in ("anthropic", None):
        with pytest.raises(LiveRefused, match="OpenAI chat format") as exc:
            _check_inspect_endpoint("inspect-agentharm", {**AGENT, "provider": provider})
        assert exc.value.code == "cli.refused.endpoint"
