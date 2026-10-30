"""The D.10.9 A9 preflight verdict decided from the reply itself (D-291): provider replies that accept, refuse and
silently ignore the stock roles. ``roles_verdict`` reads only the decoded body, so these need no benchmark package."""

from __future__ import annotations

import json

import pytest

from agentprov_backend.runner import PROBE_KEY, PROBE_PROMPT, roles_verdict


def _completion(message: dict, *, finish: str = "stop", **extra) -> bytes:
    body = {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", **message}}], **extra}
    return json.dumps(body).encode()


def _call(key: str, name: str = "get_probe_value") -> dict:
    return {"content": None, "tool_calls": [{"id": "c", "type": "function",
                                            "function": {"name": name, "arguments": json.dumps({"key": key})}}]}


def test_the_probe_key_is_only_in_the_system_message():
    assert PROBE_KEY in PROBE_PROMPT and len(PROBE_KEY) >= 8


# -- accepted: the reply follows the instruction only the system message carries ------------------------------------


@pytest.mark.parametrize("body", [
    _completion(_call(PROBE_KEY), finish="tool_calls"),
    _completion({"content": f'<function=get_probe_value>{{"key": "{PROBE_KEY}"}}</function>'}),
    _completion({"content": [{"type": "text", "text": f"get_probe_value(key='{PROBE_KEY}')"}]}),
])
def test_a_reply_that_follows_the_system_instruction_accepts_the_roles(body):
    assert roles_verdict(200, body) == ("accepted", "instruction_followed")


# -- refused: an HTTP error, or a 2xx that says so in its body ---------------------------------------------------------


@pytest.mark.parametrize("status", [400, 422, 500])
def test_a_non_2xx_status_refuses(status):
    body = json.dumps({"error": {"message": "Invalid role 'developer'", "code": "invalid_role"}}).encode()
    assert roles_verdict(status, body) == ("refused", f"http_{status}")


@pytest.mark.parametrize("error", [
    {"message": "messages[0].role 'developer' is not supported", "code": 400},
    {"code": 502, "message": "upstream provider unavailable"},
    "invalid request",
])
def test_a_2xx_with_an_error_object_refuses(error):
    body = json.dumps({"id": None, "object": "chat.completion", "choices": None, "error": error}).encode()
    assert roles_verdict(200, body) == ("refused", "error_object")


@pytest.mark.parametrize("text", [
    "Error: unsupported message role 'developer'.",
    "The developer role is not supported by this model.",
    "Invalid role: system messages are not allowed here.",
    "role 'developer' not supported",
])
def test_a_2xx_whose_text_refuses_the_role_refuses(text):
    assert roles_verdict(200, _completion({"content": text})) == ("refused", "role_refusal_text")


def test_a_role_refusal_in_the_refusal_field_refuses():
    assert roles_verdict(200, _completion({"content": None, "refusal": "Unknown role developer"})) == (
        "refused", "role_refusal_text")


# -- unconfirmed: a 2xx with no evidence the system message reached the model (silently ignored roles) ----------------


@pytest.mark.parametrize("body", [
    _completion(_call("probe"), finish="tool_calls"),  # the tool, but not the key the system message named
    _completion(_call(PROBE_KEY, name="get_probe_time"), finish="tool_calls"),
    _completion({"content": "Probe received. How can I help?"}),  # answered the user message only
    _completion({"content": "I will call get_probe_value."}),  # names the tool, not the key
    _completion({"content": None, "refusal": "I can't help with that."}),
])
def test_a_2xx_that_ignores_the_system_message_is_unconfirmed(body):
    assert roles_verdict(200, body) == ("unconfirmed", "instruction_not_evidenced")


def test_other_unconfirmed_replies():
    assert roles_verdict(200, b"<html>ok</html>") == ("unconfirmed", "body_not_json")
    assert roles_verdict(200, json.dumps({"choices": []}).encode()) == ("unconfirmed", "no_choices")
    assert roles_verdict(200, json.dumps({"choices": [{"message": None}]}).encode()) == ("unconfirmed", "no_choices")
    assert roles_verdict(200, _completion({"content": "partial"}, finish="error")) == ("unconfirmed", "finish_error")
    assert roles_verdict(200, None) == ("unconfirmed", "body_not_json")


def test_no_reply_is_unknown():
    assert roles_verdict(None, None) == ("unknown", "no_reply")
