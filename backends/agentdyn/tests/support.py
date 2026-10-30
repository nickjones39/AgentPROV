"""Helpers and scripted scenarios for the AgentDyn backend tests (no ``agentprov`` import; Python 3.12 backend
environment, AgentDyn installed as ``agentdojo``). The tool names and task ids are AgentDyn suite content at the pin;
nothing here is read from AgentDyn's repository at test time."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov_backend.agentdyn import AgentDynBackend
from agentprov_backend.runner import AgentConfig, CaptureSession, CellResult, CellSpec, build_redactor
from agentprov_backend.testing import ScriptedTransport, step_from_dict

PIN = "5353cf7615b135cace8d07c8f12dac53a16b6db3"
REPO = "https://github.com/SaFo-Lab/AgentDyn"
#: AgentDyn's default system message (AgentDojo's plus the auto-complete line), as the source profile pins it.
SYSTEM_PROMPT_SHA256 = "21a1c00db164a6d5d9d456be30eea3ed23bc11e6a89af0f56b8098d1f9ee3e36"
#: AgentDojo's default (stock 0.1.35 and the AutoDojo fork; design F-1).
AGENTDOJO_SYSTEM_PROMPT_SHA256 = "a021a92b114c523250d0e52b18adc0aa7b41db7c7628b579b2b8db1df9361837"
MODEL = "scripted-fake"

_BACKEND: AgentDynBackend | None = None


def backend() -> AgentDynBackend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = AgentDynBackend()
    return _BACKEND


def cell(suite: str, user_task: str, *, attack: str | None = None, injection: str | None = None,
         kind: str = "user_task", attack_params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"cell_key": f"{suite}/{user_task}/{attack or 'none'}/{injection or 'none'}", "suite": suite,
            "user_task_id": user_task, "injection_task_id": injection, "attack": attack, "defence": None,
            "kind": kind, "attack_params": dict(attack_params or {})}


def agent(*, model: str = MODEL, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"model_requested": model, "provider": "openai_compatible", "endpoint": "scripted", "api_key_env": None,
            "params": dict(params or {}), "llm_element": "native", "transport": "scripted", "script": "script.json",
            "base_url": None}


#: shopping's send_email stamps datetime.now() into the stored email (R-9b-1; as phase 9b's AutoDojo test).
SEND_EMAIL = {"reply": "tool_calls", "calls": [{"name": "send_email", "args": {
    "recipients": ["someone@example.com"], "subject": "Order", "body": "Hello"}, "id": "call_1"}]}
DONE = {"reply": "text", "content": "Done."}
#: one tool call whose arguments are not JSON, with text content: AgentDyn drops the call (design F-5) and the turn
#: ends on the text.
MALFORMED_WITH_TEXT = {"reply": "tool_calls", "content": "Checking.",
                       "calls": [{"name": "send_email", "arguments": "{\"recipients\": [", "id": "call_1"}]}


@dataclass(frozen=True)
class Scenario:
    name: str
    cell: Mapping[str, Any]
    agent: Mapping[str, Any]
    steps: tuple[Mapping[str, Any], ...]
    expect_status: str = "complete"


SCENARIOS: dict[str, Scenario] = {s.name: s for s in [
    # S1..S4 of the design note (section 6)
    Scenario("s1_shopping_benign", cell("shopping", "user_task_0"), agent(), (SEND_EMAIL, DONE)),
    Scenario("s2_github_important_instructions",
             cell("github", "user_task_0", attack="important_instructions", injection="injection_task_0",
                  kind="attacked", attack_params={"model_display_name": "Scripted Model"}),
             agent(), (DONE,)),
    Scenario("s3_workspace_benign", cell("workspace", "user_task_0"), agent(), (DONE,)),
    Scenario("s4_dailylife_malformed_call_dropped", cell("dailylife", "user_task_0"), agent(), (MALFORMED_WITH_TEXT,)),
]}


@dataclass
class Run:
    dir: Path
    session: CaptureSession
    result: CellResult
    transport: ScriptedTransport
    events: list[dict[str, Any]] = field(default_factory=list)

    def of(self, type_: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["type"] == type_]

    def blob(self, ref: Mapping[str, Any]) -> bytes:
        h = ref["$blob"].split(":", 1)[1]
        return (self.dir / "raw" / "blobs" / "sha256" / h[:2] / h).read_bytes()

    def json_blob(self, ref: Mapping[str, Any]) -> Any:
        return json.loads(self.blob(ref))

    def items(self) -> dict[str, dict[str, Any]]:
        return {i["id"]: i for i in self.of("instrumentation")[0]["data"]["items"]}

    def native(self) -> dict[str, Any]:
        return json.loads((self.dir / self.session.native_label).read_bytes())

    def judgements(self) -> dict[str, tuple[Any, str]]:
        (out,) = self.of("outcome")
        return {j["name"]: (j["value"], j["origin"]) for j in out["data"]["judgements"]}


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def run_cell(tmp_path: Path, cell_: Mapping[str, Any] | CellSpec, agent_: Mapping[str, Any] | AgentConfig,
             steps: Sequence[Any], *, backend_config: Mapping[str, Any] | None = None) -> Run:
    spec = cell_ if isinstance(cell_, CellSpec) else CellSpec.from_json(cell_)
    cfg = agent_ if isinstance(agent_, AgentConfig) else AgentConfig.from_json(agent_)
    script = [s if not isinstance(s, Mapping) else step_from_dict(s) for s in steps]
    tr = ScriptedTransport(script, model=cfg.model_requested)
    d = tmp_path / "session"
    d.mkdir(parents=True, exist_ok=True)
    session = CaptureSession(d, redactor=build_redactor({}, cfg))
    result = backend().execute(spec, cfg, session, backend_config=backend_config or {}, inner_transport=tr,
                               environ={}, plan_sha256="0" * 64)
    return Run(d, session, result, tr, read_events(session.capture_path))


def run_scenario(tmp_path: Path, name: str) -> Run:
    sc = SCENARIOS[name]
    return run_cell(tmp_path, sc.cell, sc.agent, sc.steps)
