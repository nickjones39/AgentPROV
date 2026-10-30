"""AgentDojo-dependent LLM elements: ``SpannedLLM`` and ``GatewayLLM`` (re-exported by ``agentprov_backend.gateway``).

``GatewayLLM`` is the D5 port of the AgentDojo-PROV baseline ``_CompatLLM`` (``agentdojo_prov/runtime.py:121-393`` at
``579a908``): the same request construction (``developer`` -> ``system`` role rewrite, RT-6; ``temperature or
NOT_GIVEN`` via the stock ``chat_completion_request``, RT-3; OpenRouter effort in ``extra_body``, other providers'
effort as ``reasoning_effort``; ``reasoning_details`` pass-back on OpenRouter, reset per pass, RT-5), the same retry
policy (up to 8 attempts; 429 back-off 30 s doubling to 120 s plus 0-15 s; connection errors and up to 3 outer 5xx
retries 10-20 s; 4xx re-raised; malformed tool-call JSON re-asked at once; upstream failures -- no ``choices`` or
``finish_reason == "error"`` -- re-asked after 10-20 s, the last kept after 8), the same client settings (timeout
``LLM_TIMEOUT_S`` default 180 s, SDK ``max_retries=0``) and the same per-call logs; reasoning never enters the scored
message (RT-1). What changes is only what is *recorded*: every wire exchange goes through the recording transport, and
every reply the port does not keep is marked ``discarded`` with its reason (fixes D2/D5 of the capture audit). The
sleeps and the jitter source are injectable for tests; their values are the baseline's.
"""

from __future__ import annotations

import os
import random
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

import openai
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.llms.openai_llm import (
    OpenAILLM,
    _function_to_openai,
    _message_to_openai,
    _openai_to_assistant_message,
    chat_completion_request,
)
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.types import ChatMessage
from openai._types import NOT_GIVEN
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_random_exponential

from agentprov_backend._jsonval import escape_text

__all__ = [
    "GATEWAY_ITEMS",
    "GatewayLLM",
    "REASONING_EFFORTS",
    "SpannedLLM",
    "reasoning_text",
    "upstream_failure",
]

#: The set both providers document (baseline runtime.py:54).
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

ITEM_MALFORMED = "agentdojo.retry_malformed_tool_json@1"
ITEM_UPSTREAM = "agentdojo.retry_upstream_failure@1"
ITEM_BACKOFF = "agentdojo.http_backoff@1"
GATEWAY_ITEMS = (ITEM_MALFORMED, ITEM_UPSTREAM, ITEM_BACKOFF)


def _diag(message: str) -> None:
    """The port's progress lines (the baseline printed them); on stderr, never on the protocol channel.

    A line can embed provider-controlled text (``upstream_failure`` quotes the provider's ``error`` member), so control
    characters, escape sequences and bidirectional or tag characters are written as ``\\uXXXX`` escapes before the line
    reaches a terminal (escaping audit F-07). A progress line is one line, so a line break in it is escaped too."""
    sys.stderr.write(escape_text(message, limit=2000) + "\n")
    sys.stderr.flush()


class SpannedLLM(BasePipelineElement):
    """The ``LlmSpan(llm)`` pipeline element of D.10.5: opens an ``LlmSpan`` around each call of ``inner``. It passes
    every argument and every return value through unchanged."""

    def __init__(self, inner: BasePipelineElement, session: Any, *, role: str = "agent", actor: str = "agent",
                 detached: bool = False) -> None:
        self.inner = inner
        self.session = session
        self.role = role
        self.actor = actor
        #: the element is called with messages that are not the pass's list (a defence's own conversation, MELON's
        #: masked re-run): the span records no positions, and a note names the call (D-670)
        self.detached = detached
        self.name = getattr(inner, "name", None)
        self.last_calls: list[str] = []

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),  # noqa: B008 - the stock BasePipelineElement.query signature
        messages: Sequence[ChatMessage] = [],  # noqa: B006
        extra_args: dict = {},  # noqa: B006
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        if self.detached:
            with self.session.span(self.role, self.actor, ()) as span:
                out = self.inner.query(query, runtime, env, messages, extra_args)
            self.last_calls = list(span.calls)
            self.session.note("agentdojo", "defence_detached_input", {"actor": self.actor, "calls": list(span.calls),
                                                                       "n_messages": len(messages)})
            return out
        self.session.observe_messages(messages)
        with self.session.span(self.role, self.actor, messages) as span:
            out = self.inner.query(query, runtime, env, messages, extra_args)
        self.last_calls = list(span.calls)  # the wire calls of this invocation (a defence recorder names them)
        self.session.observe_messages(out[3])
        return out


def _message_extras(message: Any) -> dict:
    extra = getattr(message, "model_extra", None)
    return dict(extra) if isinstance(extra, dict) else {}


def reasoning_text(message: Any) -> str | None:
    """Reasoning text a provider returned alongside the reply (baseline ``_reasoning_text``)."""
    extras = _message_extras(message)
    for key in ("reasoning", "reasoning_content"):
        value = extras.get(key, getattr(message, key, None))
        if isinstance(value, str) and value:
            return value
    details = extras.get("reasoning_details")
    if isinstance(details, list):
        parts = [d.get("text") or d.get("summary") or "" for d in details if isinstance(d, dict)]
        text = "".join(p for p in parts if isinstance(p, str))
        return text or None
    return None


def upstream_failure(completion: Any) -> str | None:
    """Why a completion is a provider failure rather than a model reply (baseline ``_upstream_failure``)."""
    choices = getattr(completion, "choices", None)
    if not choices:
        error = (getattr(completion, "model_extra", None) or {}).get("error")
        return f"no choices returned: {error}" if error else "no choices returned"
    if getattr(choices[0], "finish_reason", None) == "error":
        return "finish_reason=error"
    return None


class GatewayLLM(OpenAILLM):
    """``gateway_compat``: the baseline ``_CompatLLM``, recorded (see the module docstring)."""

    _MAX_ATTEMPTS = 8
    _BASE_WAIT = 30
    _MAX_WAIT = 120
    _MAX_SERVER_ERRORS = 3

    def __init__(
        self,
        client: openai.OpenAI,
        model: str,
        *,
        base_url: str,
        effort: str | None = None,
        passback: bool = True,
        temperature: float | None = 0.0,
        session: Any = None,
        sleep: Callable[[float], None] | None = None,
        uniform: Callable[[float, float], float] | None = None,
    ) -> None:
        super().__init__(client, model, temperature=temperature)
        if effort is not None and effort not in REASONING_EFFORTS:
            raise ValueError(f"reasoning effort {effort!r}; use one of {REASONING_EFFORTS}")
        self.base_url = base_url
        self.is_openrouter = "openrouter.ai" in base_url
        self.effort = effort
        self.passback = passback
        self.session = session
        self._sleep = sleep if sleep is not None else (lambda s: time.sleep(s))
        self._uniform = uniform if uniform is not None else (lambda a, b: random.uniform(a, b))
        # the baseline's per-trace logs (kept for parity; the capture log is the evidence)
        self.usage_log: list[dict] = []
        self.n_calls: int = 0
        self.finish_reasons: list = []
        self.reasoning_log: list[str | None] = []
        self.refusal_log: list[str | None] = []
        self._reasoning_details: list[list | None] = []
        self.reasoning_effort_setting = effort
        self.upstream_errors: list[str] = []
        self.response_log: list[dict] = []
        self.malformed_tool_calls: list[str] = []
        self.discarded_usage: list[dict] = []
        if effort is not None and not self.is_openrouter:
            self.reasoning_effort = effort  # agentdojo's request sends it as reasoning_effort
        self._request_with_reasoning = retry(
            wait=wait_random_exponential(multiplier=1, max=40),
            stop=stop_after_attempt(3),
            reraise=True,
            retry=retry_if_not_exception_type((openai.BadRequestError, openai.UnprocessableEntityError)),
        )(self._raw_request_with_reasoning)

    @staticmethod
    def client_settings() -> dict[str, Any]:
        """The SDK client settings of the baseline (``runtime.py:164-166``)."""
        return {"timeout": float(os.environ.get("LLM_TIMEOUT_S", "180")), "max_retries": 0}

    def _raw_request_with_reasoning(self, model: str, messages: Any, tools: Any, temperature: Any) -> Any:
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools or NOT_GIVEN,
            tool_choice="auto" if tools else NOT_GIVEN,
            temperature=temperature or NOT_GIVEN,
            extra_body={"reasoning": {"effort": self.effort}},
        )

    # --------------------------------------------------------------- recording helpers (no behaviour)

    def _span(self) -> Any:
        return None if self.session is None else self.session.current_span

    def _mark_kept(self) -> None:
        span = self._span()
        if span is not None and span.pending_call is not None:
            span.mark_kept(span.pending_call)

    def _mark_discarded(self, reason: str) -> None:
        span = self._span()
        if span is not None and span.pending_call is not None:
            span.mark_discarded(span.pending_call, reason)

    def _count(self, item: str, key: str) -> None:
        if self.session is not None:
            self.session.count(item, key)

    def _note_discarded(self, completion: Any) -> None:
        u = getattr(completion, "usage", None)
        if u is not None:
            self.discarded_usage.append({
                "prompt_tokens": getattr(u, "prompt_tokens", None),
                "completion_tokens": getattr(u, "completion_tokens", None)})

    # --------------------------------------------------------------- the port of _CompatLLM.query

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),  # noqa: B008 - the stock BasePipelineElement.query signature
        messages: Sequence[ChatMessage] = [],  # noqa: B006
        extra_args: dict = {},  # noqa: B006
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        openai_messages = [_message_to_openai(m, self.model) for m in messages]
        openai_messages = [
            {**m, "role": "system"} if m.get("role") == "developer" else m
            for m in openai_messages
        ]
        if not any(m.get("role") == "assistant" for m in openai_messages):
            self._reasoning_details = []
        if self.passback and any(self._reasoning_details):
            k = 0
            for i, m in enumerate(openai_messages):
                if m.get("role") != "assistant":
                    continue
                if k < len(self._reasoning_details) and self._reasoning_details[k]:
                    openai_messages[i] = {**m, "reasoning_details": self._reasoning_details[k]}
                k += 1
        openai_tools = [_function_to_openai(t) for t in runtime.functions.values()]

        server_errors = 0
        output = None
        parse_error: Exception | None = None
        completion: Any = None
        for attempt in range(self._MAX_ATTEMPTS):
            output, parse_error = None, None
            try:
                if self.effort is not None and self.is_openrouter:
                    completion = self._request_with_reasoning(
                        self.model, openai_messages, openai_tools, self.temperature,
                    )
                else:
                    completion = chat_completion_request(
                        self.client, self.model, openai_messages, openai_tools,
                        self.reasoning_effort, self.temperature,
                    )
            except openai.RateLimitError as exc:
                if attempt == self._MAX_ATTEMPTS - 1:
                    raise
                wait = min(self._BASE_WAIT * (2 ** attempt), self._MAX_WAIT) + self._uniform(0, 15)
                _diag(f"[rate-limit] attempt {attempt + 1}/{self._MAX_ATTEMPTS}: "
                      f"sleeping {wait:.0f}s  ({type(exc).__name__})")
                self._count(ITEM_BACKOFF, "retried")
                self._sleep(wait)
                continue
            except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                if attempt == self._MAX_ATTEMPTS - 1:
                    raise
                wait = 10 + self._uniform(0, 10)
                _diag(f"[conn-error] attempt {attempt + 1}/{self._MAX_ATTEMPTS}: "
                      f"sleeping {wait:.0f}s  ({type(exc).__name__})")
                self._count(ITEM_BACKOFF, "retried")
                self._sleep(wait)
                continue
            except openai.APIStatusError as exc:
                server_errors += 1
                if (exc.status_code < 500 or attempt == self._MAX_ATTEMPTS - 1
                        or server_errors >= self._MAX_SERVER_ERRORS):
                    raise
                wait = 10 + self._uniform(0, 10)
                _diag(f"[server-error] attempt {attempt + 1}/{self._MAX_ATTEMPTS}: "
                      f"sleeping {wait:.0f}s  ({exc.status_code})")
                self._count(ITEM_BACKOFF, "retried")
                self._sleep(wait)
                continue
            failure = upstream_failure(completion)
            if failure is None:
                try:
                    output = _openai_to_assistant_message(completion.choices[0].message)
                except (ValueError, TypeError) as exc:   # arguments that are not JSON
                    parse_error = exc
                    failure = f"malformed tool call: {exc!r}"[:200]
            if failure is None:
                self._mark_kept()
                break
            if parse_error is not None:
                self.malformed_tool_calls.append(failure)
                self._note_discarded(completion)
                self._mark_discarded(failure)
                self._count(ITEM_MALFORMED, "resampled")
                if attempt == self._MAX_ATTEMPTS - 1:
                    raise parse_error      # nothing to keep: the reply cannot be parsed
                continue    # a fresh sample, not an overloaded provider: ask again at once
            if attempt == self._MAX_ATTEMPTS - 1:
                if not completion.choices:
                    self._mark_discarded(failure)
                    raise RuntimeError(f"provider failed {self._MAX_ATTEMPTS} times: {failure}")
                self._mark_kept()
                break   # keep the last reply; finish_reasons flags it abnormal_finish
            self.upstream_errors.append(failure)
            self._note_discarded(completion)
            self._mark_discarded(failure)
            self._count(ITEM_UPSTREAM, "retried")
            wait = 10 + self._uniform(0, 10)
            _diag(f"[upstream-error] attempt {attempt + 1}/{self._MAX_ATTEMPTS}: "
                  f"sleeping {wait:.0f}s  ({failure})")
            self._sleep(wait)

        message = completion.choices[0].message
        if output is None:       # a kept reply after provider failures: parsed here
            output = _openai_to_assistant_message(message)
        try:
            reasoning = reasoning_text(message)
            details = _message_extras(message).get("reasoning_details")
        except Exception:  # noqa: BLE001
            reasoning, details = None, None
        self.n_calls += 1
        extra = getattr(completion, "model_extra", None) or {}
        self.response_log.append({"model": getattr(completion, "model", None),
                                  "provider": extra.get("provider"),
                                  "system_fingerprint": getattr(completion, "system_fingerprint", None)})
        self.reasoning_log.append(reasoning)
        self.refusal_log.append(getattr(message, "refusal", None) or None)
        self._reasoning_details.append(details if isinstance(details, list) and details else None)
        try:
            u = getattr(completion, "usage", None)
            if u is not None:
                ctd = getattr(u, "completion_tokens_details", None)
                ptd = getattr(u, "prompt_tokens_details", None)
                self.usage_log.append({
                    "prompt_tokens": getattr(u, "prompt_tokens", None),
                    "completion_tokens": getattr(u, "completion_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                    "reasoning_tokens": getattr(ctd, "reasoning_tokens", None),
                    "cached_tokens": getattr(ptd, "cached_tokens", None),
                })
            self.finish_reasons.append(completion.choices[0].finish_reason)
        except Exception:  # noqa: BLE001
            pass
        return query, runtime, env, [*messages, output], extra_args
