"""``MirrorToolsExecutor``: a recording mirror of AgentDojo 0.1.35 ``ToolsExecutor.query`` (D.10.5, D.10.6; K.9.4).

The body below is the stock method (``agentdojo/agent_pipeline/tool_execution.py:58-115``) with recording calls
added around each tool-call occurrence; the messages it returns and the environment effects are the stock ones, which
the differential test ``backends/agentdojo/tests/test_executor_mirror.py`` checks as JCS bytes for every suite. For each
occurrence it:

* mints a harness occurrence id ``o<n>`` (unique per session; fixes provider-id reuse, OB-6) and emits
  ``tool.dispatch`` with the requested arguments **as the model sent them** (before the stock in-place
  ``literal_eval`` of string-encoded lists), the provider call id and ``at = {message, call}`` (positions in the pass's
  native message list);
* runs the stock logic (empty name, unknown tool, list coercion, ``runtime.run_function``, the output formatter);
* emits ``tool.result`` with the status, the effective (validated) arguments and the exception type reported by the
  recording runtime, the native return value (only when the tool returned), the rendered output, and the
  **model-visible** text: ``error or content``, which is what the stock OpenAI element sends
  (``openai_llm.py:103``).

Times come from the ``ts``/``mono_ns`` of the two events (wall clock and monotonic), for every occurrence, including
those with ``id is None``.

``guard()`` compares the installed ``ToolsExecutor.query`` with the mirrored one by AST digest and raises
``MirrorMismatch`` when they differ; nothing is run then. ``ast.dump`` output is specific to the interpreter (its node
fields change between minor versions), so the expected digest is looked up by :func:`interpreter_key`; on an interpreter
without a recorded digest ``guard()`` raises ``MirrorUnverifiable`` (a ``MirrorMismatch``) instead of reporting a
difference it cannot establish (phase 9b, D-292).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
import textwrap
from ast import literal_eval
from collections.abc import Callable, Sequence
from typing import Any

from agentdojo.agent_pipeline.llms.google_llm import EMPTY_FUNCTION_NAME
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor, is_string_list, tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionReturnType, FunctionsRuntime
from agentdojo.types import ChatMessage, ChatToolResultMessage, text_content_block_from_string

__all__ = ["MIRRORS", "MirrorMismatch", "MirrorToolsExecutor", "MirrorUnverifiable", "expected_ast_sha256", "guard",
           "interpreter_key", "status_from_error", "source_digests"]

#: The AgentDojo version whose ``ToolsExecutor.query`` this module mirrors.
MIRRORS = "0.1.35"
#: sha256 of ``inspect.getsource(ToolsExecutor.query)`` in agentdojo 0.1.35 (PyPI wheel).
MIRRORED_SOURCE_SHA256 = "918da2f08913cb1df497befe803cc674b32563d37151d04c9194de19e026e12a"
#: sha256 of ``ast.dump(ast.parse(dedent(source)))`` of that method under CPython 3.12 (formatting-independent, but not
#: interpreter-independent; the AutoDojo fork's method is AST-identical, verify/autodojo.md #18).
MIRRORED_AST_SHA256 = "f38ff1afa87f4a099dcffc8556388706d8558a673966d33a2479b47f9e82ddaf"
#: The AST digest of the mirrored method per interpreter (:func:`interpreter_key`). Only CPython 3.12 is recorded: the
#: backend environments are built with Python 3.12 (AgentDojo 0.1.35 baseline parity). A digest for another interpreter
#: is added only after the mirror's differential test has passed on it.
MIRRORED_AST_SHA256_BY_INTERPRETER: dict[str, str] = {"cpython-3.12": MIRRORED_AST_SHA256}


class MirrorMismatch(RuntimeError):
    """The installed ``ToolsExecutor.query`` is not the one this mirror reproduces."""


class MirrorUnverifiable(MirrorMismatch):
    """No AST digest of the mirrored method is recorded for the running interpreter, so the guard cannot check it."""

    code = "backend.mirror.interpreter"


def interpreter_key() -> str:
    """``<implementation>-<major>.<minor>`` of the running interpreter (for example ``cpython-3.12``)."""
    return f"{sys.implementation.name}-{sys.version_info[0]}.{sys.version_info[1]}"


def expected_ast_sha256(key: str | None = None) -> str:
    """The recorded AST digest for ``key`` (default: the running interpreter); ``MirrorUnverifiable`` without one."""
    key = interpreter_key() if key is None else key
    digest = MIRRORED_AST_SHA256_BY_INTERPRETER.get(key)
    if digest is None:
        known = ", ".join(sorted(MIRRORED_AST_SHA256_BY_INTERPRETER))
        raise MirrorUnverifiable(f"the executor guard has no AST digest for interpreter {key} (recorded: {known}); "
                                 "refusing to run")
    return digest


def source_digests(func: Callable[..., Any]) -> tuple[str, str]:
    """``(sha256 of inspect.getsource, sha256 of its AST dump)`` of a function or method."""
    src = inspect.getsource(func)
    tree = ast.dump(ast.parse(textwrap.dedent(src)))
    return hashlib.sha256(src.encode("utf-8")).hexdigest(), hashlib.sha256(tree.encode("utf-8")).hexdigest()


def guard() -> str:
    """Check the installed method against the mirror; returns its source digest. ``MirrorUnverifiable`` on an interpreter
    without a recorded digest (checked first, so nothing is compared against another interpreter's dump)."""
    expected = expected_ast_sha256()
    src_sha, ast_sha = source_digests(ToolsExecutor.query)
    if ast_sha != expected:
        raise MirrorMismatch(
            f"agentdojo ToolsExecutor.query differs from the mirrored {MIRRORS} method (source sha256 {src_sha})")
    return src_sha


def status_from_error(error: str | None) -> str:
    """The stock return contract read as a status (``agentdojo.tool_status_from_error@1``): ``None`` -> ok; a
    ``ValidationError``/``ToolNotFoundError`` prefix -> invalid; any other error -> error."""
    if error is None:
        return "ok"
    if error.startswith(("ValidationError:", "ToolNotFoundError:")):
        return "invalid"
    return "error"


def _requested(args: Any) -> Any:
    from agentprov_backend._jsonval import to_jsonable

    return to_jsonable(args)


class MirrorToolsExecutor(ToolsExecutor):
    """Stock ``ToolsExecutor`` behaviour, recorded through ``hooks`` (a ``CaptureSession``; ``None`` records nothing)."""

    def __init__(self, tool_output_formatter: Callable[[FunctionReturnType], str] = tool_result_to_str,
                 hooks: Any = None) -> None:
        super().__init__(tool_output_formatter)
        self.hooks = hooks

    def _dispatch(self, tool_call: Any, at: tuple[int, int]) -> str | None:
        if self.hooks is None:
            return None
        occ = self.hooks.next_occ()
        self.hooks.tool_dispatch(occ, tool_call.id, tool_call.function, _requested(tool_call.args), None, at)
        return occ

    def _result(self, occ: str | None, *, status: str, error: str | None, rendered: str,
                returned: Any = None, has_returned: bool = False, record: dict[str, Any] | None = None) -> None:
        if self.hooks is None or occ is None:
            return
        args_effective = None
        exception = None
        if record is not None:
            status = record.get("status", status)
            args_effective = record.get("args_effective")
            exception = record.get("exception")
            has_returned = has_returned and status == "ok"
        self.hooks.tool_result(occ, status, args_effective, returned, rendered, error or rendered, error,
                               exception=exception, has_returned=has_returned)

    def _bind(self, message: Any, occ: str | None) -> None:
        if self.hooks is not None and occ is not None and hasattr(self.hooks, "bind_message"):
            self.hooks.bind_message(message, occ)

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),  # noqa: B008 - the stock BasePipelineElement.query signature
        messages: Sequence[ChatMessage] = [],  # noqa: B006
        extra_args: dict = {},  # noqa: B006
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        if len(messages) == 0:
            return query, runtime, env, messages, extra_args
        if messages[-1]["role"] != "assistant":
            return query, runtime, env, messages, extra_args
        if messages[-1]["tool_calls"] is None or len(messages[-1]["tool_calls"]) == 0:
            return query, runtime, env, messages, extra_args

        if self.hooks is not None:
            self.hooks.observe_messages(messages)
        message_index = len(messages) - 1
        tool_call_results = []
        for call_index, tool_call in enumerate(messages[-1]["tool_calls"]):
            occ = self._dispatch(tool_call, (message_index, call_index))
            if tool_call.function == EMPTY_FUNCTION_NAME:
                error = "Empty function name provided. Provide a valid function name."
                tool_call_results.append(
                    ChatToolResultMessage(
                        role="tool",
                        content=[text_content_block_from_string("")],
                        tool_call_id=tool_call.id,
                        tool_call=tool_call,
                        error=error,
                    )
                )
                self._result(occ, status="invalid", error=error, rendered="")
                self._bind(tool_call_results[-1], occ)
                continue
            if tool_call.function not in (tool.name for tool in runtime.functions.values()):
                error = f"Invalid tool {tool_call.function} provided."
                tool_call_results.append(
                    ChatToolResultMessage(
                        role="tool",
                        content=[text_content_block_from_string("")],
                        tool_call_id=tool_call.id,
                        tool_call=tool_call,
                        error=error,
                    )
                )
                self._result(occ, status="invalid", error=error, rendered="")
                self._bind(tool_call_results[-1], occ)
                continue

            # Converts type of input lists from string to list type
            for arg_k, arg_v in tool_call.args.items():
                if isinstance(arg_v, str) and is_string_list(arg_v):
                    tool_call.args[arg_k] = literal_eval(arg_v)

            if self.hooks is not None:
                self.hooks.current_occ = occ
            try:
                tool_call_result, error = runtime.run_function(env, tool_call.function, tool_call.args)
            finally:
                if self.hooks is not None:
                    self.hooks.current_occ = None
            record = self.hooks.take_runtime_record(occ) if self.hooks is not None and occ is not None else None
            tool_call_id = tool_call.id
            formatted_tool_call_result = self.output_formatter(tool_call_result)
            tool_call_results.append(
                ChatToolResultMessage(
                    role="tool",
                    content=[text_content_block_from_string(formatted_tool_call_result)],
                    tool_call_id=tool_call_id,
                    tool_call=tool_call,
                    error=error,
                )
            )
            self._result(occ, status=status_from_error(error), error=error, rendered=formatted_tool_call_result,
                         returned=tool_call_result, has_returned=error is None, record=record)
            self._bind(tool_call_results[-1], occ)
        out = [*messages, *tool_call_results]
        if self.hooks is not None:
            self.hooks.observe_messages(out)
        return query, runtime, env, out, extra_args
