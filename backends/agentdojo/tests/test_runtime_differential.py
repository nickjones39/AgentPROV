"""D.10.6 runtime differential: ``RecordingFunctionsRuntime`` vs stock ``FunctionsRuntime``.

Same inputs (deep-copied), same suite tools: the ``(result, error)`` pairs and the post-environments must be equal as
JCS bytes, with and without an active occurrence, and for ``raise_on_error=True`` the same exception type. The records
the recording runtime attaches are checked against the stock return contract."""

from __future__ import annotations

import copy
import json

import pytest
import rfc8785
from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suites
from pydantic import BaseModel

from agentprov_backend.runtime import RecordingFunctionsRuntime

SUITES = sorted(get_suites("v1.2.2"))


class FakeSession:
    def __init__(self) -> None:
        self.current_occ: str | None = None
        self.records: list[dict] = []

    def runtime_record(self, record: dict) -> None:
        self.records.append(record)


def _jcs(value: object) -> bytes:
    return rfc8785.dumps(json.loads(json.dumps(value, default=lambda o: o.model_dump(mode="json") if isinstance(o, BaseModel) else str(o))))


def _cases(suite) -> list[tuple[str, str, dict]]:
    env = suite.load_and_inject_default_environment({})
    calls = []
    for task in list(suite.user_tasks.values())[:5]:
        calls.extend(task.ground_truth(task.init_environment(env.model_copy(deep=True))))
    cases = [("valid", c.function, dict(c.args)) for c in calls[:5]]
    tool = next(t for t in suite.tools if t.parameters.model_fields)
    cases += [
        ("unknown", "no_such_tool", {}),
        ("validation", tool.name, {"__bad__": object.__name__, **{k: {"nested": [1]} for k in tool.parameters.model_fields}}),
        ("nested_call", calls[0].function, {k: FunctionCall(function="no_such_tool", args={}) for k in calls[0].args} or
         {"x": FunctionCall(function="no_such_tool", args={})}),
    ]
    return cases


def _run(runtime_cls, suite, function, args, raise_on_error=False):
    env = suite.load_and_inject_default_environment({})
    runtime = runtime_cls(suite.tools)
    try:
        result, error = runtime.run_function(env, function, copy.deepcopy(args), raise_on_error=raise_on_error)
        outcome = ("ok", _jcs(result), error)
    except Exception as exc:  # noqa: BLE001
        outcome = ("raised", type(exc).__name__, None)
    return outcome, _jcs(env.model_dump(mode="json"))


@pytest.mark.parametrize("suite_name", SUITES)
def test_recording_runtime_equals_stock_runtime(suite_name):
    suite = get_suites("v1.2.2")[suite_name]
    for label, function, args in _cases(suite):
        for raise_on_error in (False, True):
            stock = _run(FunctionsRuntime, suite, function, args, raise_on_error)
            unbound = _run(RecordingFunctionsRuntime, suite, function, args, raise_on_error)
            session = FakeSession()
            session.current_occ = "o0"
            bound = _run(RecordingFunctionsRuntime.bind(session), suite, function, args, raise_on_error)
            assert unbound == stock and bound == stock, (suite_name, label, raise_on_error)
            if not raise_on_error:
                (record,) = session.records
                _, _, error = stock[0]
                assert (record["status"] == "ok") == (error is None), (label, record)
                if label == "unknown" or label == "validation":
                    assert record["status"] == "invalid" and "args_effective" not in record
                if error is not None:
                    assert record["exception"]["type"] == error.split(":", 1)[0]
            else:
                assert session.records == []          # nested/raising calls are not recorded separately


def test_a_runtime_without_an_occurrence_records_nothing():
    suite = get_suites("v1.2.2")["banking"]
    session = FakeSession()
    runtime = RecordingFunctionsRuntime.bind(session)(suite.tools)
    runtime.run_function(suite.load_and_inject_default_environment({}), "get_balance", {})
    assert session.records == []
