"""Synthetic AgentDojo cells written as ``capture/0.1`` sessions (docs/architecture C.13, D.10.2), for the capture
mapper tests.

:class:`Cell` drives a fake stock pipeline: each pass starts a new message list (system, user), each agent turn is an
``llm.request``/``llm.response`` pair whose wire request is the stock 0.1.35 OpenAI rendering of the message list
(``_message_to_openai``: system as ``developer``, content blocks as text parts, a failed tool call's ``error`` as the
tool message content), and each tool call of a reply is a ``tool.dispatch``/``tool.result`` pair followed by the tool
message the executor appends. The pass ends with ``pass.end`` and the native message dump. Everything is synthetic.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from capture_support import (
    ENDPOINT,
    ENV_DIGEST,
    IDENTITY,
    INSTRUMENTATION,
    PARAMS,
    SESSION,
    TOOLS,
    Session,
    call,
    response,
    start_data,
    text,
)

#: A gateway_compat session declares the developer -> system rewrite (D.10.7).
INSTRUMENTATION_GATEWAY = [*copy.deepcopy(INSTRUMENTATION),
                           {"id": "agentdojo.role_rewrite_developer_to_system@1", "kind": "request_modifying",
                            "recorded": "full"}]

SYS = "You are a banking assistant."
PROMPT = "What is my balance?"


def wire(message: Mapping[str, Any]) -> dict[str, Any]:
    """The stock 0.1.35 rendering of a recorded message (openai_llm.py ``_message_to_openai``)."""
    role = message["role"]
    blocks = message.get("content")
    content = None if blocks is None else [{"type": "text", "text": b["content"] or ""} for b in blocks]
    if role == "system":
        return {"role": "developer", "content": content}
    if role == "user":
        return {"role": "user", "content": content}
    if role == "assistant":
        out: dict[str, Any] = {"role": "assistant", "content": content}
        if message.get("tool_calls"):
            out["tool_calls"] = [{"id": c["id"], "type": "function",
                                  "function": {"name": c["function"], "arguments": json.dumps(c["args"])}}
                                 for c in message["tool_calls"]]
        return out
    return {"role": "tool", "content": message["error"] or content, "tool_call_id": message["tool_call_id"],
            "name": message["tool_call"]["function"]}


@dataclass
class ToolOutcome:
    status: str = "ok"  # ok | error | invalid | denied
    result: str = "1810.0"
    error: str | None = None
    decided_by: str | None = None


@dataclass
class Cell:
    """One cell attempt as a capture session (``session`` is the UUIDv7)."""

    session: str = SESSION
    attack: str | None = None
    actors: Mapping[str, Any] | None = None
    instrumentation: Sequence[Mapping[str, Any]] = field(default_factory=lambda: copy.deepcopy(INSTRUMENTATION))
    s: Session = field(init=False)
    pass_index: int = field(init=False, default=-1)
    messages: list[dict[str, Any]] = field(init=False, default_factory=list)
    n_calls: int = field(init=False, default=0)
    n_occ: int = field(init=False, default=0)
    n_reply: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.s = Session(self.session)
        cell = {"benchmark": "agentdojo", "suite": "banking", "task_id": "user_task_0", "attack_id": self.attack,
                "attack_target_id": "injection_task_1" if self.attack else None, "defense_id": None, "attack_params": {}}
        data = start_data(self.session, cell=cell)
        if self.actors is not None:
            data["actors"] = dict(data["actors"], **self.actors)
        self.s.emit("session.start", data)
        self.s.emit("instrumentation", {"items": [dict(i) for i in self.instrumentation]})
        self.s.emit("identity", copy.deepcopy(IDENTITY))

    # ------------------------------------------------------------------------------------------ passes
    def start_pass(self, *, env: str = ENV_DIGEST) -> int:
        self.pass_index += 1
        self.messages = [{"role": "system", "content": text(SYS)}, {"role": "user", "content": text(PROMPT)}]
        self.s.emit("pass.start", {"env": {"sha256": env, "canon": "jcs-rfc8785"}}, pass_=self.pass_index)
        return self.pass_index

    def end_pass(self, *, aborted: bool = False, env: str = ENV_DIGEST, changed: bool = False,
                 as_logged: bool = False) -> None:
        """``as_logged``: the dump serialised as the harness writes it (``json.dumps``, insertion order), not JCS."""
        dump = json.dumps(self.messages).encode() if as_logged else self.messages
        self.s.emit("pass.end", {"aborted": aborted, "messages": self.s.blob(dump),
                                 "env": {"sha256": env, "canon": "jcs-rfc8785", "changed": changed}}, pass_=self.pass_index)

    def request(self, *, input_at: bool = True, n_messages: bool = True, retry_of: str | None = None,
                wire_messages: Sequence[Any] | None = None, redactions: Sequence[Mapping[str, Any]] = ()) -> str:
        cid = f"c{self.n_calls}"
        self.n_calls += 1
        body = {"model": "scripted-fake", "messages": list(wire_messages) if wire_messages is not None
                else [wire(m) for m in self.messages], "tools": TOOLS}
        data: dict[str, Any] = {"call": cid, "role": "agent", "attempt": 0, "endpoint": ENDPOINT, "params": PARAMS,
                                "request": self.s.blob(body)}
        if input_at:
            data["input_at"] = list(range(len(self.messages)))
        if n_messages:
            data["n_messages"] = len(self.messages)
        if retry_of is not None:
            data["retry_of"] = retry_of
        if redactions:
            data["redactions"] = [dict(r) for r in redactions]
        self.s.emit("llm.request", data, pass_=self.pass_index, actor="agent")
        return cid

    def reply(self, *, content: str | None = None, calls: Sequence[tuple[str, dict[str, Any]]] = (),
              outcomes: Sequence[ToolOutcome] = (), status: str = "kept", reason: str | None = None,
              raw_arguments: str | None = None, message_extra: Mapping[str, Any] | None = None, **request: Any) -> str:
        """One agent turn: request, response, and (for a kept reply) the assistant message and its tool calls."""
        cid = self.request(**request)
        made = []
        for function, args in calls:
            made.append(call(function, args, f"call_{self.n_reply}_{len(made)}"))
        self.n_reply += 1
        body = response(f"fake-{cid}", content=content, calls=made, finish="tool_calls" if made else "stop")
        if raw_arguments is not None:
            body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = raw_arguments
        if message_extra:  # provider members the stock element drops (reasoning, refusal)
            body["choices"][0]["message"].update(message_extra)
        data: dict[str, Any] = {"call": cid, "status": status, "response": self.s.blob(body),
                                "finish_reason": body["choices"][0]["finish_reason"], "served_model": "scripted-fake",
                                "response_id": body["id"], "usage": {"input_tokens": 10, "output_tokens": 5,
                                                                     "total_tokens": 15}}
        if reason is not None:
            data["reason"] = reason
        self.s.emit("llm.response", data, pass_=self.pass_index, actor="agent")
        if status != "kept":
            return cid
        assistant = {"role": "assistant", "content": None if content is None else text(content),
                     "tool_calls": made or None}
        self.messages.append(assistant)
        at = len(self.messages) - 1
        for j, made_call in enumerate(made):
            outcome = outcomes[j] if j < len(outcomes) else ToolOutcome()
            self.tool(at, j, made_call, outcome)
        return cid

    def tool(self, at: int, j: int, made_call: Mapping[str, Any], outcome: ToolOutcome) -> str:
        occ = f"o{self.n_occ}"
        self.n_occ += 1
        self.s.emit("tool.dispatch", {"occ": occ, "at": {"message": at, "call": j}, "provider_call_id": made_call["id"],
                                      "name": made_call["function"], "args": made_call["args"]},
                    pass_=self.pass_index, actor="env")
        result: dict[str, Any] = {"occ": occ, "status": outcome.status, "rendered": outcome.result,
                                  "model_visible": outcome.error or outcome.result, "error": outcome.error}
        if outcome.status == "ok":
            result.update(args_effective=made_call["args"], returned=outcome.result)
        if outcome.status == "denied":
            result["decided_by"] = outcome.decided_by
        self.s.emit("tool.result", result, pass_=self.pass_index, actor="env")
        failed = outcome.status != "ok"
        self.messages.append({"role": "tool", "content": text("" if failed else outcome.result),
                              "tool_call_id": made_call["id"], "tool_call": dict(made_call),
                              "error": outcome.error if failed else None})
        return occ

    def outcome(self, utility: bool = True, security: bool = True) -> None:
        security_origin = "harness_default" if self.attack is None else "checker"
        self.s.emit("outcome", {"judgements": [{"name": "utility", "value": utility, "origin": "checker"},
                                               {"name": "security", "value": security, "origin": security_origin}]})

    def close(self, status: str = "complete", appended_by: str = "worker") -> Session:
        self.s.close(status, appended_by)
        return self.s


def balance_cell(**kwargs: Any) -> Cell:
    """One pass: a tool call answered, then a final text reply; scored outcome."""
    cell = Cell(**kwargs)
    cell.start_pass()
    cell.reply(calls=[("get_balance", {})])
    cell.reply(content="Your balance is 1810.0.")
    cell.end_pass()
    cell.outcome()
    return cell
