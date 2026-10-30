"""Wire recording of an Inspect cell (D-665 (b): recorded and stored, not mapped).

Every HTTP exchange of the agent's and the judges' provider clients passes through the shared async recording
transport (``agentprov_backend.transport.AsyncRecordingTransport``, D-656), whose observer is a :class:`WireObserver`
here. It writes ``capture/0.1`` events into the cell's capture session: ``llm.request`` (``role`` ``agent`` for the
agent, ``auxiliary`` for a judge; ``endpoint`` host and path; ``params.configured`` from the plan and
``params.transmitted`` read from the request body; the exact body as a blob after the capture redactor) and
``llm.response`` (``kept`` for a 2xx, ``error`` otherwise or on a transport exception; the body as a blob; the served
model, response id and finish reason when the body names them). There are no ``pass`` events: an Inspect cell has
no AgentDojo passes, and nothing maps this log (the ``.eval`` is the mapped artefact). The log is chain-verifiable
by ``agentprov_capture.verify`` and sits next to the ``.eval`` in the session.

If the observer raises before a request is sent (the redactor's fail-closed scan), the request is not sent (the
transport's guarantee): an exchange is never made unrecorded.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = ["TRANSMITTED_KEYS", "WireObserver"]

#: Request-body members recorded as ``params.transmitted`` (values as sent; anything else stays in the body blob).
TRANSMITTED_KEYS = ("model", "temperature", "top_p", "max_tokens", "max_completion_tokens", "seed", "stop",
                    "tool_choice", "parallel_tool_calls", "reasoning_effort", "n", "frequency_penalty",
                    "presence_penalty", "logprobs", "top_logprobs", "stream")


def _media(headers: Any) -> str:
    value = ""
    try:
        value = str(headers.get("content-type") or "")
    except Exception:  # noqa: BLE001 - an exotic headers object
        value = ""
    return value.split(";", 1)[0].strip() or "application/octet-stream"


def _json_object(body: bytes) -> Mapping[str, Any] | None:
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


class WireObserver:
    """``agentprov_backend.transport.WireObserver`` for one model (the agent or one judge role) of a cell."""

    def __init__(self, session: Any, *, role: str, actor: str, configured: Mapping[str, Any]) -> None:
        if role not in ("agent", "auxiliary"):
            raise ValueError("role must be agent or auxiliary")
        self.session = session
        self.role = role
        self.actor = actor
        self.configured = dict(configured)
        self.calls = 0

    def on_request(self, request: Any, body: bytes) -> object:
        call = self.session.next_call()
        url = request.url
        blob = self.session.put_blob(body, _media(request.headers))
        doc = _json_object(body) or {}
        transmitted = {k: doc[k] for k in TRANSMITTED_KEYS if k in doc}
        self.session.emit("llm.request", {
            "attempt": self.session.attempt, "call": call, "role": self.role,
            "endpoint": {"host": str(url.host), "path": str(url.path)},
            "params": {"configured": dict(self.configured), "transmitted": transmitted},
            "request": blob,
        }, actor=self.actor, in_pass=False)
        self.calls += 1
        return call

    def on_response(self, token: object, status: int, headers: Any, body: bytes) -> None:
        data: dict[str, Any] = {"call": str(token), "status": "kept" if 200 <= int(status) < 300 else "error",
                                "http_status": int(status), "response": self.session.put_blob(body, _media(headers))}
        doc = _json_object(body) or {}
        if isinstance(doc.get("model"), str) and doc["model"]:
            data["served_model"] = doc["model"]
        if isinstance(doc.get("id"), str) and doc["id"]:
            data["response_id"] = doc["id"]
        choices = doc.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict) \
                and isinstance(choices[0].get("finish_reason"), str):
            data["finish_reason"] = choices[0]["finish_reason"]
        self.session.emit("llm.response", data, actor=self.actor, in_pass=False)

    def on_error(self, token: object, exc: BaseException) -> None:
        self.session.emit("llm.response", {"call": str(token), "status": "error",
                                           "exception": {"type": type(exc).__name__, "message": str(exc)[:2000]}},
                          actor=self.actor, in_pass=False)
