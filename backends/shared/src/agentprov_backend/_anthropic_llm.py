"""``AnthropicPortLLM``: AgentDojo 0.1.35's stock ``AnthropicLLM``, ported to the locked ``anthropic`` SDK (D-656).

Why a port. ``anthropic`` 1.x (1.11.0 in both backend locks; agentdojo declares ``anthropic>=0.47.0``) has no
``temperature`` parameter on ``messages.stream``, and the stock ``chat_completion_request`` always passes
``temperature=`` (``NOT_GIVEN`` when unset), so the stock element raises ``TypeError`` before anything is sent. The
user chose a declared port over pinning an older SDK (2026-10-22).

What changes, and only this. :func:`chat_completion_request` sends ``temperature`` through the SDK's ``extra_body``
when it is not ``None`` (the stock code sends it as a parameter when not ``None``) and not at all otherwise; the JSON
member then follows the SDK-built members instead of sitting among them, so the request is the same JSON object as
the stock element would send on an SDK with the parameter, not the same byte order. :meth:`AnthropicPortLLM.query` is
the stock ``query`` calling that function. Everything else is the stock code, imported, not copied: the client
conversion, the conversation and tool rendering (``_conversation_to_anthropic``, ``_function_to_anthropic``), the
reply parsing (``_anthropic_to_assistant_message``), the tenacity policy and the streaming call. A test compares both
functions with the stock source by AST, so any other drift fails (``backends/agentdojo/tests``). Declared as the
``behaviour_preserving`` instrumentation item ``agentdojo.anthropic_element_port@1``.

Imported lazily (it needs ``agentdojo`` and ``anthropic``); ``agentprov_backend`` never imports it at module load.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence

from agentdojo.agent_pipeline.llms.anthropic_llm import (
    AnthropicLLM,
    _anthropic_to_assistant_message,
    _conversation_to_anthropic,
    _function_to_anthropic,
)
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.types import ChatMessage
from anthropic import NOT_GIVEN, AsyncAnthropic, BadRequestError
from anthropic.types import Message as AnthropicMessage
from anthropic.types import MessageParam, ToolParam
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_random_exponential

__all__ = ["PORT_ITEM", "AnthropicPortLLM", "chat_completion_request"]

PORT_ITEM = "agentdojo.anthropic_element_port@1"


@retry(
    wait=wait_random_exponential(multiplier=1, max=40),
    stop=stop_after_attempt(3),
    retry=retry_if_not_exception_type(BadRequestError),
)
async def chat_completion_request(
    client: AsyncAnthropic,
    model: str,
    messages: list[MessageParam],
    tools: list[ToolParam],
    max_tokens: int,
    system_prompt: str | None = None,
    temperature: float | None = 0.0,
    thinking_budget_tokens: int | None = None,
) -> AnthropicMessage:
    async with client.messages.stream(
        model=model,
        messages=messages,
        tools=tools or NOT_GIVEN,
        max_tokens=max_tokens,
        system=system_prompt or NOT_GIVEN,
        extra_body={"temperature": temperature} if temperature is not None else None,
        thinking={"type": "enabled", "budget_tokens": thinking_budget_tokens} if thinking_budget_tokens else NOT_GIVEN,
    ) as stream:
        return await stream.get_final_message()


class AnthropicPortLLM(AnthropicLLM):
    """The stock ``AnthropicLLM`` whose ``query`` calls the ported :func:`chat_completion_request`."""

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),  # noqa: B008 - the stock signature
        messages: Sequence[ChatMessage] = [],  # noqa: B006
        extra_args: dict = {},  # noqa: B006
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        system_prompt, anthropic_messages = _conversation_to_anthropic(messages)
        if "claude-3-sonnet" in self.model or "claude-3-haiku" in self.model:
            system_prompt = f"{self._COT_PROMPT}\n\n{system_prompt}"
        anthropic_tools = [_function_to_anthropic(tool) for tool in runtime.functions.values()]
        completion = asyncio.run(
            chat_completion_request(
                self.client,
                self.model,
                anthropic_messages,
                anthropic_tools,
                max_tokens=self._MAX_TOKENS,
                system_prompt=system_prompt,
                temperature=self.temperature,
                thinking_budget_tokens=self.thinking_budget_tokens,
            )
        )
        output = _anthropic_to_assistant_message(completion)
        if output["tool_calls"] is not None:
            invalid_tool_calls: list[int] = []
            for i, tool_call in enumerate(output["tool_calls"]):
                if re.match("^[a-zA-Z0-9_-]{1,64}$", tool_call.function) is None:
                    invalid_tool_calls.append(i)
            for index in sorted(invalid_tool_calls, reverse=True):
                del output["tool_calls"][index]

        messages = [*messages, output]
        return query, runtime, env, messages, extra_args
