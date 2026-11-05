"""D-1063 (regen-batch row 176; review UC-39, UC-40, UC-41): derived wire-log runs (the fixtures' logs changed in memory,
compact re-serialisation with ``ensure_ascii``, never written to disk).

* UC-39: a usage count beyond the AER's integer domain (2^53 - 1) never reaches the typed ``usage`` of a model call; it
  stays verbatim in ``ext.wirelog.usage_extra`` (the family's place for usage members without a slot).
* UC-40: a lone UTF-16 surrogate in a typed text field or an object key is replaced by U+FFFD (the D-378 pass,
  ``wirelog.lone_surrogate_replaced@1``) instead of making the run degenerate.
* UC-41: a string over 1 MiB is not inlined (``wirelog.content_not_inlined@1``, the D-934 pattern).
"""

from __future__ import annotations

import hashlib
from typing import Any

import wirelog_support as support

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

CUT = "cut mid-emoji \ud83d"
MAX = 2**53 - 1
R_SURROGATE = "wirelog.lone_surrogate_replaced@1"
R_NOT_INLINED = "wirelog.content_not_inlined@1"
BIG = "x" * ((1 << 20) + 1)
EXACT = "y" * (1 << 20)


def _valid(m: support.Mapped) -> None:
    assert "adapter_defect" not in m.codes(), m.codes()
    rep = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
    assert not rep.findings, sorted({(f.code, f.pointer) for f in rep.findings})


def _issue_ids(m: support.Mapped, code: str) -> list[str]:
    return [i for issue in m.issues if issue["code"] == code for i in issue["ids"]]


def _last_text(text: str) -> Any:
    def change(responses: list[Any]) -> None:
        blocks = responses[-1]["output"]["message"]["content"]
        k = next(k for k, b in enumerate(blocks) if "text" in b)
        blocks[k] = {"text": text}

    return change


def _final(m: support.Mapped) -> dict[str, Any]:
    return [r for r in m.of("message") if r["role"] == "assistant"][-1]


def test_a_count_beyond_the_aer_range_stays_out_of_the_typed_usage():
    def big(responses: list[Any]) -> None:
        responses[0]["usage"]["inputTokens"] = MAX + 1

    m = support.modified("zero_calls", responses=big)
    _valid(m)
    mc = m.of("model_call")[0]
    assert "input_tokens" not in mc["usage"]
    assert mc["ext"]["wirelog"]["usage_extra"]["inputTokens"] == {"$int": str(MAX + 1)}


def test_a_reported_total_beyond_the_aer_range_is_unverifiable():
    m = support.modified("zero_calls", meta=lambda v: v.update(input_tokens=MAX + 1))
    _valid(m)
    (check,) = [c for cid, c in m.checks().items() if cid.startswith("wirelog.acc.usage_totals")]
    assert check["verdict"] == "unverifiable" and check["reason"] == "totals_out_of_range"


def test_a_negative_reported_total_is_unverifiable():
    """AU-NC-303 (D-1063, regen-batch row 181): a negative meta.json total inside the I-JSON range is outside the AER's
    count domain too; the check is unverifiable instead of the writer refusing the seal."""
    for key, value in (("input_tokens", -5), ("output_tokens", -1), ("input_tokens", -MAX - 1)):
        m = support.modified("zero_calls", meta=lambda v, key=key, value=value: v.update({key: value}))
        _valid(m)
        (check,) = [c for cid, c in m.checks().items() if cid.startswith("wirelog.acc.usage_totals")]
        assert check["verdict"] == "unverifiable" and check["reason"] == "totals_out_of_range", (key, value)


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    def task(requests: list[Any]) -> None:
        for request in requests:
            request["messages"][0]["content"][0]["text"] += "\ud83d"

    m = support.modified("zero_calls", requests=task, responses=_last_text(CUT))
    _valid(m)
    final = _final(m)
    k = next(k for k, p in enumerate(final["parts"]) if p["t"] == "text")
    assert final["parts"][k]["text"] == "cut mid-emoji �"
    assert final["evf"][f"/parts/{k}/text"] == "D" and f"{R_SURROGATE}#/parts/{k}/text" in final["rule"]
    task_msg = next(r for r in m.of("message") if r["role"] == "user")
    assert task_msg["parts"][0]["text"].endswith("�")
    ids = _issue_ids(m, "wirelog.lone_surrogate_replaced")
    assert final["id"] in ids and task_msg["id"] in ids


def test_a_lone_surrogate_in_a_key_is_replaced():
    def block(responses: list[Any]) -> None:
        responses[-1]["output"]["message"]["content"].insert(0, {"reasoning\udc00": {"text": "x"}})

    m = support.modified("zero_calls", responses=block)
    _valid(m)
    other = next(p for p in _final(m)["parts"] if p["t"] == "other")
    assert other["type"] == "reasoning�" and other["value"] == {"reasoning�": {"text": "x"}}
    assert "exec" in _issue_ids(m, "wirelog.lone_surrogate_replaced")


def test_a_string_over_1_mib_is_not_inlined():
    m = support.modified("zero_calls", responses=_last_text(BIG))
    _valid(m)
    final = _final(m)
    k = next(k for k, p in enumerate(final["parts"]) if p["t"] == "other")
    digest = {"not_inlined": {"sha256": hashlib.sha256(BIG.encode()).hexdigest(), "bytes": len(BIG)}}
    assert final["parts"][k] == {"t": "other", "type": "text", "value": digest}
    assert final["evf"][f"/parts/{k}/value"] == "D" and f"{R_NOT_INLINED}#/parts/{k}/value" in final["rule"]
    assert _issue_ids(m, "wirelog.content_not_inlined") == [final["id"]]


def test_a_text_over_1_mib_with_a_lone_surrogate_keeps_its_citations():
    """AU-RC-1 (D-1063, regen-batch row 181; UC-38's fix carried over): the surrogate pass cites its rule at
    ``/parts/<k>/text`` before the not-inlined pass retypes that field; the citation and the evf key follow it to
    ``/parts/<k>/value`` instead of dangling (aer.ref.dangling, adapter_defect)."""
    m = support.modified("zero_calls", responses=_last_text(BIG + "\ud83d"))
    _valid(m)
    final = _final(m)
    k = next(k for k, p in enumerate(final["parts"]) if p["t"] == "other")
    raw = (BIG + "�").encode()
    assert final["parts"][k] == {"t": "other", "type": "text",
                                 "value": {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}}
    assert f"{R_SURROGATE}#/parts/{k}/value" in final["rule"] and f"{R_NOT_INLINED}#/parts/{k}/value" in final["rule"]
    assert not any(r.endswith(f"/parts/{k}/text") for r in final["rule"]) and f"/parts/{k}/text" not in final["evf"]
    assert final["id"] in _issue_ids(m, "wirelog.lone_surrogate_replaced")
    assert _issue_ids(m, "wirelog.content_not_inlined") == [final["id"]]


def _call_with(value: str) -> Any:
    def change(responses: list[Any]) -> None:
        responses[-1]["output"]["message"]["content"].append(
            {"toolUse": {"toolUseId": "tu-big", "name": "read_file", "input": {"q": value}}})

    return change


def test_a_utf16_value_is_measured_by_its_text():
    """AU-RC-2 (D-1063, regen-batch row 181): a Json-position string with a lone surrogate is written as
    ``{"$utf16": <base64>}``; when that base64 exceeds 1 MiB (what the writer measures) the wrapper is replaced as a
    whole by the digest of its decoded text, never inside it (an invalid reserved form, aer.schema.pattern)."""
    kept = support.modified("zero_calls", responses=_call_with("a" * 300_000 + "\ud800"))  # base64: 800,004 characters
    _valid(kept)
    (call,) = [p for p in _final(kept)["parts"] if p["t"] == "tool_call"]
    assert set(call["args"]["q"]) == {"$utf16"} and _issue_ids(kept, "wirelog.content_not_inlined") == []
    text = "a" * 400_000 + "\ud800"  # base64: 1,066,672 characters; the text: 400,003 bytes
    digested = support.modified("zero_calls", responses=_call_with(text))
    _valid(digested)
    final = _final(digested)
    k, call = next((k, p) for k, p in enumerate(final["parts"]) if p["t"] == "tool_call")
    raw = text.encode("utf-8", "surrogatepass")
    assert call["args"]["q"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert f"{R_NOT_INLINED}#/parts/{k}/args/q" in final["rule"]


def test_a_utf16_value_whose_text_exceeds_1_mib_is_digested_though_its_base64_does_not():
    """Regen-batch row 186 (one shared pass): a ``$utf16`` value is replaced when its decoded text OR its base64 exceeds
    1 MiB. 350,001 code units of CJK text and a lone surrogate: base64 933,336 characters, text 1,050,003 bytes of UTF-8.
    Row 181's pass kept this wrapper (it measured the base64 only)."""
    text = "中" * 350_000 + "\ud800"
    m = support.modified("zero_calls", responses=_call_with(text))
    _valid(m)
    final = _final(m)
    k, call = next((k, p) for k, p in enumerate(final["parts"]) if p["t"] == "tool_call")
    raw = text.encode("utf-8", "surrogatepass")
    assert call["args"]["q"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert f"{R_NOT_INLINED}#/parts/{k}/args/q" in final["rule"] and final["id"] in _issue_ids(m, "wirelog.content_not_inlined")


def test_a_string_of_exactly_1_mib_stays_inline():
    m = support.modified("zero_calls", responses=_last_text(EXACT))
    _valid(m)
    assert any(p.get("text") == EXACT for p in _final(m)["parts"])
    assert _issue_ids(m, "wirelog.content_not_inlined") == []
    assert not any(r.startswith(R_NOT_INLINED) for rec in m.records for r in rec.get("rule", ()))
