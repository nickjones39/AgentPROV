"""``PassRecorder``: records every pass of AgentDojo's silent pipeline re-run (D.10.5; replaces the baseline
``EnvironmentRecorder`` + ``TranscriptCapture``, ``observer.py:70-169``).

AgentDojo 0.1.35 ``TaskSuite.run_task_with_pipeline`` (``task_suite.py:383-394``) runs the agent pipeline up to three
times, with fresh messages and the same (mutated) environment, while the final reply has no content; the native log
keeps only the last pass. The recorder wraps the **whole** pipeline object, is passed to the stock runner as the agent
pipeline, and for each pass:

* emits ``pass.start`` with the environment digest (and snapshot) as the pass found it;
* runs ``inner.query`` unchanged;
* on ``AbortAgentError`` emits ``pass.end`` with the exception's messages and environment, ``aborted: true``, and
  **re-raises**, so the stock handling (``task_suite.py:387-390``) is unchanged;
* on any other exception emits ``pass.end`` with the last message list a harness element saw and the environment as
  it is, ``aborted: true``, preceded by an ``error`` event (``where: "pipeline"``, not fatal by itself), and re-raises;
* otherwise emits ``pass.end`` with the returned messages and environment, serialised at pass end.

It never changes arguments, return values or exceptions. ``name`` is the inner pipeline's (attacks and the
TraceLogger read ``pipeline.name``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.errors import AbortAgentError
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.types import ChatMessage

__all__ = ["PassRecorder", "dump_env"]


def dump_env(env: Any, lossy: list[str] | None = None) -> Any:
    """The environment as JSON data (read-only ``model_dump(mode="json")``; D.10.7 ``env_dump_per_pass@1``).

    When pydantic cannot dump the environment, it is walked field by field instead (``_lossy_dump``) and every member
    that cannot be represented is replaced by the string ``"<unserialisable TYPE>"`` (a value that is not data) or
    ``"<circular TYPE>"`` (a reference back to an enclosing object), so the recorder never raises into the benchmark
    (an observer must not change the run). The case is real: the AgentDyn ``shopping`` environment of the AutoDojo
    fork stores ``(function, (platform, ...))`` in ``verification_stack`` once a checkout asks for an OTP, a callable
    whose arguments refer back to the environment. The replaced type names are appended to ``lossy`` so the caller
    records the loss (note ``agentdojo/env_dump_lossy``). Stock AgentDojo 0.1.35 environments always serialise, so
    nothing changes there."""
    if not hasattr(env, "model_dump"):
        return env
    try:
        return env.model_dump(mode="json")
    except Exception:  # noqa: BLE001 - pydantic serialisation errors vary by version
        return _lossy_dump(env, [] if lossy is None else lossy, set())


def _lossy_dump(value: Any, lossy: list[str], active: set[int]) -> Any:
    from pydantic import BaseModel
    from pydantic_core import to_jsonable_python

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (BaseModel, dict, list, tuple, set, frozenset)):
        if id(value) in active:
            lossy.append(type(value).__qualname__)
            return f"<circular {type(value).__qualname__}>"
        active.add(id(value))
        try:
            if isinstance(value, BaseModel):
                return {name: _lossy_dump(getattr(value, name), lossy, active) for name in type(value).model_fields}
            if isinstance(value, dict):
                return {str(k): _lossy_dump(v, lossy, active) for k, v in value.items()}
            return [_lossy_dump(v, lossy, active) for v in value]
        finally:
            active.discard(id(value))
    try:
        return to_jsonable_python(value)
    except Exception:  # noqa: BLE001
        lossy.append(type(value).__qualname__)
        return f"<unserialisable {type(value).__qualname__}>"


class PassRecorder(BasePipelineElement):
    """Wraps the whole pipeline; see the module docstring."""

    def __init__(self, inner: BasePipelineElement, hooks: Any) -> None:
        self.inner = inner
        self.hooks = hooks
        self.name = inner.name
        self.passes = 0

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),  # noqa: B008 - the stock BasePipelineElement.query signature
        messages: Sequence[ChatMessage] = [],  # noqa: B006
        extra_args: dict = {},  # noqa: B006
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        lossy: list[str] = []
        index = self.hooks.pass_start(dump_env(env, lossy))
        self._lossy(index, lossy, "start")
        self.passes += 1
        try:
            out = self.inner.query(query, runtime, env, messages, extra_args)
        except AbortAgentError as e:
            dumped = dump_env(e.task_environment, lossy)
            self._lossy(index, lossy, "end")
            self.hooks.pass_end(index, e.messages, dumped, aborted=True)
            raise
        except BaseException as e:
            hooks = self.hooks
            try:
                if hasattr(hooks, "record_error"):
                    hooks.record_error(e, fatal=False, where="pipeline")
                dumped = dump_env(env, lossy)
                self._lossy(index, lossy, "end")
                hooks.pass_end(index, list(getattr(hooks, "last_messages", [])), dumped, aborted=True)
            except Exception:  # noqa: BLE001 - recording a crash must not mask the crash
                pass
            raise
        dumped = dump_env(out[2], lossy)
        self._lossy(index, lossy, "end")
        self.hooks.pass_end(index, out[3], dumped, aborted=False)
        return out

    def _lossy(self, index: int, lossy: list[str], at: str) -> None:
        """Record (and clear) the member types a dump replaced (note ``agentdojo/env_dump_lossy``)."""
        if lossy and hasattr(self.hooks, "note"):
            self.hooks.note("agentdojo", "env_dump_lossy", {"pass": index, "at": at, "types": sorted(set(lossy))})
        lossy.clear()
