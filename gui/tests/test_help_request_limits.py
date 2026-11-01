"""Review UC-14: the Assistant page sends what fits the CLI's request limits. Before, one reply over 20,000 characters
(or a conversation over 1 MiB) made every later message exit 2 until New Chat."""

from __future__ import annotations

import json

from agentprov_gui.ui import help as H


def _sent(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    data = H.request_bytes(messages)
    assert len(data) <= H.SEND_BYTES
    doc = json.loads(data)
    assert doc["format"] == H.REQUEST_FORMAT
    return doc["messages"]


def test_a_long_earlier_reply_is_cut_and_the_question_sent_whole() -> None:
    sent = _sent([{"role": "user", "content": "q1"}, {"role": "assistant", "content": "r" * 27_000, "sources": "x"},
                  {"role": "user", "content": "q2"}])
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert len(sent[1]["content"]) == H.SEND_TURN_CHARS and sent[2]["content"] == "q2"
    assert all(set(m) == {"role", "content"} for m in sent)


def test_a_long_conversation_drops_its_oldest_turns_and_starts_with_the_user() -> None:
    messages: list[dict[str, str]] = []
    for i in range(60):
        messages += [{"role": "user", "content": f"q{i} " + "é" * 9_000},
                     {"role": "assistant", "content": "中" * 19_000}]
    messages.append({"role": "user", "content": "last"})
    sent = _sent(messages)
    assert len(sent) <= H.SEND_MESSAGES and sent[0]["role"] == "user" and sent[-1]["content"] == "last"
