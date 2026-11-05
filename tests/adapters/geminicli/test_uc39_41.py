"""D-1063 (regen-batch row 176; review UC-39, UC-40, UC-41): source values the AER cannot hold in a typed field no
longer make the writer refuse a gemini-cli run (it became a ``map.adapter_defect`` AER).

* UC-40: a lone UTF-16 surrogate in a typed text field is replaced by U+FFFD (the shared D-378 pass), the pointer cites
  ``geminicli.lone_surrogate_replaced@1`` and an info issue lists the records; an object key holding one is replaced
  before mapping.
* UC-41: a string whose UTF-8 encoding exceeds 1 MiB is not inlined (the D-934 pattern): ``{not_inlined: {sha256,
  bytes}}``, a tool result's text becomes its value, a text part an ``other`` part of type ``text``.
* UC-39 (the same flaw class, found here too): a reported ``tool_calls`` outside the AER's integer range is no count for
  the accounting check, which would otherwise fail to seal.

Synthetic rollouts derived from the committed fixtures (never written to disk).
"""

from __future__ import annotations

import hashlib
from typing import Any

import geminicli_support as support

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

CRITERION = "ok_with_text_and_calls"
CUT = "cut mid-emoji \ud83d"
BIG = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1 << 15 + 1))[: (1 << 20) + 1]
EXACT = BIG[: 1 << 20]


def _valid(m: support.Mapped) -> None:
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes(), m.codes()
    report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
    assert report.ok, [f.code for f in report.findings][:5]


def _issue_ids(m: support.Mapped, code: str) -> list[str]:
    return [i for issue in m.issues if issue["code"] == code for i in issue["ids"]]


def _first(items: list[dict[str, Any]], **match: Any) -> dict[str, Any]:
    return next(e for e in items if all(e.get(k) == v for k, v in match.items()))


def _digest(value: str) -> dict[str, Any]:
    raw = value.encode()
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    def change(items: list[dict[str, Any]]) -> None:
        _first(items, type="message", role="user")["content"] = CUT

    m = support.modified(CRITERION, change)
    _valid(m)
    (user,) = [r for r in m.of("message") if r["role"] == "user"]
    assert user["parts"][0]["text"] == "cut mid-emoji �" and user["evf"]["/parts/0/text"] == "D"
    assert "geminicli.lone_surrogate_replaced@1#/parts/0/text" in user["rule"]
    assert _issue_ids(m, "geminicli.lone_surrogate_replaced") == [user["id"]]


def test_a_key_with_a_lone_surrogate_is_replaced_before_mapping():
    def change(items: list[dict[str, Any]]) -> None:
        _first(items, type="tool_use")["parameters"] = {"k\ud800": "v"}

    m = support.modified(CRITERION, change)
    _valid(m)
    call = next(p for r in m.of("message") for p in r["parts"] if p["t"] == "tool_call")
    assert call["args"] == {"k�": "v"}
    assert "exec" in _issue_ids(m, "geminicli.lone_surrogate_replaced")


def test_a_string_over_1_mib_is_not_inlined():
    def change(items: list[dict[str, Any]]) -> None:
        _first(items, type="tool_result")["output"] = BIG
        _first(items, type="message", role="user")["content"] = BIG

    m = support.modified(CRITERION, change)
    _valid(m)
    tool = next(r for r in m.of("message") if r["role"] == "tool")
    part = tool["parts"][0]
    assert part["t"] == "tool_result" and "text" not in part and part["value"] == _digest(BIG)
    assert tool["evf"]["/parts/0/value"] == "D" and "geminicli.content_not_inlined@1#/parts/0/value" in tool["rule"]
    (user,) = [r for r in m.of("message") if r["role"] == "user"]
    assert user["parts"] == [{"t": "other", "type": "text", "value": _digest(BIG)}]
    assert user["evf"]["/parts/0/value"] == "D"
    assert sorted(_issue_ids(m, "geminicli.content_not_inlined")) == sorted([tool["id"], user["id"]])


def test_a_string_of_exactly_1_mib_stays_inline():
    def change(items: list[dict[str, Any]]) -> None:
        _first(items, type="tool_result")["output"] = EXACT

    m = support.modified(CRITERION, change)
    _valid(m)
    tool = next(r for r in m.of("message") if r["role"] == "tool")
    assert tool["parts"][0]["text"] == EXACT and _issue_ids(m, "geminicli.content_not_inlined") == []


def test_a_reported_tool_call_count_beyond_the_aer_range_is_no_count():
    for value in (2**60, -1):
        def change(items: list[dict[str, Any]], value: int = value) -> None:
            _first(items, type="result")["stats"]["tool_calls"] = value

        m = support.modified(CRITERION, change)
        _valid(m)
        (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "geminicli.acc.counters@1"]
        assert check["verdict"] == "unverifiable" and "reported_tool_calls" not in check["observed"], value


# ------------------------------------------------------------------------------------------------ AU-RC-1, AU-RC-2
def _citations_resolve(record: dict[str, Any]) -> None:
    from agentprov.aer.locators import pointer_exists

    for ref in record.get("rule", []):
        _rid, sep, pointer = ref.partition("#")
        assert not sep or pointer_exists(record, pointer) or pointer in record.get("unk", {}), ref
    for pointer in record.get("evf", {}):
        assert pointer_exists(record, pointer), pointer


def test_an_assistant_text_over_1_mib_moves_its_deltas_citation():
    """AU-RC-1 (D-1063): every assistant text part cites ``geminicli.deltas_compose_message_unverified@1`` at
    ``/parts/<k>/text``; when the not-inlined pass retypes the part the citation follows to ``/parts/<k>/value``.
    Before, it dangled (``aer.ref.dangling``) and every gemini-cli run with an assistant text over 1 MiB sealed
    ``adapter_defect``."""
    def change(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("type") == "message" and item.get("role") == "assistant":
                item["content"] = BIG
                break

    m = support.modified(CRITERION, change)
    _valid(m)
    (agent,) = [r for r in m.of("message") if r["role"] == "assistant" and any(p["t"] == "other" for p in r["parts"])]
    k = next(i for i, p in enumerate(agent["parts"]) if p["t"] == "other")
    assert agent["parts"][k] == {"t": "other", "type": "text", "value": _digest(BIG)}
    assert f"geminicli.deltas_compose_message_unverified@1#/parts/{k}/value" in agent["rule"]
    assert not any(r.endswith(f"#/parts/{k}/text") for r in agent["rule"])
    _citations_resolve(agent)


def test_a_user_text_over_1_mib_with_a_lone_surrogate_moves_its_citation():
    def change(items: list[dict[str, Any]]) -> None:
        _first(items, type="message", role="user")["content"] = BIG + "\ud83d"

    m = support.modified(CRITERION, change)
    _valid(m)
    (user,) = [r for r in m.of("message") if r["role"] == "user"]
    assert "geminicli.lone_surrogate_replaced@1#/parts/0/value" in user["rule"]
    assert "geminicli.content_not_inlined@1#/parts/0/value" in user["rule"]
    _citations_resolve(user)


def test_a_utf16_argument_whose_base64_exceeds_1_mib_is_its_digest():
    """AU-RC-2 (D-1063): a tool parameter with a lone surrogate whose ``$utf16`` base64 exceeds 1 MiB (400,001 code
    units) is digested as a whole over its decoded text (the writer measures the base64); before, the base64 inside the
    wrapper was replaced (``aer.schema.pattern``)."""
    text = "a" * 400_000 + "\ud800"

    def change(items: list[dict[str, Any]]) -> None:
        _first(items, type="tool_use")["parameters"] = {"content": text}

    m = support.modified(CRITERION, change)
    _valid(m)
    (msg,) = [r for r in m.of("message") if any(p["t"] == "tool_call" and "content" in p.get("args", {}) for p in r["parts"])]
    k = next(i for i, p in enumerate(msg["parts"]) if p["t"] == "tool_call" and "content" in p.get("args", {}))
    raw = text.encode("utf-8", "surrogatepass")
    assert msg["parts"][k]["args"]["content"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert f"geminicli.content_not_inlined@1#/parts/{k}/args/content" in msg["rule"]
    _citations_resolve(msg)
