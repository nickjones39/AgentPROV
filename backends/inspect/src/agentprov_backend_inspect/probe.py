"""The D.10.9 preflight probe of an Inspect backend (D-742).

The shared probe (``agentprov_backend.runner.run_probe``) sends its canned request through AgentDojo's LLM element, which
an Inspect environment does not have. This probe sends the same request (``PROBE_PROMPT`` as the system message,
``"Probe."`` as the user message, the two probe tools) through the path a cell uses: an Inspect ``Model`` built by
:func:`agentprov_backend_inspect.models.build_model` (Inspect's OpenAI-compatible provider, ``max_retries`` as in a
cell, the shared async recording transport), recorded by a :class:`~agentprov_backend_inspect.wire.WireObserver` with
``role: agent``. Its results have the shared probe's shape and are judged by the shared verdict functions:

* ``reachable``, ``http_status``: from the recorded ``llm.response`` events;
* ``roles``/``roles_reason``/``roles_accepted``: ``runner.roles_verdict`` of the last reply's recorded body (D-291);
* ``params``: the agent's configured parameters and those the request transmitted. An Inspect cell transmits none of
  the agent's sampling parameters (its ``GenerateConfig`` sets ``max_retries`` only), so the probe configures none
  either, and a configured parameter shows as not transmitted (A3), as it would be in a cell;
* ``tool_calls``: ``structured`` (the reply carries tool calls), ``text_encoded`` (the text names a probe tool or has a
  function tag; A4), ``none`` or ``error``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov_backend_inspect.plan import ModelSpec

__all__ = ["PROBE_ITEM", "probe_tools", "run_probe"]

PROBE_ITEM: dict[str, Any] = {"id": "inspect.preflight_probe@1", "kind": "harness_policy", "recorded": "full",
                              "detail": "the D.10.9 canned two-tool request through the cell's Inspect model and "
                                        "recording transport; roles judged from the reply (D-291, D-742)"}

#: the probe's agent parameters a cell would transmit if it configured them (the shared probe's A3 list)
_A3_KEYS = ("temperature", "reasoning_effort", "top_p", "seed", "max_tokens")


def probe_tools() -> list[Any]:
    """The two probe tools as Inspect ``ToolInfo`` (the shared probe's ``get_probe_value`` and ``get_probe_time``)."""
    from inspect_ai.tool import ToolInfo, ToolParam, ToolParams

    return [
        ToolInfo(name="get_probe_value", description="Return the probe value for a key.",
                 parameters=ToolParams(properties={"key": ToolParam(type="string", description="the key to look up.")},
                                       required=["key"])),
        ToolInfo(name="get_probe_time", description="Return a fixed probe time.", parameters=ToolParams()),
    ]


def _classify(output: Any) -> str:
    from agentprov_backend.runner import TEXT_TOOL_CALL_MARKS

    message = output.message
    if message.tool_calls:
        return "structured"
    text = message.text or ""
    named = any(name in text for name in ("get_probe_value", "get_probe_time"))
    marked = any(mark in text for mark in TEXT_TOOL_CALL_MARKS)
    return "text_encoded" if named or marked else "none"


def run_probe(spec: ModelSpec, params: Mapping[str, Any], session: Any, *, session_dir: Path,
              environ: Mapping[str, str]) -> dict[str, Any]:
    """Send the probe request for ``spec`` into the started capture ``session``; return the shared probe's results
    (without ``status`` and ``capture_head``, which the caller adds when it closes the session)."""
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser

    from agentprov_backend.runner import PROBE_PROMPT, _blob_bytes, _events, roles_verdict
    from agentprov_backend_inspect.models import build_model
    from agentprov_backend_inspect.wire import WireObserver

    result: dict[str, Any] = {"reachable": False, "roles_accepted": False, "roles": "unknown", "roles_reason": "no_reply",
                              "http_status": None,
                              "params": {"configured": dict(params), "transmitted": {}, "not_transmitted": []},
                              "tool_calls": "error"}
    model = build_model(spec, WireObserver(session, role="agent", actor="agent", configured={}),
                        session_dir=session_dir, environ=environ)
    messages = [ChatMessageSystem(content=PROBE_PROMPT), ChatMessageUser(content="Probe.")]
    try:
        output = asyncio.run(model.generate(messages, tools=probe_tools()))
        if output.error:
            raise RuntimeError(f"the model reported an error: {str(output.error)[:500]}")
        result["tool_calls"] = _classify(output)
    except Exception as exc:  # noqa: BLE001 - recorded in the probe session; the verdict comes from the wire
        session.record_error(exc, fatal=False, where="probe")
    exchanges = [e for e in _events(session) if e["type"] in ("llm.request", "llm.response")]
    replies = [e["data"] for e in exchanges if e["type"] == "llm.response" and isinstance(e["data"].get("http_status"), int)]
    result["reachable"] = bool(replies)
    last = replies[-1] if replies else None
    result["http_status"] = None if last is None else last["http_status"]
    body = None if last is None else _blob_bytes(session, last.get("response"))
    result["roles"], result["roles_reason"] = roles_verdict(result["http_status"], body)
    result["roles_accepted"] = result["roles"] == "accepted"
    requests = [e for e in exchanges if e["type"] == "llm.request"]
    if requests:
        transmitted = requests[-1]["data"]["params"]["transmitted"]
        result["params"]["transmitted"] = transmitted
        result["params"]["not_transmitted"] = sorted(k for k in params if k in _A3_KEYS and k not in transmitted)
    return result
