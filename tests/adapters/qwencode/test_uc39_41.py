"""D-1063 (regen-batch row 176; review UC-39, UC-40, UC-41): source values the AER cannot hold in a typed field no
longer make the writer refuse a Qwen Code run (it became a ``map.adapter_defect`` AER).

* UC-40: a lone UTF-16 surrogate in a typed text field is replaced by U+FFFD (the shared D-378 pass), the pointer cites
  ``qwencode.lone_surrogate_replaced@1`` and an info issue lists the records; an object key holding one is replaced
  before mapping.
* UC-41: a string whose UTF-8 encoding exceeds 1 MiB is not inlined (the D-934 pattern): ``{not_inlined: {sha256,
  bytes}}``, a tool result's text becomes its value, a text part an ``other`` part of type ``text``.
* UC-39: a token count outside the AER's integer range (negative, or a block sum beyond 2^53 - 1) never reaches the
  typed ``usage``; the logged values stay in ``ext.qwencode.messages``.

Synthetic runs derived from the committed fixtures (never written to disk).
"""

from __future__ import annotations

import hashlib
from typing import Any

import qwencode_support as support

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

CUT = "cut mid-emoji \ud83d"
BIG = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1 << 15 + 1))[: (1 << 20) + 1]
EXACT = BIG[: 1 << 20]


def _valid(m: support.Mapped) -> None:
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes(), m.codes()
    report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
    assert report.ok, [f.code for f in report.findings][:5]


def _issue_ids(m: support.Mapped, code: str) -> list[str]:
    return [i for issue in m.issues if issue["code"] == code for i in issue["ids"]]


def _assistants(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in items if m.get("type") == "assistant"]


def _first_text(items: list[dict[str, Any]]) -> dict[str, Any]:
    return next(c for m in _assistants(items) for c in m["message"]["content"] if c.get("type") == "text")


def _tool_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    return next(c for m in items if m.get("type") == "user" for c in m["message"]["content"] if c.get("type") == "tool_result")


def _digest(value: str) -> dict[str, Any]:
    raw = value.encode()
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    def change(items: list[dict[str, Any]]) -> None:
        _first_text(items)["text"] = CUT

    m = support.modified("python", change)
    _valid(m)
    (msg,) = [r for r in m.of("message") if r["role"] == "assistant" and any(
        p.get("text") == "cut mid-emoji �" for p in r["parts"])]
    k = next(i for i, p in enumerate(msg["parts"]) if p.get("text") == "cut mid-emoji �")
    assert msg["evf"][f"/parts/{k}/text"] == "D"
    assert f"qwencode.lone_surrogate_replaced@1#/parts/{k}/text" in msg["rule"]
    assert _issue_ids(m, "qwencode.lone_surrogate_replaced") == [msg["id"]]


def test_a_key_with_a_lone_surrogate_is_replaced_before_mapping():
    def change(items: list[dict[str, Any]]) -> None:
        use = next(c for m in _assistants(items) for c in m["message"]["content"] if c.get("type") == "tool_use")
        use["input"] = {"k\ud800": "v"}

    m = support.modified("python", change)
    _valid(m)
    call = next(p for r in m.of("message") for p in r["parts"] if p["t"] == "tool_call")
    assert call["args"] == {"k�": "v"}
    assert "exec" in _issue_ids(m, "qwencode.lone_surrogate_replaced")


def test_a_string_over_1_mib_is_not_inlined():
    def change(items: list[dict[str, Any]]) -> None:
        _tool_result(items)["content"] = BIG
        _first_text(items)["text"] = BIG

    m = support.modified("python", change)
    _valid(m)
    (tool,) = [r for r in m.of("message") if r["role"] == "tool"]
    part = tool["parts"][0]
    assert part["t"] == "tool_result" and "text" not in part and part["value"] == _digest(BIG)
    assert tool["evf"]["/parts/0/value"] == "D" and "qwencode.content_not_inlined@1#/parts/0/value" in tool["rule"]
    (agent,) = [r for r in m.of("message") if r["role"] == "assistant" and any(p["t"] == "other" for p in r["parts"])]
    k = next(i for i, p in enumerate(agent["parts"]) if p["t"] == "other")
    assert agent["parts"][k] == {"t": "other", "type": "text", "value": _digest(BIG)}
    assert agent["evf"][f"/parts/{k}/value"] == "D"
    assert sorted(_issue_ids(m, "qwencode.content_not_inlined")) == sorted([tool["id"], agent["id"]])


def test_a_string_of_exactly_1_mib_stays_inline():
    def change(items: list[dict[str, Any]]) -> None:
        _tool_result(items)["content"] = EXACT

    m = support.modified("python", change)
    _valid(m)
    (tool,) = [r for r in m.of("message") if r["role"] == "tool"]
    assert tool["parts"][0]["text"] == EXACT and _issue_ids(m, "qwencode.content_not_inlined") == []


def test_a_count_beyond_the_aer_range_stays_out_of_the_typed_usage():
    def change(items: list[dict[str, Any]]) -> None:
        _assistants(items)[0]["message"]["usage"]["input_tokens"] = 2**60

    m = support.modified("python", change)
    _valid(m)
    mc = m.of("model_call")[0]
    assert "usage" not in mc and mc["unk"]["/usage"] == "ambiguous"
    assert "qwencode.block_usage_sum@1#/usage" in mc["rule"]
    msg = next(r for r in m.of("message") if r.get("generated_by") == mc["id"])
    assert msg["ext"]["qwencode"]["messages"][0]["usage"]["input_tokens"] == {"$int": str(2**60)}


def test_a_negative_count_stays_out_of_the_typed_usage():
    def change(items: list[dict[str, Any]]) -> None:
        _assistants(items)[0]["message"]["usage"]["output_tokens"] = -5

    m = support.modified("python", change)
    _valid(m)
    mc = m.of("model_call")[0]
    assert "usage" not in mc and mc["unk"]["/usage"] == "ambiguous"


def test_a_reported_usage_beyond_the_aer_range_is_kept_in_the_check():
    def change(items: list[dict[str, Any]]) -> None:
        next(m for m in items if m.get("type") == "result")["usage"]["input_tokens"] = 2**60

    m = support.modified("python", change)
    _valid(m)
    # no count to compare: no usage check, as for a reported value that is not an integer (the seal held 2^60 before)
    checks = {c["id"]: c for c in m.doc.seal["accounting"]["checks"]}
    assert "qwencode.acc.usage@1" not in checks and checks["qwencode.acc.turns@1"]["verdict"] == "consistent"


# ------------------------------------------------------------------------------------------------ AU-RC-1, AU-RC-2
def _citations_resolve(record: dict[str, Any]) -> None:
    from agentprov.aer.locators import pointer_exists

    for ref in record.get("rule", []):
        _rid, sep, pointer = ref.partition("#")
        assert not sep or pointer_exists(record, pointer) or pointer in record.get("unk", {}), ref
    for pointer in record.get("evf", {}):
        assert pointer_exists(record, pointer), pointer


def test_a_text_over_1_mib_with_a_lone_surrogate_moves_its_citation():
    """AU-RC-1 (D-1063): the D-378 pass cites ``qwencode.lone_surrogate_replaced@1`` at ``/parts/<k>/text``; the
    not-inlined pass that then retypes the part moves the citation to ``/parts/<k>/value``. Before, it dangled
    (``aer.ref.dangling``) and the run sealed ``adapter_defect``."""
    def change(items: list[dict[str, Any]]) -> None:
        _first_text(items)["text"] = BIG + "\ud83d"

    m = support.modified("python", change)
    _valid(m)
    (agent,) = [r for r in m.of("message") if r["role"] == "assistant" and any(p["t"] == "other" for p in r["parts"])]
    k = next(i for i, p in enumerate(agent["parts"]) if p["t"] == "other")
    assert f"qwencode.lone_surrogate_replaced@1#/parts/{k}/value" in agent["rule"]
    assert f"qwencode.content_not_inlined@1#/parts/{k}/value" in agent["rule"]
    assert not any(r.endswith(f"#/parts/{k}/text") for r in agent["rule"])
    _citations_resolve(agent)


def test_a_utf16_argument_whose_base64_exceeds_1_mib_is_its_digest():
    """AU-RC-2 (D-1063): a tool input string with a lone surrogate whose ``$utf16`` base64 exceeds 1 MiB is digested as
    a whole over its decoded text; before, the base64 inside the wrapper was replaced (``aer.schema.pattern``)."""
    text = "a" * 400_000 + "\ud800"

    def change(items: list[dict[str, Any]]) -> None:
        use = next(c for m in _assistants(items) for c in m["message"]["content"] if c.get("type") == "tool_use")
        use["input"] = {"code": text}

    m = support.modified("python", change)
    _valid(m)
    (msg,) = [r for r in m.of("message") if any(p["t"] == "tool_call" and "code" in p.get("args", {}) for p in r["parts"])]
    k = next(i for i, p in enumerate(msg["parts"]) if p["t"] == "tool_call")
    raw = text.encode("utf-8", "surrogatepass")
    assert msg["parts"][k]["args"]["code"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert f"qwencode.content_not_inlined@1#/parts/{k}/args/code" in msg["rule"]
    _citations_resolve(msg)
