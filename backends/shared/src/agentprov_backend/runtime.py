"""``RecordingFunctionsRuntime``: the stock ``FunctionsRuntime``, recording what it decided (D.10.5).

Passed through the public ``runtime_class`` parameter of ``TaskSuite.run_task_with_pipeline`` (``task_suite.py:345``)
by ``runner.SuiteRunProxy``. ``run_function`` delegates to ``FunctionsRuntime.run_function`` **unchanged** and returns
its result unchanged. Before delegating it computes, without side effects, what the stock method will compute:

* whether the function exists;
* the validated (effective) arguments, with the same pydantic model ``Function.parameters`` the stock method uses
  (``model_validate(...).model_dump()``; validation is pure). This is skipped when an argument is a nested
  ``FunctionCall`` (the stock method would execute it first; such calls never come from a chat-completions reply);

and after it, the status from the stock return contract (``(result, None)`` = ok; ``("", "<Type>: <message>")`` = a
failure) and the exception type named by the error prefix. The record is attached to the occurrence the executor
mirror is dispatching (``session.current_occ``); nested calls (``raise_on_error=True``) and calls outside an occurrence
are not recorded separately.

Statuses (C.3 ``tool_execution.status``): ``ok`` ran and returned; ``invalid`` not run because the runtime rejected the
call (unknown tool, argument validation); ``error`` ran and raised (including a failing nested call).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from agentdojo.functions_runtime import FunctionCall, FunctionCallArgTypes, FunctionReturnType, FunctionsRuntime, TaskEnvironment
from pydantic import ValidationError

__all__ = ["RecordingFunctionsRuntime"]


class RecordingFunctionsRuntime(FunctionsRuntime):
    """See the module docstring. Use ``RecordingFunctionsRuntime.bind(session)`` to get a class bound to a session
    (the stock runner instantiates ``runtime_class(suite.tools)`` itself)."""

    session: ClassVar[Any] = None

    @classmethod
    def bind(cls, session: Any) -> type[RecordingFunctionsRuntime]:
        return type("RecordingFunctionsRuntime", (cls,), {"session": session, "__module__": cls.__module__})

    def run_function(
        self,
        env: TaskEnvironment | None,
        function: str,
        kwargs: Mapping[str, FunctionCallArgTypes],
        raise_on_error: bool = False,
    ) -> tuple[FunctionReturnType, str | None]:
        session = type(self).session
        gate = getattr(session, "gate", None) if session is not None else None
        if not raise_on_error and gate is not None and getattr(session, "current_occ", None) is None:
            # a defence's own executor is running (defences.GateRecorder): this call is the next matching call of the
            # batch; it is dispatched now, recorded as usual, and its result is reported back to the gate
            occ = gate.begin(function)
            if occ is None:
                return super().run_function(env, function, kwargs, raise_on_error)
            session.current_occ = occ
            try:
                result, error = self.run_function(env, function, kwargs, raise_on_error)
            finally:
                session.current_occ = None
            gate.end(session.take_runtime_record(occ), result)
            return result, error
        if raise_on_error or session is None or getattr(session, "current_occ", None) is None:
            return super().run_function(env, function, kwargs, raise_on_error)
        exists = function in self.functions
        args_effective: Any = None
        validation_failed = False
        nested = any(isinstance(v, FunctionCall) for v in kwargs.values())
        if exists and not nested:
            try:
                args_effective = self.functions[function].parameters.model_validate(dict(kwargs)).model_dump()
            except ValidationError:
                validation_failed = True
            except Exception:  # noqa: BLE001 - recording never changes the call
                args_effective = None
        result, error = super().run_function(env, function, kwargs, raise_on_error)
        record: dict[str, Any] = {}
        if error is None:
            record["status"] = "ok"
        elif not exists or validation_failed or error.startswith("ValidationError:"):
            record["status"] = "invalid"
        else:
            record["status"] = "error"
        if error is not None:
            etype, _, message = error.partition(": ")
            record["exception"] = {"type": etype, "message": message}
        if args_effective is not None and not validation_failed:
            record["args_effective"] = args_effective
        session.runtime_record(record)
        return result, error
