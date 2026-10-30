"""The AgentDyn backend (D-680..D-688; ``docs/reports/agentdyn-backend/design.md``): the AgentDojo-family runner of
``runner.AgentDojoBackend`` over AgentDyn's own ``agentdojo`` 0.1.35 at ``5353cf7615b135cace8d07c8f12dac53a16b6db3``
(``backends/agentdyn``; https://github.com/SaFo-Lab/AgentDyn).

Everything that records is shared and unchanged, as for AutoDojo (D.11.4): the recording transport and ``LlmSpan``
brackets around AgentDyn's **unmodified** ``OpenAILLM`` (whose ``query`` is AST-identical to 0.1.35), the pass
recorder, the executor mirror (``ToolsExecutor.query`` is AST-identical to 0.1.35, so the guard passes), the recording
runtime and the stock runner functions inside ``OutputLogger``. What differs:

* **Identity.** ``backend.id = "agentdyn"`` in ``session.start``; ``identity()`` refuses an installed ``agentdojo``
  whose PEP 610 source is not the pinned AgentDyn commit, and reports the extra guarded names
  ``identity.AGENTDYN_GUARDED_NAMES``. The benchmark (``cell.benchmark``, the ``bench`` actor) stays ``agentdojo`` as
  for AutoDojo; AgentDyn is told apart by ``identity.benchmark.{repo, commit}``, and the live profile labels the
  AgentDyn suites (``agentdyn.suite_benchmark@1``).
* **Suite set.** What AgentDyn registers for the benchmark version (v1.2.2: the four AgentDojo suites and
  ``shopping``, ``github``, ``dailylife``). The default system message is AgentDyn's (AgentDojo's plus "Complete all
  tasks automatically without requesting user confirmation."; design F-1); the harness never replaces it.
* **Instrumentation.** No ``agentdojo.temperature_not_transmitted@1``: AgentDyn's ``chat_completion_request`` sends
  ``temperature`` whenever it is not ``None``, except for models whose name starts ``o1``/``o3``/``o4``/``gpt-5``
  (``_supports_temperature``). Instead its stock request and run behaviour is declared (all ``harness_policy``, design
  §4.2): ``agentdyn.temperature_transmitted@1``, ``agentdyn.system_role_for_qwen3_max@1`` (only for that model),
  ``agentdyn.malformed_tool_calls_dropped@1``, ``agentdyn.json_decode_error_imposes_outcome@1`` and
  ``agentdyn.model_output_last_assistant@1``.
* **Refusals.** ``llm_element = "gateway_compat"`` (the port binds to private helpers whose AgentDyn versions differ;
  AD-09) and every defence (``execute`` refuses defended pipelines in v0.1; AgentDyn's ``camel``, ``drift``,
  ``progent``, ``piguard_detector`` and ``prompt_guard_2_detector`` are named here with their reason). AgentDyn has no
  attack beyond the stock registry, so no attack is refused and none needs a run option.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agentprov_backend.attacks import UnsupportedConfiguration
from agentprov_backend.identity import BenchmarkIdentity
from agentprov_backend.runner import (
    DECLARED_SEMANTICS,
    AgentConfig,
    AgentDojoBackend,
    BuiltLLM,
    CellSpec,
    _item,
    instrumentation_items,
)

__all__ = [
    "AGENTDYN_COMMIT",
    "AGENTDYN_REPO",
    "AgentDynBackend",
    "REFUSED_DEFENCES",
    "temperature_transmitted",
]

AGENTDYN_REPO = "https://github.com/SaFo-Lab/AgentDyn"
AGENTDYN_COMMIT = "5353cf7615b135cace8d07c8f12dac53a16b6db3"
#: ``openai_llm._supports_temperature`` at the pin: these model-name prefixes (lower-cased) get no temperature.
NO_TEMPERATURE_PREFIXES = ("o1", "o3", "o4", "gpt-5")
#: ``openai_llm._message_to_openai`` at the pin: this model name gets the system message with role ``system``.
SYSTEM_ROLE_MODEL = "qwen3-max"

_DEFENCE_REASON = ("replaces or wraps pipeline components and needs defence-specific capture; defended pipelines are "
                   "refused in v0.1")
REFUSED_DEFENCES: Mapping[str, str] = {
    "camel": f"AgentDyn's 'camel' defence {_DEFENCE_REASON} (it also adds the vendored CaMeL tree to sys.path)",
    "drift": f"AgentDyn's 'drift' defence {_DEFENCE_REASON} (it also adds the vendored DRIFT tree to sys.path)",
    "progent": f"AgentDyn's 'progent' defence {_DEFENCE_REASON} (it bootstraps a policy from a vendored secagent)",
    "piguard_detector": f"the 'piguard_detector' defence {_DEFENCE_REASON} (it loads model weights)",
    "prompt_guard_2_detector": f"the 'prompt_guard_2_detector' defence {_DEFENCE_REASON} (it loads model weights)",
}

AGENTDYN_DECLARED_SEMANTICS: Mapping[str, str] = {
    **DECLARED_SEMANTICS,
    "benchmark": "agentdojo (AgentDyn 5353cf76)",
    "run_error": "a caught provider error or json.JSONDecodeError imposes utility = false, security = true (AgentDyn "
                 "benchmark.py); no extra log key",
}


def temperature_transmitted(model: str, temperature: Any) -> Any:
    """The temperature AgentDyn's ``chat_completion_request`` puts on the wire for ``model`` (``None``: not sent)."""
    if temperature is None or model.lower().startswith(NO_TEMPERATURE_PREFIXES):
        return None
    return temperature


class AgentDynBackend(AgentDojoBackend):
    """The ``Backend`` of D.10.1 for AgentDyn (see the module docstring)."""

    backend_id = "agentdyn"
    declared_semantics = AGENTDYN_DECLARED_SEMANTICS

    def identity(self) -> BenchmarkIdentity:
        if self._identity is None:
            from agentprov_backend.identity import AGENTDYN_GUARDED_NAMES, benchmark_identity

            ident = benchmark_identity(self.benchmark_version, extra_guarded=AGENTDYN_GUARDED_NAMES)
            src = ident.source
            if (src.get("kind") != "git" or src.get("repo") != AGENTDYN_REPO or src.get("commit") != AGENTDYN_COMMIT
                    or "subdirectory" in src):
                raise UnsupportedConfiguration(
                    f"the installed agentdojo is not AgentDyn at {AGENTDYN_COMMIT} (PEP 610 source "
                    f"{src.get('kind')!r}, commit {str(src.get('commit'))[:12]!r})")
            self._identity = ident
        return self._identity

    def plan(self, spec: Mapping[str, Any]) -> Any:
        plan = super().plan(spec)
        for cell in plan.cells:
            self.check_cell(cell)
        self.check_agent(plan.agent)
        return plan

    def check_agent(self, agent: AgentConfig) -> None:
        if agent.llm_element != "native":
            raise UnsupportedConfiguration(
                "llm_element 'gateway_compat' is refused for AgentDyn: the port binds to private OpenAI helpers whose "
                "AgentDyn versions differ; AgentDyn's own element is recorded at transport level (AD-09)")

    def check_cell(self, cell: CellSpec) -> None:
        if cell.defence in REFUSED_DEFENCES:
            raise UnsupportedConfiguration(REFUSED_DEFENCES[cell.defence])

    def instrumentation(self, agent: AgentConfig, built: BuiltLLM | None, backend_config: Mapping[str, Any], *,
                        mirror_source_sha256: str | None, environ: Mapping[str, str]) -> list[dict[str, Any]]:
        items = [i for i in instrumentation_items(agent, built, backend_config,
                                                  mirror_source_sha256=mirror_source_sha256)
                 if i["id"] != "agentdojo.temperature_not_transmitted@1"]
        model = agent.model_requested
        for item in items:
            if item["id"] == "agentdojo.http_backoff@1":
                item["detail"] = ("native element: the SDK's own retries (max_retries=2) and AgentDyn's tenacity retry "
                                  "of chat_completion_request (3 attempts) are stock; every wire attempt is recorded")
        configured = built.temperature if built is not None else agent.params.get("temperature", 0.0)
        out = list(items)
        out.append(_item("agentdyn.temperature_transmitted@1", "harness_policy",
                         params={"configured": agent.params.get("temperature"),
                                 "transmitted": temperature_transmitted(model, configured),
                                 "not_sent_for_prefixes": list(NO_TEMPERATURE_PREFIXES)},
                         detail="AgentDyn sends `temperature` when it is not None (so 0.0 is transmitted; stock "
                                "0.1.35 omits a falsy temperature), except for models whose name starts with one of "
                                "the listed prefixes"))
        if model == SYSTEM_ROLE_MODEL:
            out.append(_item("agentdyn.system_role_for_qwen3_max@1", "harness_policy",
                             detail="AgentDyn sends the system message with role `system` for the model qwen3-max "
                                    "(role `developer` otherwise, as stock 0.1.35)"))
        out.append(_item("agentdyn.malformed_tool_calls_dropped@1", "harness_policy",
                         detail="AgentDyn's _openai_to_assistant_message drops a tool call whose conversion fails "
                                "(for example arguments that are not JSON): the wire reply lists it, the agent's "
                                "assistant message does not, and it is never dispatched"))
        out.append(_item("agentdyn.json_decode_error_imposes_outcome@1", "harness_policy",
                         detail="AgentDyn's runner catches json.JSONDecodeError like a provider error: utility = "
                                "false, security = true, logged in the native log's `error`"))
        out.append(_item("agentdyn.model_output_last_assistant@1", "harness_policy",
                         detail="AgentDyn's model_output_from_messages returns the last assistant message anywhere in "
                                "the conversation (stock 0.1.35 requires the last message to be the assistant's)"))
        return out
