"""The worker's identity report (D.10.1 ``BenchmarkIdentity``; D.10.6; D.11.3 ``hello_ok``; G.6.3).

Everything here is the worker's *self-report*. T0 computes the same digests from the built environment's files before
spawning and cross-checks them (D.10.6, SR-09(3)); the worker never decides whether it matches.

* ``record_digest``: sha256 over the bytes of the benchmark distribution's dist-info ``RECORD`` file.
* ``source``: PEP 610 ``direct_url.json`` when present (``{"kind": "git", "repo", "commit"}``, ``{"kind": "url",
  ...}``, ``{"kind": "dir", ...}``); a registry wheel has none and is ``{"kind": "pypi"}``.
* ``guarded_sources``: qualified name -> sha256 of ``inspect.getsource()`` for the guarded names of D.10.6, plus
  ``FunctionsRuntime.run_function`` and the two stock runner functions the harness drives.
* ``tool_definitions_sha256``: JCS sha256 of ``{suite: [{name, description, parameters}]}`` over the suite set.
* ``default_system_prompt_sha256``: sha256 (UTF-8) of AgentDojo's default system message.
* ``lock_sha256``: see ``lock_digest`` (D.10.10 item 3).
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import json
import platform
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "BenchmarkIdentity",
    "AGENTDYN_GUARDED_NAMES",
    "AUTODOJO_GUARDED_NAMES",
    "ENV_MARKER",
    "GUARDED_NAMES",
    "LockDigestUnavailable",
    "benchmark_identity",
    "lock_digest",
]

ENV_MARKER = "AGENTPROV_ENV.json"

#: D.10.6 guarded qualified names (module, attribute path), plus the runtime and the two runner entry points.
GUARDED_NAMES: tuple[tuple[str, str], ...] = (
    ("agentdojo.agent_pipeline.tool_execution", "ToolsExecutor.query"),
    ("agentdojo.task_suite.task_suite", "TaskSuite.run_task_with_pipeline"),
    ("agentdojo.task_suite.task_suite", "model_output_from_messages"),
    ("agentdojo.logging", "TraceLogger.log"),
    ("agentdojo.logging", "TraceLogger.save"),
    ("agentdojo.agent_pipeline.llms.openai_llm", "_function_to_openai"),
    ("agentdojo.agent_pipeline.llms.openai_llm", "_message_to_openai"),
    ("agentdojo.agent_pipeline.llms.openai_llm", "_openai_to_assistant_message"),
    ("agentdojo.agent_pipeline.llms.openai_llm", "chat_completion_request"),
    ("agentdojo.agent_pipeline.llms.openai_llm", "OpenAILLM.query"),
    # D-656: the Anthropic element the declared port (``_anthropic_llm``) builds on: its rendering, parsing and the
    # two functions the port mirrors (checked equal by AST in the backend tests)
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "_conversation_to_anthropic"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "_merge_tool_result_messages"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "_message_to_anthropic"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "_function_to_anthropic"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "_anthropic_to_assistant_message"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "chat_completion_request"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "AnthropicLLM.__init__"),
    ("agentdojo.agent_pipeline.llms.anthropic_llm", "AnthropicLLM.query"),
    ("agentdojo.functions_runtime", "FunctionsRuntime.run_function"),
    ("agentdojo.benchmark", "run_task_with_injection_tasks"),
    ("agentdojo.benchmark", "run_task_without_injection_tasks"),
)

#: Extra guarded names of the AutoDojo fork (D.11; D.10.6): the fork's request-and-parse retry, the tools loop with
#: ``max_input_tokens``, the cache-replay attack and the model-name fallback. Reported only by the AutoDojo backend.
AUTODOJO_GUARDED_NAMES: tuple[tuple[str, str], ...] = (
    ("agentdojo.agent_pipeline.llms.openai_llm", "_request_and_parse"),
    ("agentdojo.agent_pipeline.tool_execution", "ToolsExecutionLoop.query"),
    ("agentdojo.attacks.autodojo_attack", "AutoDojoAttack.__init__"),
    ("agentdojo.attacks.autodojo_attack", "AutoDojoAttack.attack"),
    ("agentdojo.attacks.base_attacks", "get_model_name_from_pipeline"),
)


#: Extra guarded names of AgentDyn (design D-682): the AgentDyn code that differs from 0.1.35 and bears on what is
#: recorded but is not already in :data:`GUARDED_NAMES` -- the temperature rule, the pipeline construction and the
#: default system message. Reported only by the AgentDyn backend.
AGENTDYN_GUARDED_NAMES: tuple[tuple[str, str], ...] = (
    ("agentdojo.agent_pipeline.llms.openai_llm", "_supports_temperature"),
    ("agentdojo.agent_pipeline.agent_pipeline", "AgentPipeline.from_config"),
    ("agentdojo.agent_pipeline.agent_pipeline", "load_system_message"),
)

class LockDigestUnavailable(RuntimeError):
    """The worker cannot name the ``uv.lock`` its environment was built from."""


@dataclass(frozen=True)
class BenchmarkIdentity:
    distribution: str
    version_reported: str
    source: Mapping[str, str]
    record_digest: str
    guarded_sources: Mapping[str, str]
    suite_set: tuple[str, ...]
    benchmark_version: str
    default_system_prompt_sha256: str
    tool_definitions_sha256: str
    python: str
    platform: str
    lock_sha256: str
    lock_source: str = field(default="marker")

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["suite_set"] = list(self.suite_set)
        d["source"] = dict(self.source)
        d["guarded_sources"] = dict(self.guarded_sources)
        return d


def lock_digest(prefix: Path | None = None) -> tuple[str, str]:
    """``(lock_sha256, source)`` of the backend project's ``uv.lock`` the running environment was built from.

    1. ``<sys.prefix>/AGENTPROV_ENV.json`` written by ``agentprov backends build`` (``lock_sha256`` member;
       D.11.2, G.6.2): source ``"marker"``. This is the production path: the parent computes the same digest from
       the lock independently (D.10.6) and cross-checks it.
    2. Otherwise, an in-project environment (``backends/<b>/.venv`` made by ``uv sync --project backends/<b>``, the
       development and CI layout): the ``uv.lock`` beside it, ``<sys.prefix>/../uv.lock``; source
       ``"project_lock"``.
    3. Otherwise ``LockDigestUnavailable``: ``session.start.runtime.lock_sha256`` is required, and nothing is run.
    """
    root = Path(sys.prefix if prefix is None else prefix)
    marker = root / ENV_MARKER
    if marker.is_file():
        try:
            doc = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LockDigestUnavailable(f"{ENV_MARKER} is unreadable: {type(exc).__name__}") from None
        value = doc.get("lock_sha256") if isinstance(doc, dict) else None
        if isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value):
            return value, "marker"
        raise LockDigestUnavailable(f"{ENV_MARKER} has no valid lock_sha256")
    lock = root.parent / "uv.lock"
    if root.name == ".venv" and lock.is_file():
        return hashlib.sha256(lock.read_bytes()).hexdigest(), "project_lock"
    raise LockDigestUnavailable("no AGENTPROV_ENV.json marker and no project uv.lock beside the environment")


def _resolve(module: str, path: str) -> Any:
    obj: Any = importlib.import_module(module)
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def guarded_source_digests(extra: tuple[tuple[str, str], ...] = ()) -> dict[str, str]:
    out: dict[str, str] = {}
    for module, path in (*GUARDED_NAMES, *extra):
        obj = _resolve(module, path)
        out[f"{module}.{path}"] = hashlib.sha256(inspect.getsource(obj).encode("utf-8")).hexdigest()
    return out


def _dist_source(dist: importlib.metadata.Distribution) -> dict[str, str]:
    text = dist.read_text("direct_url.json")
    if not text:
        return {"kind": "pypi"}
    try:
        doc = json.loads(text)
    except ValueError:
        return {"kind": "unreadable_direct_url"}
    url = doc.get("url", "")
    vcs = doc.get("vcs_info")
    if isinstance(vcs, dict):
        out = {"kind": str(vcs.get("vcs", "vcs")), "repo": str(url), "commit": str(vcs.get("commit_id", ""))}
        sub = doc.get("subdirectory")
        if isinstance(sub, str):
            out["subdirectory"] = sub
        return out
    if isinstance(doc.get("dir_info"), dict):
        return {"kind": "dir", "editable": str(bool(doc["dir_info"].get("editable", False))).lower()}
    archive = doc.get("archive_info")
    if isinstance(archive, dict):
        out = {"kind": "url", "url": str(url)}
        h = archive.get("hash") or ""
        if isinstance(h, str) and h.startswith("sha256="):
            out["wheel_sha256"] = h.split("=", 1)[1]
        return out
    return {"kind": "unknown"}


def record_digest(dist: importlib.metadata.Distribution) -> str:
    # RECORD names its own path; ``dist.files`` is not used because it stats every listed file, and the real-model
    # sandbox denies even a stat of a ``.env``/``.env.*`` file, which AgentDyn's package ships
    # (``agentdojo/defenses/camel/.env.example``)
    text = dist.read_text("RECORD")
    if text is None:
        raise RuntimeError("the benchmark distribution has no RECORD file")
    for line in text.splitlines():
        path = line.split(",", 1)[0]
        parts = path.split("/")
        if len(parts) == 2 and parts[1] == "RECORD" and parts[0].endswith(".dist-info"):
            return hashlib.sha256(Path(dist.locate_file(path)).read_bytes()).hexdigest()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tool_definitions(benchmark_version: str) -> dict[str, list[dict[str, Any]]]:
    from agentdojo.task_suite.load_suites import get_suites

    out: dict[str, list[dict[str, Any]]] = {}
    for name, suite in get_suites(benchmark_version).items():
        out[name] = [{"name": t.name, "description": t.description, "parameters": t.parameters.model_json_schema()}
                     for t in suite.tools]
    return out


def installed_source(distribution: str = "agentdojo") -> dict[str, str]:
    """The PEP 610 source of the installed benchmark distribution (no benchmark import)."""
    return _dist_source(importlib.metadata.distribution(distribution))


def benchmark_identity(benchmark_version: str = "v1.2.2", *, distribution: str = "agentdojo",
                       extra_guarded: tuple[tuple[str, str], ...] = ()) -> BenchmarkIdentity:
    import rfc8785
    from agentdojo.agent_pipeline.agent_pipeline import load_system_message
    from agentdojo.task_suite.load_suites import get_suites

    from agentprov_backend._jsonval import encode_value

    dist = importlib.metadata.distribution(distribution)
    lock, lock_source = lock_digest()
    tools = tool_definitions(benchmark_version)
    return BenchmarkIdentity(
        distribution=distribution,
        version_reported=dist.version,
        source=_dist_source(dist),
        record_digest=record_digest(dist),
        guarded_sources=guarded_source_digests(extra_guarded),
        suite_set=tuple(get_suites(benchmark_version)),
        benchmark_version=benchmark_version,
        default_system_prompt_sha256=hashlib.sha256(load_system_message(None).encode("utf-8")).hexdigest(),
        tool_definitions_sha256=hashlib.sha256(rfc8785.dumps(encode_value(tools))).hexdigest(),
        python=platform.python_version(),
        platform=platform.platform(),
        lock_sha256=lock,
        lock_source=lock_source,
    )
