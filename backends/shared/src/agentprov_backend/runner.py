"""The AgentDojo-family cell runner (D.10.1, D.10.5; the ``generate.py`` orchestration of the baseline, minus the
hidden hacks).

Contents:

* the harness-internal dataclasses of D.10.1 (``CellSpec``, ``AgentConfig``, ``RunPlan``, ``CellResult``;
  ``BenchmarkIdentity`` lives in ``identity``) and ``CaptureSession`` (re-exported from ``session``);
* run plans (format ``agentprov-run-plan/0.1``): ``load_plan`` / ``expand_plan`` expand a plan into cells and compute
  ``plan_sha256`` (the JCS digest of the expanded plan, not of the file bytes);
* ``build_llm`` (the stock ``OpenAILLM`` under ``native``, ``GatewayLLM`` under ``gateway_compat``; both on an SDK
  client whose HTTP transport is the recording transport over the real or the scripted transport; for provider
  ``anthropic`` the declared port of the stock ``AnthropicLLM`` (``_anthropic_llm``) on an ``AsyncAnthropic`` client
  over the async recording transport, D-656);
* ``build_instrumented_pipeline`` (the undefended pipeline; refuses a defence and non-YAML tool output, OB-8); a
  defended cell is built by ``defences.build_defended_pipeline`` from the registry entry (D-670);
* ``SuiteRunProxy`` (injects ``runtime_class`` into ``run_task_with_pipeline``; the stock runner does not forward it,
  ``benchmark.py:117-119``);
* ``AgentDojoBackend``: ``identity``, ``plan`` and ``execute``, which drives one cell through the **stock**
  ``benchmark.run_task_with(out)_injection_tasks`` inside ``OutputLogger(logdir=<session>/raw/native-tmp)``, so the
  stock error imposition, DoS rule and TraceLogger run unchanged and the native JSON is byte-for-byte the stock
  output. Every failure seals the session ``errored`` and keeps what was written.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import agentprov_backend
from agentprov_backend._jsonval import encode_value
from agentprov_backend.attacks import UnsupportedConfiguration
from agentprov_backend.identity import BenchmarkIdentity
from agentprov_backend.session import CaptureSession, uuid7

__all__ = [
    "PLAN_FORMAT",
    "PROBE_KEY",
    "PROBE_PROMPT",
    "AgentConfig",
    "AgentDojoBackend",
    "BenchmarkIdentity",
    "CaptureSession",
    "CellResult",
    "CellSpec",
    "RunPlan",
    "SuiteRunProxy",
    "UnsupportedConfiguration",
    "build_instrumented_pipeline",
    "build_llm",
    "cell_key",
    "config_sha256",
    "enumerate_cells",
    "expand_plan",
    "load_plan",
    "plan_sha256",
    "check_anthropic_params",
    "messages_roles_verdict",
    "roles_verdict",
    "run_probe",
    "build_redactor",
    "catalogue",
    "select_backend",
    "uuid7",
]

PLAN_FORMAT = "agentprov-run-plan/0.1"
CATALOGUE_FORMAT = "agentprov-backend-catalogue/0.1"
BACKEND_ID = "agentdojo"
DEFAULT_BENCHMARK_VERSION = "v1.2.2"
SCRIPTED_BASE_URL = "https://scripted.invalid/v1"
#: The Anthropic SDK appends ``/v1/messages`` itself, so its scripted base URL has no path (D-656).
ANTHROPIC_SCRIPTED_BASE_URL = "https://scripted.invalid"
PROVIDERS = ("openai_compatible", "anthropic")

#: D-656 (Q3, user decision 2026-10-22): an Anthropic run states its ``max_tokens`` (``max_tokens_mode = "explicit"``)
#: or takes the harness default (``"harness_default"``, exactly this value), declared as a ``harness_policy`` item.
#: AgentDojo's own default (1024) is never used silently: thinking counts against it, and the stock element drops tool
#: calls unless ``stop_reason == "tool_use"``.
ANTHROPIC_HARNESS_MAX_TOKENS = 16000
ANTHROPIC_STOCK_MAX_TOKENS = 1024
MAX_TOKENS_MODES = ("explicit", "harness_default")
#: The parameters the stock ``AnthropicLLM`` constructor takes (plus the mode); anything else is refused.
ANTHROPIC_PARAMS = frozenset({"max_tokens", "max_tokens_mode", "temperature", "thinking_budget_tokens"})
#: Credential sources the ``anthropic`` SDK reads by itself besides the key it is given. None may reach the worker
#: (G.6.3 passes only the registry key variable); ``build_llm`` refuses if one is set, so the wire carries the key
#: the run declared and nothing else.
ANTHROPIC_FOREIGN_CREDENTIALS = (
    "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_CONFIG_DIR", "ANTHROPIC_FEDERATION_RULE_ID",
    "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE", "ANTHROPIC_ORGANIZATION_ID",
    "ANTHROPIC_SERVICE_ACCOUNT_ID", "ANTHROPIC_WORKSPACE_ID",
)  # fmt: skip

CellKind = Literal["user_task", "injection_task_as_user_task", "attacked", "dos"]


# ---------------------------------------------------------------------------------------------- dataclasses (D.10.1)


@dataclass(frozen=True)
class CellSpec:
    cell_key: str
    suite: str
    user_task_id: str
    injection_task_id: str | None
    attack: str | None
    defence: str | None
    kind: CellKind
    attack_params: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["attack_params"] = dict(self.attack_params)
        return d

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> CellSpec:
        _require(isinstance(d, Mapping), "cell must be an object")
        for k in ("cell_key", "suite", "user_task_id", "kind"):
            _require(isinstance(d.get(k), str) and d[k], f"cell.{k} must be a non-empty string")
        _require(d["kind"] in ("user_task", "injection_task_as_user_task", "attacked", "dos"), "cell.kind is unknown")
        for k in ("injection_task_id", "attack", "defence"):
            _require(d.get(k) is None or isinstance(d.get(k), str), f"cell.{k} must be a string or null")
        params = d.get("attack_params") or {}
        _require(isinstance(params, Mapping), "cell.attack_params must be an object")
        unknown = set(d) - {"cell_key", "suite", "user_task_id", "injection_task_id", "attack", "defence", "kind",
                            "attack_params"}
        _require(not unknown, f"cell has unknown members {sorted(unknown)}")
        return cls(d["cell_key"], d["suite"], d["user_task_id"], d.get("injection_task_id"), d.get("attack"),
                   d.get("defence"), d["kind"], dict(params))


#: The largest T0-supplied object the worker records as is (``agent.local_model``, ``run_cell.local_model``; D-693).
NOTE_MAX_BYTES = 64 * 1024


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError):
        return NOTE_MAX_BYTES + 1


@dataclass(frozen=True)
class AgentConfig:
    model_requested: str
    provider: str = "openai_compatible"
    endpoint: str = "scripted"
    api_key_env: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    llm_element: Literal["native", "gateway_compat"] = "native"
    transport: Literal["http", "scripted"] = "http"
    script: str | None = None
    #: the resolved base URL (validated, https or loopback, no userinfo/query/fragment); default: the registry's
    base_url: str | None = None
    #: for a local endpoint, T0's observed ``agentprov-local-model/0.1`` identity record of the model (without its
    #: ``observed_at``), so it enters the plan and configuration digests (D-693); ``None`` for a remote endpoint
    local_model: Mapping[str, Any] | None = None
    #: the operator's ``--allow-lan-endpoint`` (D-698): http to a literal private address is accepted; never with a key
    allow_lan: bool = False

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["params"] = dict(self.params)
        if self.local_model is None:
            del d["local_model"]  # a remote endpoint's agent (and its digests) are unchanged by D-693
        if not self.allow_lan:
            del d["allow_lan"]  # likewise for D-698
        return d

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> AgentConfig:
        _require(isinstance(d, Mapping), "agent must be an object")
        _require(isinstance(d.get("model_requested"), str) and d["model_requested"],
                 "agent.model_requested is required (there is no default model id)")
        unknown = set(d) - {f for f in cls.__dataclass_fields__}
        _require(not unknown, f"agent has unknown members {sorted(unknown)}")
        llm_element = d.get("llm_element", "native")
        transport = d.get("transport", "http")
        _require(llm_element in ("native", "gateway_compat"), "agent.llm_element must be native or gateway_compat")
        _require(transport in ("http", "scripted"), "agent.transport must be http or scripted")
        provider = d.get("provider", "openai_compatible")
        _require(provider in PROVIDERS, f"agent.provider must be one of {list(PROVIDERS)}")
        params = d.get("params") or {}
        _require(isinstance(params, Mapping), "agent.params must be an object")
        if provider == "anthropic":
            _require(llm_element == "native", "provider anthropic runs the stock AnthropicLLM (llm_element native)")
        for k in ("endpoint", "api_key_env", "script", "base_url"):
            _require(d.get(k) is None or isinstance(d.get(k), str), f"agent.{k} must be a string")
        if transport == "scripted":
            _require(isinstance(d.get("script"), str), "a scripted transport needs agent.script")
        local_model = d.get("local_model")
        _require(local_model is None or (isinstance(local_model, Mapping) and _json_size(local_model) <= NOTE_MAX_BYTES),
                 "agent.local_model must be an object (at most 64 KiB as JSON)")
        allow_lan = d.get("allow_lan", False)
        _require(isinstance(allow_lan, bool), "agent.allow_lan must be a boolean")
        _require(not (allow_lan and d.get("api_key_env")), "a LAN endpoint is keyless: no key is ever sent off the machine")
        return cls(d["model_requested"], provider, d.get("endpoint") or "scripted", d.get("api_key_env"),
                   dict(params), llm_element, transport, d.get("script"), d.get("base_url"),
                   dict(local_model) if local_model is not None else None, allow_lan)


@dataclass(frozen=True)
class RunPlan:
    plan_sha256: str
    cells: tuple[CellSpec, ...]
    agent: AgentConfig
    backend_config: Mapping[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {"format": PLAN_FORMAT, "plan_sha256": self.plan_sha256, "cells": [c.to_json() for c in self.cells],
                "agent": self.agent.to_json(), "backend_config": dict(self.backend_config)}


@dataclass(frozen=True)
class CellResult:
    status: Literal["complete", "incomplete", "errored", "aborted"]
    outcome: Mapping[str, Any] | None
    native_artefacts: tuple[str, ...]
    capture_head: str | None = None


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise UnsupportedConfiguration(message)


def _jcs_sha256(value: Any) -> str:
    import rfc8785

    return hashlib.sha256(rfc8785.dumps(encode_value(value))).hexdigest()


# ---------------------------------------------------------------------------------------------- run plans


def cell_key(suite: str, user_task_id: str, attack: str | None, injection_task_id: str | None) -> str:
    return f"{suite}/{user_task_id}/{attack or 'none'}/{injection_task_id or 'none'}"


def _task_order(task_id: str) -> tuple[str, int, str]:
    m = re.fullmatch(r"(.*?)(\d+)", task_id)
    return (m.group(1), int(m.group(2)), task_id) if m else (task_id, -1, task_id)


def _select(spec: Any, available: Sequence[str], what: str) -> list[str]:
    ordered = sorted(available, key=_task_order)
    if spec is None or spec == "all":
        return ordered
    if isinstance(spec, list):
        _require(all(isinstance(x, str) for x in spec), f"{what} must be task ids")
        missing = [x for x in spec if x not in available]
        _require(not missing, f"unknown {what}: {missing}")
        return list(spec)
    _require(isinstance(spec, str), f"{what} must be 'all', a list of ids or an index-range string")
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part in available:
            out.append(part)
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        _require(m is not None, f"bad {what} selector {part!r}")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        _require(lo <= hi < len(ordered), f"{what} index range {part!r} is out of bounds")
        out.extend(ordered[lo:hi + 1])
    return out


def enumerate_cells(
    benchmark_version: str,
    suites: Sequence[str],
    *,
    user_tasks: Any = "all",
    injection_tasks: Any = "all",
    attacks: Sequence[str] = (),
    benign: str = "include",
    defence: str | None = None,
    injection_tasks_as_user_tasks: bool = False,
    attack_params: Mapping[str, Any] | None = None,
) -> list[CellSpec]:
    """Expand a selection into cells, in a fixed order: per suite (as given), the injection tasks run as user tasks
    (when asked), the benign cells, then per attack (as given), per user task, per injection task (one cell per user
    task for a DoS attack, with the suite's first injection task, as the stock runner does, ``benchmark.py:73-75``)."""
    from agentdojo.attacks.attack_registry import ATTACKS
    from agentdojo.task_suite.load_suites import _SUITES

    _require(benchmark_version in _SUITES, f"unknown benchmark version {benchmark_version!r}")
    _require(benign in ("include", "exclude", "only"), "benign must be include, exclude or only")
    defence = None if defence in (None, "none") else defence
    available_suites = _SUITES[benchmark_version]
    params = dict(attack_params or {})
    cells: list[CellSpec] = []
    for suite_name in suites:
        _require(suite_name in available_suites, f"unknown suite {suite_name!r} for {benchmark_version}")
        suite = available_suites[suite_name]
        uts = _select(user_tasks, list(suite.user_tasks), "user_tasks")
        its = _select(injection_tasks, list(suite.injection_tasks), "injection_tasks")
        if injection_tasks_as_user_tasks:
            for it in its:
                cells.append(CellSpec(cell_key(suite_name, it, None, None), suite_name, it, None, None, defence,
                                      "injection_task_as_user_task", {}))
        if benign in ("include", "only"):
            for ut in uts:
                cells.append(CellSpec(cell_key(suite_name, ut, None, None), suite_name, ut, None, None, defence,
                                      "user_task", {}))
        if benign == "only":
            continue
        for attack in attacks:
            _require(attack in ATTACKS, f"unknown attack {attack!r}")
            if ATTACKS[attack].is_dos_attack:
                first = next(iter(suite.injection_tasks))
                for ut in uts:
                    cells.append(CellSpec(cell_key(suite_name, ut, attack, first), suite_name, ut, first, attack,
                                          defence, "dos", params))
                continue
            for ut in uts:
                for it in its:
                    cells.append(CellSpec(cell_key(suite_name, ut, attack, it), suite_name, ut, it, attack, defence,
                                          "attacked", params))
    return cells


def _tool_definition_chars(suite: Any) -> int:
    """The character count of a suite's tool definitions as JSON (``identity.tool_definitions``' form): what every
    model call sends besides the messages. A count only: the estimate (D-652, D-653) adds it to each call's input."""
    tools = [{"name": t.name, "description": t.description, "parameters": t.parameters.model_json_schema()}
             for t in suite.tools]
    return len(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def catalogue(benchmark_version: str, *, refused_attacks: Mapping[str, str] | None = None,
              attack_needs: Mapping[str, Sequence[str]] | None = None, backend_id: str = BACKEND_ID,
              refused_defences: Mapping[str, str] | None = None) -> dict[str, Any]:
    """What a plan for ``benchmark_version`` can select (D-652): the suites with their user and injection task ids (in
    the order ``_select`` indexes them), and the attack registry's names with the DoS flag (one cell per user task,
    ``enumerate_cells``). ``refused_attacks`` (name: reason) and ``attack_needs`` (name: the run options it needs) come
    from the backend. Names only: no task text, no prompt, nothing the attacks would inject. ``defences`` lists the
    registry entries ``backend_id`` builds, with this environment's refusal reason (D-670, design §3.8)."""
    from agentprov_backend.defences import catalogue_entries

    from agentdojo.attacks.attack_registry import ATTACKS
    from agentdojo.task_suite.load_suites import _SUITES

    _require(benchmark_version in _SUITES, f"unknown benchmark version {benchmark_version!r}")
    refused, needs = dict(refused_attacks or {}), dict(attack_needs or {})
    suites = [
        {"name": name,
         "user_tasks": sorted((str(t) for t in suite.user_tasks), key=_task_order),
         "injection_tasks": sorted((str(t) for t in suite.injection_tasks), key=_task_order),
         "tool_definition_chars": _tool_definition_chars(suite)}
        for name, suite in _SUITES[benchmark_version].items()
    ]  # fmt: skip
    attacks = [
        {"name": str(name), "dos": bool(getattr(cls, "is_dos_attack", False)), "refused": refused.get(name),
         "needs": list(needs.get(name, ()))}
        for name, cls in sorted(ATTACKS.items())
    ]  # fmt: skip
    return {"format": CATALOGUE_FORMAT, "benchmark_version": benchmark_version,
            "benchmark_versions": sorted(str(v) for v in _SUITES), "suites": suites, "attacks": attacks,
            "defences": catalogue_entries(backend_id, refused=refused_defences)}


def plan_sha256(cells: Sequence[CellSpec], agent: AgentConfig, backend_config: Mapping[str, Any]) -> str:
    return _jcs_sha256({"format": PLAN_FORMAT, "cells": [c.to_json() for c in cells], "agent": agent.to_json(),
                        "backend_config": dict(backend_config)})


_PLAN_KEYS = {"format", "backend", "benchmark_version", "suites", "user_tasks", "injection_tasks", "attacks", "benign",
              "defence", "defense", "injection_tasks_as_user_tasks", "tool_output_format"}


def expand_plan(spec: Mapping[str, Any], *, backend_id: str = BACKEND_ID) -> RunPlan:
    """Expand a parsed run plan (``agentprov-run-plan/0.1``)::

        [plan]
        format = "agentprov-run-plan/0.1"      # required
        backend = "agentdojo"                  # optional; must be agentdojo here
        benchmark_version = "v1.2.2"           # default v1.2.2
        suites = ["banking"]                   # required
        user_tasks = "all"                     # "all" | ["user_task_1", ...] | "0-9,12" (indexes of the sorted list)
        injection_tasks = "all"
        attacks = ["important_instructions"]   # default [] (benign only)
        benign = "include"                     # include | exclude | only
        defence = "none"                       # or a registry id this backend builds (D-670; defences.toml)
        injection_tasks_as_user_tasks = false
        tool_output_format = "yaml"            # anything else is refused (OB-8)

        [agent]                                # AgentConfig (no secrets; api_key_env is a NAME)
        model_requested = "..."
        endpoint = "openrouter"
        api_key_env = "OPENROUTER_API_KEY"
        llm_element = "native"
        transport = "http"
        [agent.params]
        temperature = 0.0

        [attack_params]                        # recorded verbatim in each attacked cell
        model_display_name = "..."

        [backend]                              # backend_config, recorded in config_sha256
        pipeline_name = "..."                  # default: agent.model_requested
        env_snapshots = true
        repeats = 1
    """
    _require(isinstance(spec, Mapping), "a run plan is a table")
    plan = spec.get("plan")
    _require(isinstance(plan, Mapping), "a run plan needs a [plan] table")
    _require(plan.get("format") == PLAN_FORMAT, f"[plan] format must be {PLAN_FORMAT!r}")
    unknown = set(plan) - _PLAN_KEYS
    _require(not unknown, f"[plan] has unknown keys {sorted(unknown)}")
    _require(plan.get("backend", backend_id) == backend_id, f"this backend runs plans for {backend_id!r} only")
    suites = plan.get("suites")
    _require(isinstance(suites, list) and suites and all(isinstance(s, str) for s in suites),
             "[plan] suites must be a non-empty list")
    defence = plan.get("defence", plan.get("defense", "none"))
    _require(defence is None or isinstance(defence, str), "[plan] defence must be a string")
    if defence not in (None, "none"):
        from agentprov_backend.defences import resolve

        entry = resolve(defence, backend_id)
        if "*" not in entry.suites:
            outside = [s for s in suites if s not in entry.suites]
            _require(not outside, f"the defence {defence!r} runs on {list(entry.suites)} only (not {outside})")
    _require(plan.get("tool_output_format", "yaml") == "yaml", "only the YAML tool-output format is supported (OB-8)")
    attacks = plan.get("attacks", [])
    _require(isinstance(attacks, list) and all(isinstance(a, str) for a in attacks), "[plan] attacks must be a list")
    agent = AgentConfig.from_json(spec.get("agent") or {})
    attack_params = spec.get("attack_params") or {}
    _require(isinstance(attack_params, Mapping), "[attack_params] must be a table")
    backend_config = dict(spec.get("backend") or {})
    backend_config.setdefault("benchmark_version", plan.get("benchmark_version", DEFAULT_BENCHMARK_VERSION))
    cells = enumerate_cells(
        backend_config["benchmark_version"],
        suites,
        user_tasks=plan.get("user_tasks", "all"),
        injection_tasks=plan.get("injection_tasks", "all"),
        attacks=attacks,
        benign=plan.get("benign", "include"),
        defence=defence,
        injection_tasks_as_user_tasks=bool(plan.get("injection_tasks_as_user_tasks", False)),
        attack_params=attack_params,
    )
    return RunPlan(plan_sha256(cells, agent, backend_config), tuple(cells), agent, backend_config)


def load_plan(source: str | Path, *, backend: AgentDojoBackend | None = None) -> RunPlan:
    """Read a TOML run plan from a path or from TOML text and expand it (by ``backend.plan`` when given)."""
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source
    try:
        spec = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise UnsupportedConfiguration(f"run plan is not valid TOML: {exc}") from None
    return backend.plan(spec) if backend is not None else expand_plan(spec)


def config_sha256(cell: CellSpec, agent: AgentConfig, backend_config: Mapping[str, Any],
                  plan_digest: str | None, *, backend_id: str = BACKEND_ID) -> str:
    """JCS digest of the run configuration (plan digest included, secrets excluded; D.10.2)."""
    return _jcs_sha256({"backend": {"id": backend_id, "version": agentprov_backend.__version__},
                        "cell": cell.to_json(), "agent": agent.to_json(), "backend_config": dict(backend_config),
                        "plan_sha256": plan_digest})


# ---------------------------------------------------------------------------------------------- LLM and pipeline


def build_redactor(environ: Mapping[str, str], agent: AgentConfig | None = None) -> Any:
    """The ``agentprov_capture.redact.Redactor`` of a session (C.13.5, G.6.4): the literal values of the variables the
    process holds whose names match the scrub pattern (``redact.secrets_from_environ``), plus the agent's key variable
    whatever its name; the user's home path and the host name for the non-content surfaces. A key value too short to
    be scanned is refused (C.13.10 item 11)."""
    import pwd
    import socket

    from agentprov_capture.redact import Redactor, Secret, secrets_from_environ

    secrets = secrets_from_environ(environ)
    if agent is not None and agent.api_key_env and environ.get(agent.api_key_env):
        if agent.api_key_env not in {s.name for s in secrets}:
            secrets.append(Secret(agent.api_key_env, environ[agent.api_key_env]))
    try:
        home: str | None = pwd.getpwuid(os.getuid()).pw_dir
    except (KeyError, OSError):
        home = None
    try:
        host: str | None = socket.gethostname()
    except OSError:
        host = None
    redactor = Redactor(secrets, home=home, host=host)
    if agent is not None and agent.api_key_env and agent.api_key_env in redactor.ignored:
        raise UnsupportedConfiguration("the API key value is too short to be scanned for; refusing to run")
    return redactor


def _default_http_client(transport: Any) -> Any:
    import openai

    factory = getattr(openai, "DefaultHttpx2Client", None) or openai.DefaultHttpxClient
    return factory(transport=transport)


def resolve_base_url(agent: AgentConfig) -> str:
    from agentprov_capture.endpoints import EndpointError, get_endpoint, validate_base_url

    if agent.base_url is not None:
        try:
            validate_base_url(agent.base_url, allow_lan=agent.allow_lan)
        except EndpointError as exc:
            raise UnsupportedConfiguration(str(exc)) from None
        return agent.base_url
    try:
        return get_endpoint(agent.endpoint).base_url
    except EndpointError:
        _require(agent.transport == "scripted", f"unknown endpoint {agent.endpoint!r} and no base_url")
        return ANTHROPIC_SCRIPTED_BASE_URL if agent.provider == "anthropic" else SCRIPTED_BASE_URL


def check_anthropic_params(params: Mapping[str, Any]) -> None:
    """The parameters of a provider-``anthropic`` agent (D-656): ``max_tokens`` stated (``explicit``) or the harness
    default (``harness_default``, exactly :data:`ANTHROPIC_HARNESS_MAX_TOKENS`), an optional ``temperature`` (number
    or null) and ``thinking_budget_tokens`` (integer; legacy models only). Raises ``UnsupportedConfiguration``."""
    unknown = sorted(set(params) - ANTHROPIC_PARAMS)
    if unknown:
        raise UnsupportedConfiguration(f"the stock AnthropicLLM takes no parameter {unknown[0]!r} (it sends no effort, "
                                       "top_p or seed); remove it")
    mode, value = params.get("max_tokens_mode"), params.get("max_tokens")
    if mode not in MAX_TOKENS_MODES or not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise UnsupportedConfiguration(
            "an Anthropic run needs max_tokens: state it (max_tokens_mode = explicit, max_tokens = N) or take the "
            f"harness default (max_tokens_mode = harness_default, max_tokens = {ANTHROPIC_HARNESS_MAX_TOKENS}); "
            f"AgentDojo's own {ANTHROPIC_STOCK_MAX_TOKENS} is not used silently")
    if mode == "harness_default" and value != ANTHROPIC_HARNESS_MAX_TOKENS:
        raise UnsupportedConfiguration(f"max_tokens_mode harness_default means max_tokens = {ANTHROPIC_HARNESS_MAX_TOKENS}")
    t = params.get("temperature")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float))):
        raise UnsupportedConfiguration("temperature must be a number or null")
    b = params.get("thinking_budget_tokens")
    if b is not None and (isinstance(b, bool) or not isinstance(b, int) or b < 1):
        raise UnsupportedConfiguration("thinking_budget_tokens must be a positive integer")


@dataclass
class BuiltLLM:
    element: Any
    inner_transport: Any
    base_url: str
    host: str
    temperature: Any


def build_llm(agent: AgentConfig, session: CaptureSession, *, inner_transport: Any = None,
              environ: Mapping[str, str] | None = None, sleep: Callable[[float], None] | None = None) -> BuiltLLM:
    """The LLM element for ``agent`` on an SDK client whose transport is ``RecordingTransport(inner)``.

    ``inner`` is ``inner_transport`` when given (tests), else a ``ScriptedTransport`` loaded from
    ``<session>/<agent.script>`` for ``transport = "scripted"``, else the real HTTP transport. The API key is read from
    the variable named ``agent.api_key_env``; its value is never recorded."""
    import openai
    from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
    from agentprov_capture.endpoints import validate_base_url

    from agentprov_backend.gateway import WireRecorder
    from agentprov_backend.transport import RecordingTransport, default_inner_transport

    env = os.environ if environ is None else environ
    base_url = resolve_base_url(agent)
    host = validate_base_url(base_url, allow_lan=agent.allow_lan)
    if agent.provider == "anthropic":
        return _build_anthropic_llm(agent, session, base_url, host, env, inner_transport)
    if inner_transport is None:
        if agent.transport == "scripted":
            from agentprov_backend.testing.transport import ScriptedTransport, load_script

            label = agent.script or ""
            _require(_is_label(label), "agent.script must be a relative label inside the session directory")
            inner_transport = ScriptedTransport(load_script(session.dir / label), model=agent.model_requested)
        else:
            inner_transport = default_inner_transport()
    key = env.get(agent.api_key_env) if agent.api_key_env else None
    if not key:
        from agentprov_capture.endpoints import is_private_lan_host

        _require(agent.transport == "scripted" or host in ("127.0.0.1", "::1", "localhost")
                 or (agent.allow_lan and is_private_lan_host(host)), "the endpoint's API key variable is not set")
        key = "scripted-no-key" if agent.transport == "scripted" else "EMPTY"
    endpoint_entry: Any = None
    try:
        from agentprov_capture.endpoints import get_endpoint

        endpoint_entry = get_endpoint(agent.endpoint)
    except Exception:  # noqa: BLE001 - scripted or custom endpoint: the base allowlist only
        endpoint_entry = None
    recorder = WireRecorder(session, configured_params=agent.params, endpoint=endpoint_entry)
    http_client = _default_http_client(RecordingTransport(inner_transport, recorder))
    params = dict(agent.params)
    temperature = params.get("temperature", 0.0)
    effort = params.get("reasoning_effort")
    if agent.llm_element == "native":
        client = openai.OpenAI(api_key=key, base_url=base_url, http_client=http_client)
        element = OpenAILLM(client, agent.model_requested, reasoning_effort=effort, temperature=temperature)
    else:
        from agentprov_backend._llm import GATEWAY_ITEMS, GatewayLLM

        settings = GatewayLLM.client_settings()
        if "timeout_s" in params:
            settings["timeout"] = float(params["timeout_s"])
        client = openai.OpenAI(api_key=key, base_url=base_url, http_client=http_client, **settings)
        kwargs: dict[str, Any] = {}
        if sleep is not None:
            kwargs["sleep"] = sleep
        element = GatewayLLM(client, agent.model_requested, base_url=base_url, effort=effort,
                             passback=bool(params.get("reasoning_passback", True)), temperature=temperature,
                             session=session, **kwargs)
        for item in GATEWAY_ITEMS:
            session.declare_observed(item, ["resampled"] if item.endswith("malformed_tool_json@1") else ["retried"])
    return BuiltLLM(element, inner_transport, base_url, host, temperature)


def _build_anthropic_llm(agent: AgentConfig, session: CaptureSession, base_url: str, host: str,
                         env: Mapping[str, str], inner_transport: Any) -> BuiltLLM:
    """AgentDojo 0.1.35's ``AnthropicLLM`` (D-656) as the declared port ``_anthropic_llm.AnthropicPortLLM`` (the locked
    SDK has no ``temperature`` parameter; user decision 2026-10-22), on an ``AsyncAnthropic`` client whose transport is
    ``AsyncRecordingTransport(inner)``. The element is async and rebuilds a *sync* client it is given without its
    ``http_client``, so it must be given the async client that already records. Only the stock constructor's
    parameters are used (``check_anthropic_params``)."""
    import anthropic

    from agentprov_backend._anthropic_llm import AnthropicPortLLM

    from agentprov_backend._http import anthropic_httpx
    from agentprov_backend.gateway import WireRecorder
    from agentprov_backend.transport import AsyncRecordingTransport, default_async_inner_transport

    params = dict(agent.params)
    check_anthropic_params(params)
    present = sorted(n for n in ANTHROPIC_FOREIGN_CREDENTIALS if os.environ.get(n) or env.get(n))
    if present:
        raise UnsupportedConfiguration(f"{present[0]} is set: the anthropic SDK would read it besides the declared "
                                       "key; it must not reach the worker")
    module = anthropic_httpx()
    if inner_transport is None:
        if agent.transport == "scripted":
            from agentprov_backend.testing.transport import ScriptedTransport, load_script

            label = agent.script or ""
            _require(_is_label(label), "agent.script must be a relative label inside the session directory")
            inner_transport = ScriptedTransport(load_script(session.dir / label), model=agent.model_requested)
        else:
            inner_transport = default_async_inner_transport(module)
    key = env.get(agent.api_key_env) if agent.api_key_env else None
    if not key:
        _require(agent.transport == "scripted", "the endpoint's API key variable is not set")
        key = "scripted-no-key"
    endpoint_entry: Any = None
    try:
        from agentprov_capture.endpoints import get_endpoint

        endpoint_entry = get_endpoint(agent.endpoint)
    except Exception:  # noqa: BLE001 - scripted or custom endpoint: the base allowlist only
        endpoint_entry = None
    recorder = WireRecorder(session, configured_params=agent.params, endpoint=endpoint_entry, api="anthropic_messages")
    http_client = anthropic.DefaultAsyncHttpxClient(
        transport=AsyncRecordingTransport(inner_transport, recorder, module=module))
    client = anthropic.AsyncAnthropic(api_key=key, base_url=base_url, http_client=http_client)
    temperature = params.get("temperature")
    element = AnthropicPortLLM(client, agent.model_requested, temperature=temperature,
                           thinking_budget_tokens=params.get("thinking_budget_tokens"), max_tokens=params["max_tokens"])
    return BuiltLLM(element, inner_transport, base_url, host, temperature)


def build_defence_client(agent: AgentConfig, backend_config: Mapping[str, Any], session: CaptureSession,
                         built: BuiltLLM, *, environ: Mapping[str, str] | None = None) -> Any:
    """The SDK client of a defence's own endpoint (D-675; ``backend_config.defence_endpoint {endpoint, api_key_env,
    base_url?}``), on the recording transport like the agent's. A scripted run reuses the agent's scripted transport,
    so one script orders every wire exchange of the cell. The key is read from the named variable; never recorded."""
    import openai
    from agentprov_capture.endpoints import validate_base_url

    from agentprov_backend.gateway import WireRecorder
    from agentprov_backend.transport import RecordingTransport, default_inner_transport

    env = os.environ if environ is None else environ
    spec = backend_config.get("defence_endpoint")
    if agent.transport == "scripted":
        inner, key, base_url, entry = built.inner_transport, "scripted-no-key", built.base_url, None
    else:
        _require(isinstance(spec, Mapping) and isinstance(spec.get("endpoint"), str),
                 "this defence calls its own endpoint: give --defence-endpoint (D-675)")
        assert isinstance(spec, Mapping)
        cfg = AgentConfig(model_requested=agent.model_requested, endpoint=str(spec["endpoint"]),
                          api_key_env=spec.get("api_key_env"), base_url=spec.get("base_url"))
        base_url = resolve_base_url(cfg)
        validate_base_url(base_url)
        key = env.get(cfg.api_key_env) if cfg.api_key_env else None
        _require(bool(key), "the defence endpoint's API key variable is not set")
        inner = default_inner_transport()
        try:
            from agentprov_capture.endpoints import get_endpoint

            entry = get_endpoint(cfg.endpoint)
        except Exception:  # noqa: BLE001 - a custom endpoint: the base allowlist only
            entry = None
    recorder = WireRecorder(session, configured_params={}, endpoint=entry)
    return openai.OpenAI(api_key=key, base_url=base_url, http_client=_default_http_client(RecordingTransport(inner, recorder)))


def _is_label(label: str) -> bool:
    if not label or label.startswith("/") or "\\" in label or "\x00" in label:
        return False
    parts = label.split("/")
    return all(p not in ("", ".", "..") for p in parts)


def build_instrumented_pipeline(config: Any, session: CaptureSession, *, name: str | None = None) -> Any:
    """``PassRecorder(AgentPipeline([SystemMessage(prompt), InitQuery(), LlmSpan(llm),
    ToolsExecutionLoop([MirrorToolsExecutor(tool_result_to_str), LlmSpan(llm)])]))`` -- the stock undefended pipeline
    of ``AgentPipeline.from_config`` (``agent_pipeline.py:202-206``) with the recording elements.

    ``config`` is an ``agentdojo.agent_pipeline.PipelineConfig`` whose ``llm`` is an element. A defence or a
    non-YAML tool-output format raises ``UnsupportedConfiguration`` (OB-8): recording a defended run as undefended is
    the failure this refuses."""
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
    from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, tool_result_to_str

    from agentprov_backend._llm import SpannedLLM
    from agentprov_backend.executor_mirror import MirrorToolsExecutor
    from agentprov_backend.pass_recorder import PassRecorder

    if getattr(config, "defense", None) is not None:
        raise UnsupportedConfiguration(f"defended pipelines are refused in v0.1 (defense={config.defense!r})")
    if getattr(config, "tool_output_format", None) not in (None, "yaml"):
        raise UnsupportedConfiguration(
            f"only the YAML tool-output format is supported (got {config.tool_output_format!r})")
    llm = config.llm
    if not isinstance(llm, BasePipelineElement):
        raise UnsupportedConfiguration("build_instrumented_pipeline needs an LLM element, not a model name")
    if config.system_message is None:
        raise UnsupportedConfiguration("PipelineConfig.system_message was not resolved")
    tools_loop = ToolsExecutionLoop([MirrorToolsExecutor(tool_result_to_str, hooks=session), SpannedLLM(llm, session)])
    pipeline = AgentPipeline([SystemMessage(config.system_message), InitQuery(), SpannedLLM(llm, session), tools_loop])
    pipeline.name = name or getattr(llm, "name", None) or getattr(llm, "model", None)
    return PassRecorder(pipeline, session)


class SuiteRunProxy:
    """Delegates to a ``TaskSuite``; its only override is ``run_task_with_pipeline``, which injects
    ``runtime_class`` (D.10.5)."""

    def __init__(self, suite: Any, runtime_class: type) -> None:
        object.__setattr__(self, "_suite", suite)
        object.__setattr__(self, "_runtime_class", runtime_class)

    def run_task_with_pipeline(self, agent_pipeline: Any, user_task: Any, injection_task: Any,
                               injections: dict[str, str], runtime_class: Any = None, environment: Any = None,
                               verbose: bool = False, **kwargs: Any) -> tuple[bool, bool]:
        # **kwargs: parameters a fork adds (the AutoDojo fork's `prompt_override`, task_suite.py), passed unchanged
        return self._suite.run_task_with_pipeline(agent_pipeline, user_task, injection_task, injections,
                                                  runtime_class=self._runtime_class, environment=environment,
                                                  verbose=verbose, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._suite, name)


# ---------------------------------------------------------------------------------------------- instrumentation


def _item(id_: str, kind: str, *, params: Any = None, detail: str | None = None,
          recorded: str = "full") -> dict[str, Any]:
    d: dict[str, Any] = {"id": id_, "kind": kind, "recorded": recorded}
    if params is not None:
        d["params"] = params
    if detail is not None:
        d["detail"] = detail
    return d


def instrumentation_items(agent: AgentConfig, built: BuiltLLM | None, backend_config: Mapping[str, Any],
                          *, mirror_source_sha256: str | None) -> list[dict[str, Any]]:
    """The D.10.7 items in force for this session (the attack item is added by ``AttackFactory``)."""
    if agent.provider == "anthropic":
        return _anthropic_items(agent, built, backend_config)
    import openai

    from agentprov_backend._http import sdk_httpx

    items = [
        _item("agentdojo.pass_recorder_wrap@1", "behaviour_preserving"),
        _item("agentdojo.executor_mirror@1", "behaviour_preserving",
              params={"mirrors": "0.1.35", **({"source_sha256": mirror_source_sha256} if mirror_source_sha256 else {})}),
        _item("agentdojo.recording_runtime_class@1", "behaviour_preserving"),
        _item("agentdojo.recording_transport@1", "behaviour_preserving",
              params={"sdk": "openai", "sdk_version": openai.__version__, "http_module": sdk_httpx().__name__}),
        _item("agentdojo.llm_span_brackets@1", "behaviour_preserving"),
    ]
    temperature = built.temperature if built is not None else agent.params.get("temperature", 0.0)
    if not temperature:
        items.append(_item("agentdojo.temperature_not_transmitted@1", "harness_policy",
                           params={"configured": agent.params.get("temperature")},
                           detail="agentdojo 0.1.35 sends `temperature or NOT_GIVEN`: a falsy temperature is "
                                  "not transmitted"))
    if agent.llm_element == "gateway_compat":
        items.append(_item("agentdojo.role_rewrite_developer_to_system@1", "request_modifying"))
        items.append(_item("agentdojo.retry_malformed_tool_json@1", "harness_policy", params={"max": 8}))
        items.append(_item("agentdojo.retry_upstream_failure@1", "harness_policy", params={"max": 8}))
        items.append(_item("agentdojo.http_backoff@1", "harness_policy",
                           params={"statuses": ["429", "5xx"], "policy": "gateway_compat", "max": 8,
                                   "max_server_errors": 3, "sdk_max_retries": 0}))
        host = built.host if built is not None else ""
        if host == "openrouter.ai" and bool(agent.params.get("reasoning_passback", True)):
            items.append(_item("agentdojo.reasoning_passback@1", "request_modifying",
                               detail="OpenRouter reasoning_details passed back on their assistant turn; reset per pass"))
    else:
        items.append(_item("agentdojo.http_backoff@1", "harness_policy",
                           params={"statuses": ["429", "5xx"], "policy": "stock_sdk"},
                           detail="native element: the SDK's own retries (max_retries=2) and agentdojo's tenacity "
                                  "retry (3 attempts) are stock; every wire attempt is recorded"))
    items.append(_item("agentdojo.env_dump_per_pass@1", "behaviour_preserving",
                       params={"snapshots": bool(backend_config.get("env_snapshots", True))}))
    if agent.transport == "scripted":
        items.append(_item("agentdojo.transport_scripted@1", "test_only"))
    sched = backend_config.get("scheduler")
    if isinstance(sched, Mapping):
        if "parallel_workers" in sched:
            items.append(_item("agentdojo.scheduler_parallel_workers@1", "harness_policy",
                               params={"n": sched["parallel_workers"]}, recorded="summary"))
        if "start_stagger_s" in sched:
            items.append(_item("agentdojo.scheduler_start_stagger@1", "harness_policy",
                               params={"n": sched["start_stagger_s"]}, recorded="summary"))
    return items


def _common_tail(agent: AgentConfig, backend_config: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = [_item("agentdojo.env_dump_per_pass@1", "behaviour_preserving",
                   params={"snapshots": bool(backend_config.get("env_snapshots", True))})]
    if agent.transport == "scripted":
        items.append(_item("agentdojo.transport_scripted@1", "test_only"))
    sched = backend_config.get("scheduler")
    if isinstance(sched, Mapping):
        if "parallel_workers" in sched:
            items.append(_item("agentdojo.scheduler_parallel_workers@1", "harness_policy",
                               params={"n": sched["parallel_workers"]}, recorded="summary"))
        if "start_stagger_s" in sched:
            items.append(_item("agentdojo.scheduler_start_stagger@1", "harness_policy",
                               params={"n": sched["start_stagger_s"]}, recorded="summary"))
    return items


def _anthropic_items(agent: AgentConfig, built: BuiltLLM | None,
                     backend_config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The D.10.7 items of a provider-``anthropic`` session (D-656): the declared port of the stock ``AnthropicLLM`` on
    the async recording transport; the max_tokens choice; temperature not transmitted when it is null."""
    from agentprov_backend._http import anthropic_httpx

    try:
        import anthropic

        sdk_version, http_module = anthropic.__version__, anthropic_httpx().__name__
    except ImportError:  # the element could not be built; the session records the setup error
        sdk_version, http_module = "unavailable", "unavailable"
    params = agent.params
    items = [
        _item("agentdojo.pass_recorder_wrap@1", "behaviour_preserving"),
        _item("agentdojo.executor_mirror@1", "behaviour_preserving"),
        _item("agentdojo.recording_runtime_class@1", "behaviour_preserving"),
        _item("agentdojo.recording_transport@1", "behaviour_preserving",
              params={"sdk": "anthropic", "sdk_version": sdk_version, "http_module": http_module, "mode": "async",
                      "inner_keepalive": 0},
              detail="streamed replies are read to their end before the SDK parses them (the stock element waits for "
                     "the final message anyway); the inner transport keeps no connection alive, because the stock "
                     "element runs each query in a new event loop and a reused connection fails (D-656 R-1)"),
        _item("agentdojo.llm_span_brackets@1", "behaviour_preserving"),
        _item("agentdojo.anthropic_element_port@1", "behaviour_preserving",
              params={"ports": ["agentdojo.agent_pipeline.llms.anthropic_llm.AnthropicLLM.query",
                                "agentdojo.agent_pipeline.llms.anthropic_llm.chat_completion_request"],
                      "change": "temperature sent through extra_body when set (the SDK has no temperature parameter)"},
              detail="the stock element raises TypeError on anthropic 1.x; the port sends the same request object "
                     "(member order may differ) and is otherwise the stock code, checked by AST (D-656)"),
        _item("agentdojo.anthropic_max_tokens@1", "harness_policy",
              params={"max_tokens": params.get("max_tokens"), "mode": params.get("max_tokens_mode"),
                      "stock_default": ANTHROPIC_STOCK_MAX_TOKENS},
              detail="the run states max_tokens (explicit) or takes the harness default; AgentDojo's own default is "
                     "not used (D-656)"),
    ]
    if params.get("temperature") is None:
        items.append(_item("agentdojo.temperature_not_transmitted@1", "harness_policy",
                           params={"configured": None},
                           detail="agentdojo 0.1.35 AnthropicLLM sends temperature unless it is None; the harness "
                                  "leaves it None unless the run sets one (current models refuse sampling parameters)"))
    items.append(_item("agentdojo.http_backoff@1", "harness_policy",
                       params={"statuses": ["408", "409", "429", "5xx"], "policy": "stock_sdk"},
                       detail="native anthropic element: the SDK's own retries (max_retries=2) and agentdojo's "
                              "tenacity retry (3 attempts, not on BadRequestError) are stock; every wire attempt is "
                              "recorded"))
    return items + _common_tail(agent, backend_config)


DECLARED_SEMANTICS = {
    "benchmark": "agentdojo",
    "utility": "the stock user-task checker's verdict (true: the user task was solved)",
    "security": "the stock injection-task checker's verdict (true: the injection task's goal was achieved)",
    "benign_security": "run_task_without_injection_tasks returns security = true as a constant",
    "dos_security": "DoS attacks: security = not utility (benchmark.py:149-150)",
    "run_error": "a caught provider error imposes utility = false, security = true (benchmark.py:120-147)",
}


def _sdk_identity(agent: AgentConfig) -> dict[str, str]:
    """``{name, version}`` of the SDK the agent's element sends with (the recorded identity, C.13.3)."""
    try:
        if agent.provider == "anthropic":
            import anthropic

            return {"name": "anthropic", "version": anthropic.__version__}
        import openai

        return {"name": "openai", "version": openai.__version__}
    except ImportError:
        return {"name": "anthropic" if agent.provider == "anthropic" else "openai", "version": "unavailable"}


# ---------------------------------------------------------------------------------------------- the backend


class AgentDojoBackend:
    """The ``Backend`` of D.10.1 for stock AgentDojo (``agentdojo==0.1.35``)."""

    backend_id = BACKEND_ID
    version = agentprov_backend.__version__
    declared_semantics: Mapping[str, str] = DECLARED_SEMANTICS

    def __init__(self, benchmark_version: str = DEFAULT_BENCHMARK_VERSION) -> None:
        self.benchmark_version = benchmark_version
        self._identity: BenchmarkIdentity | None = None

    def identity(self) -> BenchmarkIdentity:
        if self._identity is None:
            from agentprov_backend.identity import benchmark_identity

            self._identity = benchmark_identity(self.benchmark_version)
        return self._identity

    def plan(self, spec: Mapping[str, Any]) -> RunPlan:
        return expand_plan(spec, backend_id=self.backend_id)

    def catalogue(self, benchmark_version: str | None = None) -> dict[str, Any]:
        """D-652: the suites, tasks and attacks a plan of this backend can select (worker op ``catalogue``)."""
        return {"backend": self.backend_id, **catalogue(benchmark_version or self.benchmark_version,
                                                        backend_id=self.backend_id)}

    # ------------------------------------------------------------------ backend hooks (the AutoDojo backend overrides)

    def check_agent(self, agent: AgentConfig) -> None:
        """Refuse an agent configuration this backend cannot record faithfully (none for stock AgentDojo)."""

    def check_cell(self, cell: CellSpec) -> None:
        """Refuse a cell this backend cannot run (stock AgentDojo: none here; a defence is resolved against the
        registry, ``defences.toml``, and refused there when this backend does not build it or its assets are missing)."""

    def instrumentation(self, agent: AgentConfig, built: BuiltLLM | None, backend_config: Mapping[str, Any], *,
                        mirror_source_sha256: str | None, environ: Mapping[str, str]) -> list[dict[str, Any]]:
        return instrumentation_items(agent, built, backend_config, mirror_source_sha256=mirror_source_sha256)

    def attack_overrides(self, cell: CellSpec, session: CaptureSession,
                         attack_env: Mapping[str, Any] | None) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
        """``(environment overrides for the attack's construction, extra instrumentation items)``; stock: none
        (``run_cell.attack_env`` is accepted and unused)."""
        return None, []

    def after_outcome(self, session: CaptureSession, utility: bool, security: bool, run_error: bool) -> None:
        """Called after the ``outcome`` event (the AutoDojo backend records the fork's imposed outcome)."""

    # ------------------------------------------------------------------ header

    def _header(self, cell: CellSpec, agent: AgentConfig, backend_config: Mapping[str, Any], plan_digest: str | None,
                items: Sequence[Mapping[str, Any]], built: BuiltLLM | None, pipeline_name: str | None,
                pipeline_extra: Mapping[str, Any] | None = None,
                local_model: Mapping[str, Any] | None = None, defence: Any = None,
                defence_digests: Mapping[str, str] | None = None) -> dict:
        ident = self.identity()
        host = built.host if built is not None else "unresolved"
        actors: dict[str, Any] = {
            "agent": {"kind": "llm_agent", "model": {"requested": agent.model_requested, "provider": agent.provider,
                                                     "endpoint": host}},
            "env": {"kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime"},
            "bench": {"kind": "benchmark", "name": "agentdojo"},
        }
        if cell.attack is not None:
            actors["attacker"] = {"kind": "attacker", "name": cell.attack}
        notes: list[tuple[str, str, Any]] = []
        if defence is not None:
            from agentprov_backend.defences import ACTOR, defence_actor, defence_identity

            model = None
            if defence.aux_llm == "agent_endpoint":
                model = {"requested": agent.model_requested, "provider": agent.provider, "endpoint": host}
            actors[ACTOR] = defence_actor(defence, model)
            notes.append(("agentdojo", "defence_identity", defence_identity(defence, defence_digests or {})))
        benchmark: dict[str, Any] = {"name": "agentdojo", "dist": ident.distribution,
                                     "dist_version": ident.version_reported, "suite_set": ident.benchmark_version,
                                     "tool_definitions_sha256": ident.tool_definitions_sha256,
                                     "system_prompt_sha256": ident.default_system_prompt_sha256}
        src = ident.source
        if src.get("repo"):
            benchmark["repo"] = src["repo"]
        if re.fullmatch(r"[0-9a-f]{40}", src.get("commit", "") or ""):
            benchmark["commit"] = src["commit"]
        if re.fullmatch(r"[0-9a-f]{64}", src.get("wheel_sha256", "") or ""):
            benchmark["wheel_sha256"] = src["wheel_sha256"]
        return {
            "cell": {"benchmark": "agentdojo", "suite": cell.suite, "task_id": cell.user_task_id,
                     "attack_id": cell.attack, "attack_target_id": cell.injection_task_id,
                     "defense_id": cell.defence, "attack_params": encode_value(dict(cell.attack_params))},
            "backend": {"id": self.backend_id, "version": agentprov_backend.__version__},
            "runtime": {"python": ident.python, "platform": ident.platform, "lock_sha256": ident.lock_sha256},
            "actors": actors,
            "config_sha256": config_sha256(cell, agent, backend_config, plan_digest, backend_id=self.backend_id),
            "instrumentation": list(items),
            "identity": {
                "benchmark": benchmark,
                "harness": {"dist": "agentprov-backend", "version": agentprov_backend.__version__},
                "agent": {"model_requested": agent.model_requested, "provider": agent.provider,
                          "endpoint_host": host, "sdk": _sdk_identity(agent)},
            },
            "notes": [
                ("agentdojo", "identity_digests", ident.to_json()),
                ("agentdojo", "cell", {"cell_key": cell.cell_key, "kind": cell.kind,
                                       "benchmark_version": self.benchmark_version, "plan_sha256": plan_digest}),
                ("agentdojo", "pipeline", {"name": pipeline_name, "llm_element": agent.llm_element,
                                           "transport": agent.transport, **dict(pipeline_extra or {})}),
                # D-693: T0's observation of the local model just before this cell, as given (not mapped; raw only)
                *((("agentdojo", "local_model", dict(local_model)),) if local_model is not None else ()),
                *notes,
            ],
        }

    # ------------------------------------------------------------------ execute

    def execute(self, cell: CellSpec, agent: AgentConfig, session: CaptureSession, *,
                backend_config: Mapping[str, Any] | None = None, plan_sha256: str | None = None,
                inner_transport: Any = None, environ: Mapping[str, str] | None = None,
                sleep: Callable[[float], None] | None = None,
                attack_env: Mapping[str, Any] | None = None,
                local_model: Mapping[str, Any] | None = None) -> CellResult:
        """Run one cell through the stock runner (see the module docstring). Always returns a sealed session's
        result; the session status is ``complete`` (the stock runner returned), ``incomplete`` (it returned but some
        evidence is missing, e.g. no native log), ``errored`` (an exception escaped, or the cell was refused) or
        ``aborted`` (interrupted). ``attack_env`` is ``run_cell.attack_env`` (used by the AutoDojo backend only).
        ``local_model`` is ``run_cell.local_model``: T0's per-cell observation of a local model, recorded as the header
        note ``agentdojo/local_model`` (D-693)."""
        from agentdojo.agent_pipeline.agent_pipeline import PipelineConfig

        from agentprov_backend.attacks import AttackFactory, RecordingAttack
        from agentprov_backend.executor_mirror import guard

        bc = dict(backend_config or {})
        version = bc.get("benchmark_version", self.benchmark_version)
        mirror_sha: str | None = None
        built: BuiltLLM | None = None
        pipeline: Any = None
        attack: Any = None
        attack_items: tuple[Mapping[str, Any], ...] = ()
        suite: Any = None
        pre_error: BaseException | None = None
        pipeline_name = bc.get("pipeline_name") or agent.model_requested
        pipeline_extra: dict[str, Any] = {}
        defence: Any = None
        defence_digests: dict[str, str] = {}
        defence_items_: list[dict[str, Any]] = []
        env = os.environ if environ is None else environ
        try:
            _require(version == self.benchmark_version, "benchmark_version differs from the worker's")
            self.check_cell(cell)
            self.check_agent(agent)
            if cell.defence not in (None, "none"):
                from agentprov_backend.defences import entry_refusal, resolve

                defence = resolve(cell.defence, self.backend_id)
                _require("*" in defence.suites or cell.suite in defence.suites,
                         f"the defence {defence.id!r} runs on {list(defence.suites)} only")
                refusal = entry_refusal(defence)
                _require(refusal is None, f"the defence {defence.id!r} cannot be built here: {refusal}")
            mirror_sha = guard()
            from agentdojo.task_suite.load_suites import _SUITES

            _require(cell.suite in _SUITES[version], f"unknown suite {cell.suite!r}")
            suite = _SUITES[version][cell.suite]
            built = build_llm(agent, session, inner_transport=inner_transport, environ=environ, sleep=sleep)
            config = PipelineConfig(llm=built.element, model_id=None, defense=None, system_message_name=None,
                                    system_message=bc.get("system_message"),
                                    tool_output_format=bc.get("tool_output_format"))
            if defence is None:
                pipeline = build_instrumented_pipeline(config, session, name=pipeline_name)
            else:
                from agentprov_backend.defences import build_defended_pipeline, defence_items

                defence_client = (build_defence_client(agent, bc, session, built, environ=environ)
                                  if defence.aux_llm == "defence_endpoint" else None)
                made_defence = build_defended_pipeline(defence, config, session, name=pipeline_name,
                                                       defence_client=defence_client)
                pipeline = made_defence.pipeline
                defence_digests = made_defence.digests
                defence_items_ = defence_items(defence, made_defence.substitutions)
                pipeline_extra["defence"] = defence.id
                pipeline_name = pipeline.name
            loop = next(e for e in pipeline.inner.elements if hasattr(e, "max_iters"))
            if hasattr(loop, "max_input_tokens"):
                # a fork's ToolsExecutionLoop limit (AutoDojo): the harness never sets it; recorded in the pipeline note
                _require(loop.max_input_tokens is None, "ToolsExecutionLoop.max_input_tokens must be None")
                pipeline_extra["max_input_tokens"] = loop.max_input_tokens
            if cell.kind in ("attacked", "dos"):
                _require(cell.attack is not None and cell.injection_task_id is not None,
                         "an attacked cell needs attack and injection_task_id")
                overrides, extra_items = self.attack_overrides(cell, session, attack_env)
                made = AttackFactory(suite, pipeline).create(cell.attack, cell.attack_params,
                                                             model_id=agent.model_requested, env_overrides=overrides)
                _require(bool(made.attack.is_dos_attack) == (cell.kind == "dos"), "cell kind does not match attack")
                attack_items = (*made.instrumentation, *extra_items)
                attack = RecordingAttack(made.attack, session)
        except BaseException as exc:  # noqa: BLE001 - every failure seals the session
            pre_error = exc
        items = (self.instrumentation(agent, built, bc, mirror_source_sha256=mirror_sha, environ=env)
                 + list(attack_items) + defence_items_)
        session.env_snapshots = bool(bc.get("env_snapshots", True))
        session.start(self._header(cell, agent, bc, plan_sha256, items, built, pipeline_name, pipeline_extra,
                                   local_model, defence=defence, defence_digests=defence_digests))
        status = "errored"
        outcome: dict[str, Any] | None = None
        if pre_error is not None:
            session.record_error(pre_error, fatal=True, where="setup")
            status = "aborted" if isinstance(pre_error, KeyboardInterrupt) else "errored"
        else:
            try:
                outcome = self._run(cell, suite, pipeline, attack, session, version)
                status = "complete"
            except KeyboardInterrupt as exc:
                session.record_error(exc, fatal=True, where="cell")
                status = "aborted"
            except BaseException as exc:  # noqa: BLE001
                session.record_error(exc, fatal=True, where="cell")
                status = "errored"
        if session.poisoned:
            # a failed redaction scan: nothing more is written; close() seals errored (C.13.10 item 6)
            head = session.close("errored")
            return CellResult("errored", None, (), head)
        try:
            natives = self._collect_native(session)
        except Exception as exc:  # noqa: BLE001 - keep the session sealable
            session.problems.append("native_log_error")
            session.record_error(exc, fatal=False, where="native_log")
            natives = ()
        if status == "complete" and (not natives or session.problems):
            status = "incomplete"
        head = session.close(status)
        return CellResult(session.final_status or status, outcome, natives, head)  # type: ignore[arg-type]

    def _run(self, cell: CellSpec, suite: Any, pipeline: Any, attack: Any, session: CaptureSession,
             version: str) -> dict[str, Any]:
        from agentdojo.benchmark import run_task_with_injection_tasks, run_task_without_injection_tasks
        from agentdojo.logging import OutputLogger

        from agentprov_backend.runtime import RecordingFunctionsRuntime

        proxy = SuiteRunProxy(suite, RecordingFunctionsRuntime.bind(session))
        logdir = session.native_tmp_dir
        logdir.mkdir(parents=True, exist_ok=True)
        with OutputLogger(logdir=str(logdir)):
            if cell.kind == "user_task":
                task = suite.get_user_task_by_id(cell.user_task_id)
                utility, security = run_task_without_injection_tasks(proxy, pipeline, task, logdir, True, version)
            elif cell.kind == "injection_task_as_user_task":
                task = suite.get_injection_task_by_id(cell.user_task_id)
                utility, security = run_task_without_injection_tasks(proxy, pipeline, task, logdir, True, version)
            else:
                task = suite.get_user_task_by_id(cell.user_task_id)
                u, s = run_task_with_injection_tasks(proxy, pipeline, task, attack, logdir, True,
                                                     injection_tasks=[cell.injection_task_id],
                                                     benchmark_version=version)
                ((_, utility),) = u.items()
                ((_, security),) = s.items()
        run_error = session.pipeline_errors > 0 or self._native_error(session)
        if run_error:
            origins = ("harness_default", "harness_default")
        elif cell.kind in ("user_task", "injection_task_as_user_task"):
            origins = ("checker", "harness_default")
        elif cell.kind == "dos":
            origins = ("checker", "harness_rule")
        else:
            origins = ("checker", "checker")
        session.outcome([{"name": "utility", "value": bool(utility), "origin": origins[0]},
                         {"name": "security", "value": bool(security), "origin": origins[1]}],
                        dict(self.declared_semantics))
        self.after_outcome(session, bool(utility), bool(security), bool(run_error))
        return {"utility": bool(utility), "security": bool(security)}

    @staticmethod
    def _native_files(session: CaptureSession) -> list[Path]:
        root = session.native_tmp_dir
        return sorted(p for p in root.rglob("*.json") if p.is_file()) if root.is_dir() else []

    def _native_error(self, session: CaptureSession) -> bool:
        files = self._native_files(session)
        if len(files) != 1:
            return False
        try:
            return json.loads(files[0].read_text(encoding="utf-8")).get("error") is not None
        except (OSError, ValueError, AttributeError):
            return False

    def _collect_native(self, session: CaptureSession) -> tuple[str, ...]:
        """Move the TraceLogger JSON, unchanged, to ``raw/capture/<session>.native.json`` and announce it."""
        files = self._native_files(session)
        root = session.native_tmp_dir
        try:
            if len(files) != 1:
                session.problems.append("native_log_missing" if not files else "native_log_ambiguous")
                session.note("agentdojo", "native_log_problem",
                             {"n_files": len(files), "paths": [p.relative_to(root).as_posix() for p in files]})
                if not files:
                    return ()
            src = files[0]
            rel = src.relative_to(root).as_posix()
            dest = session.dir / session.native_label
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dest)
            session.note("agentdojo", "native_log_stock_path", {"logdir_relative": rel})
            session.add_native(session.native_label, "application/json")
            return (session.native_label,)
        finally:
            if root.is_dir() and not any(p.is_file() for p in root.rglob("*")):
                shutil.rmtree(root, ignore_errors=True)


def select_backend(benchmark_version: str = DEFAULT_BENCHMARK_VERSION) -> AgentDojoBackend:
    """The backend for the installed ``agentdojo``, chosen by its PEP 610 source (never by the version string, which
    the forks share): the AutoDojo fork's git repository gives ``AutoDojoBackend`` and AgentDyn's gives
    ``AgentDynBackend`` (each then refuses any commit but its pinned one), anything else ``AgentDojoBackend``. T0
    cross-checks the identity either way (D.10.6)."""
    import importlib.metadata

    from agentprov_backend.identity import installed_source

    try:
        source = installed_source()
    except importlib.metadata.PackageNotFoundError:
        return AgentDojoBackend(benchmark_version)  # no benchmark installed: identity() then fails as before
    if source.get("kind") == "git" and source.get("repo") == "https://github.com/xhOwenMa/AutoDojo":
        from agentprov_backend.autodojo import AutoDojoBackend

        return AutoDojoBackend(benchmark_version)
    if source.get("kind") == "git" and source.get("repo") == "https://github.com/SaFo-Lab/AgentDyn":
        from agentprov_backend.agentdyn import AgentDynBackend

        return AgentDynBackend(benchmark_version)
    return AgentDojoBackend(benchmark_version)


# ---------------------------------------------------------------------------------------------- preflight probe


#: The key the probe's system message asks for. It appears only in that message (the user message is "Probe."), so a call
#: that names it shows the message reached the model; a distinctive value, so a model that never saw the instruction is
#: unlikely to guess it (D-291).
PROBE_KEY = "q7f3-probe"
PROBE_PROMPT = f"Call the tool get_probe_value with the key '{PROBE_KEY}'. Do not answer in text."
#: Marks of a tool call written as text (D.10.9 A4): Llama/Hermes-style function tags.
TEXT_TOOL_CALL_MARKS = ("<function=", "<|python_tag|>", "<tool_call>")
#: A role refusal written into a 2xx body (as text or as an error message) by gateways that do not use an HTTP error.
_ROLE_REFUSAL = re.compile(
    r"(?i)(?:\b(?:unsupported|invalid|unknown|unrecognized|unexpected)\s+(?:message\s+)?role\b"
    r"|\brole\b[^\n]{0,60}\b(?:developer|system)\b[^\n]{0,60}\b(?:not\s+supported|unsupported|not\s+allowed|not\s+permitted|invalid|rejected)"
    r"|\b(?:developer|system)\b[^\n]{0,40}\b(?:role|message)s?\b[^\n]{0,40}\b(?:not\s+supported|unsupported|not\s+allowed|not\s+permitted|invalid|rejected))")


def _reply_text(message: Mapping[str, Any]) -> str:
    """The text of a chat-completion message: ``content`` (a string or text parts) and ``refusal``."""
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        parts += [p["text"] for p in content if isinstance(p, Mapping) and isinstance(p.get("text"), str)]
    if isinstance(message.get("refusal"), str):
        parts.append(message["refusal"])
    return "\n".join(parts)


def _calls_probe_key(message: Mapping[str, Any]) -> bool:
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return False
    from agentprov_backend.gateway import decode_json_body

    for call in calls:
        fn = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(fn, Mapping) or fn.get("name") != "get_probe_value" or not isinstance(fn.get("arguments"), str):
            continue
        args = decode_json_body(fn["arguments"].encode("utf-8"))
        if isinstance(args, Mapping) and args.get("key") == PROBE_KEY:
            return True
    return False


def messages_roles_verdict(http_status: int | None, body: bytes | None, media: str | None) -> tuple[str, str]:
    """:func:`roles_verdict` for an Anthropic Messages reply (D-656), JSON or ``text/event-stream``: ``accepted`` when
    a ``tool_use`` block calls ``get_probe_value`` with :data:`PROBE_KEY` (or the text names both); ``refused`` for a
    non-2xx status, an error object or ``error`` event (``error_object``), or a role refusal in the text;
    ``unconfirmed`` for a body that does not decode (``body_not_json``), ``stop_reason: "refusal"`` (``refusal``), a
    stream without ``message_stop`` (``stream_incomplete``) or no evidence (``instruction_not_evidenced``)."""
    from agentprov_backend.messages import decode_messages_body

    if http_status is None:
        return "unknown", "no_reply"
    if not 200 <= http_status < 300:
        return "refused", f"http_{http_status}"
    msg = decode_messages_body(body, media) if body is not None else None
    if msg is None:
        return "unconfirmed", "body_not_json"
    if msg.error is not None:
        return "refused", "error_object"
    text = "\n".join(b["text"] for b in msg.content if b.get("type") == "text" and isinstance(b.get("text"), str))
    if _ROLE_REFUSAL.search(text):
        return "refused", "role_refusal_text"
    for block in msg.content:
        if (block.get("type") == "tool_use" and block.get("name") == "get_probe_value"
                and isinstance(block.get("input"), Mapping) and block["input"].get("key") == PROBE_KEY):
            return "accepted", "instruction_followed"
    if "get_probe_value" in text and PROBE_KEY in text:
        return "accepted", "instruction_followed"
    if msg.stop_reason == "refusal":
        return "unconfirmed", "refusal"
    if not msg.complete:
        return "unconfirmed", "stream_incomplete"
    return "unconfirmed", "instruction_not_evidenced"


def roles_verdict(http_status: int | None, body: bytes | None) -> tuple[str, str]:
    """Whether the endpoint accepted the stock roles, decided from the reply itself (D.10.9 A9; D-291): a 2xx status
    alone proves nothing, because gateways also answer 2xx with an error object, write a role refusal as text, or drop
    a role they do not know without saying so. Returns ``(verdict, reason)``:

    * ``accepted``: the reply follows the system-message instruction (``get_probe_value`` with :data:`PROBE_KEY`, as a
      structured call or as text; ``instruction_followed``);
    * ``refused``: a non-2xx status (``http_<n>``), a 2xx body with an ``error`` object (``error_object``) or a role
      refusal in its text (``role_refusal_text``);
    * ``unconfirmed``: a 2xx reply that neither refuses nor shows the instruction was read (``instruction_not_evidenced``,
      ``no_choices``, ``finish_error``, ``body_not_json``): the roles may have been ignored silently;
    * ``unknown``: no reply (``no_reply``).

    Only the decoded body is read: headers never enter the verdict."""
    from agentprov_backend.gateway import decode_json_body

    if http_status is None:
        return "unknown", "no_reply"
    if not 200 <= http_status < 300:
        return "refused", f"http_{http_status}"
    decoded = decode_json_body(body) if body is not None else None
    if not isinstance(decoded, Mapping):
        return "unconfirmed", "body_not_json"
    if decoded.get("error") not in (None, {}, ""):
        return "refused", "error_object"
    choices = decoded.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return "unconfirmed", "no_choices"
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        return "unconfirmed", "no_choices"
    text = _reply_text(message)
    if _ROLE_REFUSAL.search(text):
        return "refused", "role_refusal_text"
    if _calls_probe_key(message) or ("get_probe_value" in text and PROBE_KEY in text):
        return "accepted", "instruction_followed"
    if choices[0].get("finish_reason") == "error":
        return "unconfirmed", "finish_error"
    return "unconfirmed", "instruction_not_evidenced"


def get_probe_value(key: str) -> str:
    """Return the probe value for a key.

    :param key: the key to look up.
    """
    return f"value-{key}"


def get_probe_time() -> str:
    """Return a fixed probe time."""
    return "2026-01-01T00:00:00Z"


def run_probe(agent: AgentConfig, session: CaptureSession, backend: AgentDojoBackend, *,
              inner_transport: Any = None, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The D.10.9 preflight probe for one endpoint and model, written as its own capture session (role
    ``supporting``; never mapped to an execution). One canned two-tool request is sent through the same LLM element,
    SDK client and recording transport a cell would use. Results:

    * ``reachable``: an HTTP reply arrived (any status);
    * ``roles`` and ``roles_reason``: :func:`roles_verdict` of the last reply to the stock-role request
      (``developer``/``user`` under ``native``), read from its recorded body; ``roles_accepted`` is ``roles ==
      "accepted"`` (D-291: a 2xx status alone no longer counts);
    * ``params``: configured vs transmitted values, and the configured keys that were not transmitted (A3);
    * ``tool_calls``: ``structured`` (a ``tool_calls`` reply), ``text_encoded`` (no structured call, but the text names
      a probe tool or carries a function tag; A4), ``none`` or ``error``.
    """
    from agentdojo.functions_runtime import FunctionsRuntime, make_function
    from agentdojo.types import ChatSystemMessage, ChatUserMessage, text_content_block_from_string

    from agentprov_backend._llm import SpannedLLM

    cell = CellSpec("probe/preflight/none/none", "probe", "preflight", None, None, None, "user_task", {})
    built: BuiltLLM | None = None
    error: BaseException | None = None
    try:
        backend.check_agent(agent)
        built = build_llm(agent, session, inner_transport=inner_transport, environ=environ)
    except BaseException as exc:  # noqa: BLE001 - recorded in the probe session
        error = exc
    items = [_item("agentdojo.recording_transport@1", "behaviour_preserving"),
             _item("agentdojo.llm_span_brackets@1", "behaviour_preserving"),
             _item("agentdojo.preflight_probe@2", "harness_policy",
                   detail="a canned two-tool request; roles judged from the reply (D.10.9, D-291)")]
    if agent.transport == "scripted":
        items.append(_item("agentdojo.transport_scripted@1", "test_only"))
    header = backend._header(cell, agent, {}, None, items, built, agent.model_requested)
    header["cell"] = {"benchmark": "agentdojo", "task_id": "preflight_probe", "attack_params": {}}
    session.start(header)
    result: dict[str, Any] = {"reachable": False, "roles_accepted": False, "roles": "unknown", "roles_reason": "no_reply",
                              "http_status": None,
                              "params": {"configured": dict(agent.params), "transmitted": {}, "not_transmitted": []},
                              "tool_calls": "error"}
    status = "complete"
    if error is not None:
        session.record_error(error, fatal=True, where="probe")
        status = "errored"
    else:
        assert built is not None
        runtime = FunctionsRuntime([make_function(get_probe_value), make_function(get_probe_time)])
        messages = [ChatSystemMessage(role="system", content=[text_content_block_from_string(PROBE_PROMPT)]),
                    ChatUserMessage(role="user", content=[text_content_block_from_string("Probe.")])]
        try:
            _, _, _, out, _ = SpannedLLM(built.element, session).query("Probe.", runtime, messages=messages)
            reply = out[-1]
            if reply.get("tool_calls"):
                result["tool_calls"] = "structured"
            else:
                from agentdojo.types import get_text_content_as_str

                text = get_text_content_as_str(reply["content"] or [])
                named = any(name in text for name in ("get_probe_value", "get_probe_time"))
                marked = any(mark in text for mark in TEXT_TOOL_CALL_MARKS)
                result["tool_calls"] = "text_encoded" if named or marked else "none"
        except BaseException as exc:  # noqa: BLE001
            session.record_error(exc, fatal=False, where="probe")
        responses = [e for e in _events(session) if e["type"] in ("llm.request", "llm.response")]
        statuses = [e["data"].get("http_status") for e in responses if e["type"] == "llm.response"]
        result["reachable"] = any(isinstance(x, int) for x in statuses)
        last_response = next((e["data"] for e in reversed(responses) if e["type"] == "llm.response"
                              and isinstance(e["data"].get("http_status"), int)), None)
        last = None if last_response is None else last_response["http_status"]
        result["http_status"] = last
        body = None if last_response is None else _blob_bytes(session, last_response.get("response"))
        if agent.provider == "anthropic":
            ref = last_response.get("response") if last_response is not None else None
            media = ref.get("media") if isinstance(ref, Mapping) else None
            result["roles"], result["roles_reason"] = messages_roles_verdict(last, body, media)
        else:
            result["roles"], result["roles_reason"] = roles_verdict(last, body)
        result["roles_accepted"] = result["roles"] == "accepted"
        reqs = [e for e in responses if e["type"] == "llm.request"]
        if reqs:
            transmitted = reqs[-1]["data"]["params"]["transmitted"]
            result["params"]["transmitted"] = transmitted
            if agent.provider == "anthropic":  # a null value is "not configured"; the budget is sent as `thinking`
                wire = {"thinking_budget_tokens": "thinking"}
                result["params"]["not_transmitted"] = sorted(
                    k for k in agent.params
                    if k in ("temperature", "max_tokens", "thinking_budget_tokens") and agent.params[k] is not None
                    and wire.get(k, k) not in transmitted)
            else:
                result["params"]["not_transmitted"] = sorted(k for k in agent.params
                                                              if k in ("temperature", "reasoning_effort", "top_p",
                                                                       "seed", "max_tokens") and k not in transmitted)
    session.note("agentdojo", "preflight_result", result)
    head = session.close(status)
    result["capture_head"] = head
    result["status"] = status
    return result


def _blob_bytes(session: CaptureSession, ref: Any) -> bytes | None:
    """The stored (redacted) bytes of a blob reference of this session, or ``None``."""
    if not isinstance(ref, Mapping) or not isinstance(ref.get("$blob"), str):
        return None
    digest = ref["$blob"].removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None
    try:
        return (session.blobs_dir / "sha256" / digest[:2] / digest).read_bytes()
    except OSError:
        return None


def _events(session: CaptureSession) -> list[dict[str, Any]]:
    return [json.loads(line) for line in session.capture_path.read_bytes().splitlines()]
