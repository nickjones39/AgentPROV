"""The two wire variants of ``wirelog.request_response``, normalised to one block model (docs/architecture D.20.2; D-283).

A request log is a JSON array of request bodies as the harness sent them, in order; a response log the array of the
decoded responses. Two body formats occur:

* ``bedrock-converse`` (AWS Bedrock Converse): ``{model, messages, toolConfig, inferenceConfig, system?}``; content blocks
  ``{"text"}``, ``{"toolUse": {toolUseId, name, input}}``, ``{"toolResult": {toolUseId, content[], status?}}``; responses
  ``{output: {message}, stopReason, usage, metrics}``;
* ``anthropic-messages`` (the Anthropic Messages body): ``{model, messages, tools, max_tokens, system?}``; user content a
  string or blocks ``{type: text|tool_use|tool_result, ...}``; responses ``{id, model, role, content[], stop_reason,
  usage, ...}``.

The ``model`` member of a logged request is the harness's own addition (the wire carries it in the URL). Nothing here
interprets content: a block is classified by its keys and kept verbatim (``raw``), with the JSON pointer it came from.
Shape errors raise :class:`~agentprov.errors.MalformedArtefact`. Standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from agentprov.adapters.wirelog import VARIANT_ANTHROPIC, VARIANT_CONVERSE
from agentprov.aer.canon import json_pointer
from agentprov.errors import MalformedArtefact

__all__ = [
    "Block",
    "WireMessage",
    "WireRequest",
    "WireResponse",
    "detect_response_variant",
    "detect_variant",
    "parse_requests",
    "parse_responses",
]

BlockKind = Literal["text", "tool_use", "tool_result", "other"]

#: Usage keys of each variant mapped to the AER ``Usage`` members (C.3.12); every other usage member is kept in ``ext``.
USAGE_KEYS: Final[Mapping[str, Mapping[str, str]]] = {
    VARIANT_CONVERSE: {"inputTokens": "input_tokens", "outputTokens": "output_tokens", "totalTokens": "total_tokens",
                       "cacheReadInputTokens": "cache_read_tokens", "cacheWriteInputTokens": "cache_write_tokens"},
    VARIANT_ANTHROPIC: {"input_tokens": "input_tokens", "output_tokens": "output_tokens",
                        "cache_read_input_tokens": "cache_read_tokens",
                        "cache_creation_input_tokens": "cache_write_tokens"},
}


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


@dataclass(frozen=True, slots=True)
class Block:
    """One content block. ``pointer`` is relative to the message object; ``extra`` holds members the AER part has no slot
    for (Anthropic ``citations``, ``caller``; a Converse ``toolResult`` ``status``)."""

    kind: BlockKind
    pointer: str
    raw: Any
    text: str | None = None
    name: Any = None
    input: Any = None
    call_id: Any = None
    content: Any = None
    type: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WireMessage:
    """A conversation item: its role verbatim, its blocks, and the object as logged (compared by JCS across requests)."""

    role: Any
    blocks: tuple[Block, ...]
    raw: Any
    string_content: bool = False


@dataclass(frozen=True, slots=True)
class WireRequest:
    index: int
    model: Any
    messages: tuple[WireMessage, ...]
    system: Any  # the logged ``system`` member verbatim, or None when absent
    system_texts: tuple[str, ...] | None
    tools: Any
    tools_key: str | None
    params: Mapping[str, Any]  # transmitted generation parameters (``inferenceConfig`` or ``max_tokens``)
    extra: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class WireResponse:
    index: int
    message: WireMessage | None
    message_pointer: str
    stop_reason: Any
    usage: Mapping[str, int]
    usage_extra: Mapping[str, Any]
    latency_ms: Any
    served_model: Any
    response_id: Any
    extra: Mapping[str, Any]


def detect_variant(value: object) -> str | None:
    """The wire variant of a request log, or ``None`` when ``value`` is not one (total; never raises)."""
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(r, dict) and isinstance(r.get("messages"), list) and isinstance(r.get("model"), str)
               for r in value):
        return None
    if all(("inferenceConfig" in r or "toolConfig" in r) and "max_tokens" not in r for r in value):
        return VARIANT_CONVERSE
    if all("max_tokens" in r and "inferenceConfig" not in r and "toolConfig" not in r for r in value):
        return VARIANT_ANTHROPIC
    return None


def detect_response_variant(value: object) -> str | None:
    """The wire variant of a response log (``stopReason`` for Converse, ``stop_reason`` for Anthropic Messages), or
    ``None`` when ``value`` is not one (total; never raises)."""
    if not isinstance(value, list) or not value or not all(isinstance(r, dict) for r in value):
        return None
    if all("stopReason" in r and "stop_reason" not in r for r in value):
        return VARIANT_CONVERSE
    if all("stop_reason" in r and "content" in r and "stopReason" not in r for r in value):
        return VARIANT_ANTHROPIC
    return None


# ------------------------------------------------------------------------------------------------ blocks
def _converse_block(raw: object, pointer: str) -> Block:
    if not isinstance(raw, dict) or len(raw) != 1:
        if isinstance(raw, dict):
            return Block("other", pointer, raw, type="wirelog.multi_key_block")
        raise MalformedArtefact("a Converse content block is not an object")
    (key, body), = raw.items()
    if key == "text" and isinstance(body, str):
        return Block("text", pointer, raw, text=body)
    if key == "toolUse" and isinstance(body, dict) and {"toolUseId", "name", "input"} <= set(body):
        extra = {k: v for k, v in body.items() if k not in ("toolUseId", "name", "input")}
        return Block("tool_use", pointer, raw, name=body["name"], input=body["input"], call_id=body["toolUseId"],
                     extra=extra)
    if key == "toolResult" and isinstance(body, dict) and {"toolUseId", "content"} <= set(body):
        extra = {k: v for k, v in body.items() if k not in ("toolUseId", "content")}
        return Block("tool_result", pointer, raw, call_id=body["toolUseId"], content=body["content"], extra=extra)
    return Block("other", pointer, raw, type=key)


def _anthropic_block(raw: object, pointer: str) -> Block:
    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
        raise MalformedArtefact("an Anthropic content block is not a typed object")
    kind = raw["type"]
    if kind == "text" and isinstance(raw.get("text"), str):
        return Block("text", pointer, raw, text=raw["text"], extra={k: v for k, v in raw.items() if k not in ("type", "text")})
    if kind == "tool_use" and {"id", "name", "input"} <= set(raw):
        extra = {k: v for k, v in raw.items() if k not in ("type", "id", "name", "input")}
        return Block("tool_use", pointer, raw, name=raw["name"], input=raw["input"], call_id=raw["id"], extra=extra)
    if kind == "tool_result" and {"tool_use_id", "content"} <= set(raw):
        extra = {k: v for k, v in raw.items() if k not in ("type", "tool_use_id", "content")}
        return Block("tool_result", pointer, raw, call_id=raw["tool_use_id"], content=raw["content"], extra=extra)
    return Block("other", pointer, raw, type=kind)


def _message(raw: object, variant: str) -> WireMessage:
    if not isinstance(raw, dict) or "role" not in raw or "content" not in raw:
        raise MalformedArtefact("a logged message is not an object with role and content")
    content = raw["content"]
    if variant == VARIANT_ANTHROPIC and isinstance(content, str):
        return WireMessage(raw["role"], (Block("text", "/content", content, text=content),), raw, string_content=True)
    if not isinstance(content, list):
        raise MalformedArtefact("a logged message's content is not an array")
    parse = _converse_block if variant == VARIANT_CONVERSE else _anthropic_block
    return WireMessage(raw["role"], tuple(parse(b, _p("content", k)) for k, b in enumerate(content)), raw)


def _system_texts(system: object, variant: str) -> tuple[str, ...] | None:
    """The system prompt's text blocks, or ``None`` when its shape is not a list of text blocks (kept verbatim then)."""
    if isinstance(system, str) and variant == VARIANT_ANTHROPIC:
        return (system,)
    if not isinstance(system, list):
        return None
    out: list[str] = []
    for block in system:
        if variant == VARIANT_CONVERSE and isinstance(block, dict) and set(block) == {"text"} and isinstance(block["text"], str):
            out.append(block["text"])
        elif variant == VARIANT_ANTHROPIC and isinstance(block, dict) and block.get("type") == "text" \
                and isinstance(block.get("text"), str):
            out.append(block["text"])
        else:
            return None
    return tuple(out)


# ------------------------------------------------------------------------------------------------ logs
def parse_requests(value: object, variant: str) -> list[WireRequest]:
    """The request log ``value`` as :class:`WireRequest` objects (variant ``variant``)."""
    if detect_variant(value) != variant:
        raise MalformedArtefact(f"the request log is not a {variant} log")
    assert isinstance(value, list)
    out: list[WireRequest] = []
    for i, body in enumerate(value):
        if variant == VARIANT_CONVERSE:
            known = ("model", "messages", "system", "toolConfig", "inferenceConfig")
            tools_key = "toolConfig" if "toolConfig" in body else None
            params = {"inferenceConfig": body["inferenceConfig"]} if "inferenceConfig" in body else {}
        else:
            known = ("model", "messages", "system", "tools", "max_tokens")
            tools_key = "tools" if "tools" in body else None
            params = {"max_tokens": body["max_tokens"]}
        system = body.get("system")
        out.append(WireRequest(
            index=i,
            model=body["model"],
            messages=tuple(_message(m, variant) for m in body["messages"]),
            system=system,
            system_texts=_system_texts(system, variant) if "system" in body else None,
            tools=body.get(tools_key) if tools_key is not None else None,
            tools_key=tools_key,
            params=params,
            extra={k: v for k, v in body.items() if k not in known},
        ))
    return out


def _usage(raw: object, variant: str) -> tuple[dict[str, int], dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}, ({"usage": raw} if raw is not None else {})
    table = USAGE_KEYS[variant]
    usage: dict[str, int] = {}
    extra: dict[str, Any] = {}
    for key, val in raw.items():
        name = table.get(key)
        if name is not None and isinstance(val, int) and not isinstance(val, bool) and val >= 0:
            usage[name] = val
        else:
            extra[key] = val
    return usage, extra


def parse_responses(value: object, variant: str) -> list[WireResponse]:
    """The response log ``value`` as :class:`WireResponse` objects (variant ``variant``)."""
    if detect_response_variant(value) != variant:
        raise MalformedArtefact(f"the response log is not a {variant} log")
    assert isinstance(value, list)
    out: list[WireResponse] = []
    for i, body in enumerate(value):
        if variant == VARIANT_CONVERSE:
            output = body.get("output")
            raw_message = output.get("message") if isinstance(output, dict) else None
            message = _message(raw_message, variant) if raw_message is not None else None
            usage, usage_extra = _usage(body.get("usage"), variant)
            metrics = body.get("metrics")
            latency = metrics.get("latencyMs") if isinstance(metrics, dict) else None
            known: Sequence[str] = ("output", "stopReason", "usage", "metrics")
            extra = {k: v for k, v in body.items() if k not in known}
            if isinstance(metrics, dict) and set(metrics) - {"latencyMs"}:
                extra["metrics"] = {k: v for k, v in metrics.items() if k != "latencyMs"}
            out.append(WireResponse(i, message, "/output/message", body.get("stopReason"), usage, usage_extra, latency,
                                    None, None, extra))
        else:
            raw_message = {"role": body.get("role"), "content": body.get("content")} if "content" in body else None
            message = _message(raw_message, variant) if raw_message is not None else None
            usage, usage_extra = _usage(body.get("usage"), variant)
            known = ("id", "model", "role", "content", "stop_reason", "usage")
            out.append(WireResponse(i, message, "", body.get("stop_reason"), usage, usage_extra, None, body.get("model"),
                                    body.get("id"), {k: v for k, v in body.items() if k not in known}))
    return out


def echo_form(response: WireResponse, variant: str) -> Any:
    """The object a later request carries when it echoes ``response``'s message (the comparison target of D-281)."""
    if response.message is None:
        return None
    if variant == VARIANT_CONVERSE:
        return response.message.raw
    return {"role": response.message.raw["role"], "content": response.message.raw["content"]}
