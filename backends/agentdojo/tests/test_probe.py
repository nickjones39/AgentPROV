"""D.10.9 preflight probes (A3 parameters transmitted, A4 structured tool calls, A9 stock roles accepted, reachability)
as a separate capture session written through the same recording transport. A9 is decided from the reply itself
(D-291): replies that accept, refuse and silently ignore the stock roles."""

from __future__ import annotations

import dataclasses
import json

import pytest

from agentprov_backend.runner import PROBE_KEY, AgentConfig, CaptureSession, build_redactor, run_probe
from agentprov_backend.testing import Fail, Reply, ScriptedTransport
from support import backend, read_events

ACCEPT = Reply.tool_calls([{"name": "get_probe_value", "args": {"key": PROBE_KEY}}])

AGENT = AgentConfig(model_requested="scripted-fake", endpoint="scripted", transport="scripted", script="probe.json",
                    params={"temperature": 0.0})


def _probe(tmp_path, steps, agent=AGENT, redactor=None):
    session = CaptureSession(tmp_path / "probe", redactor=redactor)
    tr = ScriptedTransport(steps)
    result = run_probe(agent, session, backend(), inner_transport=tr, environ={})
    from agentprov_capture.verify import verify_file

    report = verify_file(session.capture_path)
    assert report.sealed and report.head == result["capture_head"]
    return result, read_events(session.capture_path), tr


def test_structured_tool_calls_and_untransmitted_temperature(tmp_path):
    result, events, tr = _probe(tmp_path, [ACCEPT])
    assert result["tool_calls"] == "structured" and result["roles_accepted"] and result["reachable"]
    assert (result["roles"], result["roles_reason"]) == ("accepted", "instruction_followed")
    assert result["params"]["not_transmitted"] == ["temperature"]
    (req,) = [e for e in events if e["type"] == "llm.request"]
    assert req["data"]["input_at"] == [0, 1] and req["data"]["n_messages"] == 2
    body = tr.bodies[0]
    assert b'"developer"' in body and b"get_probe_time" in body
    sent = json.loads(body)["messages"]
    assert sent[0]["role"] == "developer" and PROBE_KEY in json.dumps(sent[0])
    assert all(PROBE_KEY not in json.dumps(m) for m in sent[1:])  # the key is only in the system (developer) message
    assert [e for e in events if e["type"] == "note" and e["data"]["kind"] == "preflight_result"]
    assert not [e for e in events if e["type"] in ("pass.start", "outcome")]


@pytest.mark.parametrize("text", [f'<function=get_probe_value>{{"key": "{PROBE_KEY}"}}</function>',
                                  "I will call get_probe_value."])
def test_text_encoded_tool_calls_are_detected(tmp_path, text):
    result, _, _ = _probe(tmp_path, [Reply.text(text)])
    assert result["tool_calls"] == "text_encoded"
    assert result["roles_accepted"] == (PROBE_KEY in text)


def test_role_rejection_and_unreachable(tmp_path):
    result, events, _ = _probe(tmp_path / "a", [Fail.http(400, code="invalid_role")])
    assert result["reachable"] and not result["roles_accepted"] and result["http_status"] == 400
    assert (result["roles"], result["roles_reason"]) == ("refused", "http_400")
    assert result["tool_calls"] == "error"
    result, _, _ = _probe(tmp_path / "b", [Fail.connection()] * 9)
    assert not result["reachable"] and result["http_status"] is None
    assert (result["roles"], result["roles_accepted"]) == ("unknown", False)


# -- D-291: a 2xx is not enough --------------------------------------------------------------------------------------


def test_a_2xx_with_an_error_object_refuses_the_roles(tmp_path):
    result, events, _ = _probe(tmp_path, [Fail.no_choices(error={"message": "role 'developer' is not supported"})])
    assert result["http_status"] == 200 and result["reachable"]
    assert (result["roles"], result["roles_reason"], result["roles_accepted"]) == ("refused", "error_object", False)
    (note,) = [e for e in events if e["type"] == "note" and e["data"]["kind"] == "preflight_result"]
    assert note["data"]["payload"]["roles"] == "refused"


def test_a_2xx_role_refusal_written_as_text_refuses_the_roles(tmp_path):
    result, _, _ = _probe(tmp_path, [Reply.text("Error: unsupported message role 'developer'.")])
    assert (result["http_status"], result["roles"], result["roles_reason"]) == (200, "refused", "role_refusal_text")
    assert result["tool_calls"] == "none"


@pytest.mark.parametrize("step", [
    Reply.tool_calls([{"name": "get_probe_value", "args": {"key": "probe"}}]),  # the tool, not the instructed key
    Reply.text("Probe received."),  # answered only the user message
])
def test_a_2xx_that_silently_ignores_the_roles_is_not_accepted(tmp_path, step):
    result, _, _ = _probe(tmp_path, [step])
    assert result["http_status"] == 200 and not result["roles_accepted"]
    assert (result["roles"], result["roles_reason"]) == ("unconfirmed", "instruction_not_evidenced")


SECRET_HEADERS = {"set-cookie": "sid=probe-cookie-value-1f2e", "x-api-key": "probe-header-key-9a8b7c",
                  "openai-organization": "org-probe-private-77aa", "x-request-id": "req-probe-55cc"}


def test_the_probe_records_allowlisted_header_values_only(tmp_path):
    """The verdict reads the body only; the response headers go to the filtered ``wire_headers`` note (names of the
    others only), whatever the reply: no value outside the allowlist reaches the probe session."""
    environ = {"FAKE_PROVIDER_API_KEY": "sk-agentprov-probe-sentinel-0c4d"}
    for n, step in enumerate([ACCEPT, Reply.text("Probe received.")]):
        tagged = dataclasses.replace(step, headers={**SECRET_HEADERS, "date": "Thu, 01 Jan 2026 00:00:00 GMT"})
        result, events, _ = _probe(tmp_path / str(n), [tagged], redactor=build_redactor(environ))
        assert result["roles"] == ("accepted" if n == 0 else "unconfirmed")
        (note,) = [e["data"]["payload"] for e in events if e["type"] == "note" and e["data"]["kind"] == "wire_headers"
                   and e["data"]["payload"]["direction"] == "response"]
        assert set(note["kept"]) <= {"content-type", "date"}
        assert set(SECRET_HEADERS) <= set(note["dropped"])
        files = [p for p in (tmp_path / str(n)).rglob("*") if p.is_file()]
        assert files
        for path in files:
            data = path.read_bytes()
            for value in [*SECRET_HEADERS.values(), environ["FAKE_PROVIDER_API_KEY"]]:
                assert value.encode() not in data, (path.name, value)
