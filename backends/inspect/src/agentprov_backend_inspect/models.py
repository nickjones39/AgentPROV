"""Inspect ``Model`` objects with a recording client (D-665; design §4.2).

Every model goes through Inspect's OpenAI-compatible provider (``openai-api/<endpoint>/<model>``: chat completions,
the wire format the scripted transport serves and ``endpoints.toml``'s ``openai_chat`` endpoints speak), constructed
with an ``http_client`` of the SDK's httpx family whose transport is the shared async recording transport around:

* the scripted transport (``transport = "scripted"``: a script file staged in the session; no network, no key); or
* the real transport (``transport = "http"``), routed through T0's egress proxy when ``AGENTPROV_EGRESS_PROXY`` is
  set (D-664) by the shared helper.

The key is passed as ``api_key`` (never in ``model_args``, so Inspect never writes it into the log header; the header
records ``model_args: {"http_client": null}``, the name of the injected client only, tested). A judge is a separate
``Model`` with its own client and observer, so its exchanges are recorded with ``role: auxiliary``. Every call builds a
new ``Model`` (``memoize=False``, D-743): Inspect's memo key does not include the injected client.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov_backend_inspect.plan import ModelSpec
from agentprov_backend_inspect.wire import WireObserver

__all__ = ["SCRIPTED_BASE_URL", "build_model", "inspect_model_name"]

SCRIPTED_BASE_URL = "https://scripted.invalid/v1"
SCRIPTED_KEY = "scripted-no-key"


def inspect_model_name(spec: ModelSpec) -> str:
    """The Inspect model name: ``openai-api/<endpoint>/<model>`` (the endpoint name is the provider label)."""
    return f"openai-api/{spec.endpoint}/{spec.model}"


def scripted_steps(path: Path, role: str) -> list[Any]:
    """The scripted steps of ``role`` (``"agent"`` or a judge role) from the session's script file: a combined document
    ``{"agent": [...], "judges": {"<role>": [...]}}`` (T0 stages one file per session), or a plain script (a list, or
    ``{"steps": [...]}``) for the agent only. Judges never share the agent's steps: their calls interleave."""
    import json

    from agentprov_backend.testing.transport import ScriptError, load_script, step_from_dict

    data = path.read_bytes()
    doc = json.loads(data.decode("utf-8")) if data.strip().startswith(b"{") else None
    if isinstance(doc, dict) and "agent" in doc:
        steps = doc["agent"] if role == "agent" else (doc.get("judges") or {}).get(role)
        if not isinstance(steps, list):
            raise ScriptError(f"the script has no steps for {role}")
        return [step_from_dict(step) for step in steps]
    if role != "agent":
        raise ScriptError(f"scripted judges need a combined script with judges.{role}")
    return load_script(path)


def _inner_transport(spec: ModelSpec, session_dir: Path, module: Any, role: str) -> Any:
    if spec.transport == "scripted":
        from agentprov_backend.testing.transport import ScriptedTransport

        return ScriptedTransport(scripted_steps(session_dir / str(spec.script), role), model=spec.model)
    from agentprov_backend.transport import default_async_inner_transport

    return default_async_inner_transport(module)


#: D-740: Inspect's retries per model call (``GenerateConfig.max_retries``), for the agent and every judge; the provider
#: SDK's own retries are off (model arg ``max_retries=0``), so one logical call is at most ``1 + MAX_RETRIES`` billed
#: responses. Equal to ``agentprov.cli.live.envs.INSPECT_MAX_RETRIES``, which T0's cell bound uses (a test checks).
MAX_RETRIES = 1


def build_model(spec: ModelSpec, observer: WireObserver, *, session_dir: Path, environ: Mapping[str, str],
                configured: Mapping[str, Any] | None = None, role: str = "agent") -> Any:
    """An Inspect ``Model`` for ``spec`` whose every exchange ``observer`` records."""
    from inspect_ai.model import GenerateConfig, get_model

    from agentprov_backend._http import sdk_httpx
    from agentprov_backend.transport import AsyncRecordingTransport

    module = sdk_httpx()
    transport = AsyncRecordingTransport(_inner_transport(spec, session_dir, module, role), observer, module=module)
    client = module.AsyncClient(transport=transport, timeout=600.0)
    if spec.transport == "scripted":
        base_url, key = SCRIPTED_BASE_URL, SCRIPTED_KEY
    else:
        base_url = str(spec.base_url)
        key = environ.get(str(spec.api_key_env), "") if spec.api_key_env else "no-key-lan-endpoint"  # D-698: keyless
        if not key:
            raise ValueError(f"the key variable {spec.api_key_env} is not set in the worker environment")
    config = GenerateConfig(**{**dict(configured or {}), "max_retries": MAX_RETRIES})
    # memoize=False (D-743): get_model's memo key omits the http_client (a non-JSON model arg), so a memoized call
    # would hand a judge on the agent's model the agent's Model (its exchanges recorded as the agent's), and a later
    # cell the earlier cell's Model, whose capture session is closed
    return get_model(inspect_model_name(spec), config=config, base_url=base_url, api_key=key, http_client=client,
                     memoize=False, max_retries=0)  # the SDK client's retries: off, Inspect's are the only ones (D-740)
