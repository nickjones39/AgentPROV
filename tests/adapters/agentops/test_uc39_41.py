"""D-1063 (regen-batch row 176; review UC-39, UC-40, UC-41): source values the AER cannot hold in a typed field no
longer turn a run into a degenerate ``adapter_defect`` AER. Runs built here in memory (never written to disk).

* UC-39: a step's token count outside the AER's count domain (negative, fractional, beyond 2^53-1, not a number) stays
  out of the typed usage, verbatim in ``ext.agentops.usage_reported``; a call timestamp that is not a string stays out of
  ``t.raw``, verbatim in ``ext.agentops.timestamp``;
* UC-40: a lone UTF-16 surrogate in a typed text field (and in an object key) is replaced by U+FFFD with the D-378
  disclosure (``agentops.lone_surrogate_replaced@1``);
* UC-41: a string over 1 MiB of UTF-8 is not inlined (``agentops.content_not_inlined@1``); a string of exactly 1 MiB is.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import agentops_support as support
import pytest
from agentops_support import _call, _result, run_json, step

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

CUT = "cut mid-emoji \ud83d"
BIG = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1 << 15 + 1))[: (1 << 20) + 1]
EXACT = BIG[: 1 << 20]
SCHEMA = json.loads((support.REPO / "src" / "agentprov" / "adapters" / "agentops" / "ext.schema.json").read_bytes())


def _map(run: dict[str, Any]) -> support.Mapped:
    label = f"pilot_v1_seeded/gpt/openai_gpt-x/{run['condition']}/safety_001_run1.json"
    m = support.map_label(label, data=json.dumps(run).encode(), tasks={})
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes(), m.codes()
    for mode in ("dev", "release"):
        report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode=mode)
        assert report.ok, (mode, [(f.code, f.pointer) for f in report.findings][:5])
    import jsonschema

    validator = jsonschema.Draft202012Validator(SCHEMA)
    for rec in m.records:
        ext = rec.get("ext", {}).get("agentops")
        if ext is not None:
            assert list(validator.iter_errors(ext)) == [], rec["id"]
    return m


def _issue_ids(m: support.Mapped, code: str) -> list[str]:
    return [i for issue in m.issues if issue["code"] == code for i in issue["ids"]]


def _plain() -> list[dict[str, Any]]:
    return [step(1, [_call("run_python")], [_result("run_python", "ok")]), step(2, [], [], reasoning="done")]


@pytest.mark.parametrize("bad", [-1, 2**53, 2**60, 1.5, "10", None])
def test_a_count_outside_the_aer_range_stays_out_of_the_typed_usage(bad):
    steps = _plain()
    steps[0]["llm_input_tokens"] = bad
    m = _map(run_json(steps))
    mc = m.of("model_call")[0]
    assert mc["usage"] == {"output_tokens": 5}
    expected = {"$int": str(bad)} if isinstance(bad, int) and bad > 2**53 - 1 else bad  # the lossless C.11.3 form
    assert mc["ext"]["agentops"]["usage_reported"] == {"llm_input_tokens": expected}
    assert mc["unk"]["/usage/input_tokens"] == "ambiguous"
    assert m.of("model_call")[1]["usage"] == {"input_tokens": 10, "output_tokens": 5}  # in range: unchanged


def test_two_counts_outside_the_range_leave_no_typed_usage():
    steps = _plain()
    steps[0].update(llm_input_tokens=-3, llm_output_tokens=2**64)
    mc = _map(run_json(steps)).of("model_call")[0]
    assert "usage" not in mc and mc["unk"]["/usage"] == "ambiguous" and "/usage" not in mc.get("evf", {})
    assert mc["ext"]["agentops"]["usage_reported"] == {"llm_input_tokens": -3, "llm_output_tokens": {"$int": str(2**64)}}


def test_a_negative_zero_count_stays_out_of_the_typed_usage():
    """AU-NC-306 (D-1063): ``-0.0`` is an integral float with ``0 <= -0.0``, so ``_count`` admitted it and the writer
    refused the typed usage (``aer.schema.pattern``); it now stays verbatim in ``ext.agentops.usage_reported``."""
    steps = _plain()
    steps[0]["llm_input_tokens"] = -0.0
    mc = _map(run_json(steps)).of("model_call")[0]
    assert mc["usage"] == {"output_tokens": 5} and mc["unk"]["/usage/input_tokens"] == "ambiguous"
    assert "llm_input_tokens" in mc["ext"]["agentops"]["usage_reported"]


def test_an_integral_float_count_stays_typed_as_before():
    steps = _plain()
    steps[0]["llm_input_tokens"] = 7.0
    mc = _map(run_json(steps)).of("model_call")[0]
    assert mc["usage"]["input_tokens"] == 7 and "usage_reported" not in mc.get("ext", {}).get("agentops", {})


@pytest.mark.parametrize("bad", [1767225600, None, {"t": 1}])
def test_a_call_timestamp_that_is_not_a_string_stays_out_of_the_typed_time(bad):
    steps = _plain()
    steps[0]["tool_calls"][0]["timestamp"] = bad
    te = _map(run_json(steps)).of("tool_execution")[0]
    assert "t" not in te and te["ext"]["agentops"]["timestamp"] == bad and te["unk"]["/t/start"] == "ambiguous"


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    steps = [step(1, [_call("run_python", {"k\ud800": CUT})], [_result("run_python", CUT)], reasoning=CUT),
             step(2, [], [], reasoning="done")]
    m = _map(run_json(steps))
    msg = m.of("message")[0]
    assert msg["parts"][0]["text"] == "cut mid-emoji �" and msg["evf"]["/parts/0/text"] == "D"
    assert "agentops.lone_surrogate_replaced@1#/parts/0/text" in msg["rule"]
    args = msg["parts"][1]["args"]  # the key is replaced (scrub_keys); the Json value keeps its lossless $utf16 form
    assert list(args) == ["k�"] and set(args["k�"]) == {"$utf16"}
    tool = [r for r in m.of("message") if r["role"] == "tool"][0]
    assert tool["parts"][0]["text"] == "cut mid-emoji �"
    ids = _issue_ids(m, "agentops.lone_surrogate_replaced")
    assert "exec" in ids and msg["id"] in ids and tool["id"] in ids
    (issue,) = [i for i in m.issues if i["code"] == "agentops.lone_surrogate_replaced"]
    assert issue["rule"] == "agentops.lone_surrogate_replaced@1"


def _digest(value: str) -> dict[str, Any]:
    raw = value.encode()
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def test_a_string_over_1_mib_is_not_inlined():
    steps = [step(1, [_call("run_python")], [_result("run_python", BIG)], reasoning=BIG), step(2, [], [], reasoning="done")]
    m = _map(run_json(steps))
    msg = m.of("message")[0]
    assert msg["parts"][0] == {"t": "other", "type": "text", "value": _digest(BIG)}
    assert msg["evf"]["/parts/0/value"] == "D" and "agentops.content_not_inlined@1#/parts/0/value" in msg["rule"]
    tool = [r for r in m.of("message") if r["role"] == "tool"][0]
    part = tool["parts"][0]
    assert part["t"] == "tool_result" and "text" not in part and part["value"] == _digest(BIG)
    assert tool["evf"]["/parts/0/value"] == "D"
    assert sorted(_issue_ids(m, "agentops.content_not_inlined")) == sorted([msg["id"], tool["id"]])


def test_a_string_of_exactly_1_mib_stays_inline():
    steps = [step(1, [_call("run_python")], [_result("run_python", EXACT)]), step(2, [], [], reasoning="done")]
    m = _map(run_json(steps))
    tool = [r for r in m.of("message") if r["role"] == "tool"][0]
    assert tool["parts"][0]["text"] == EXACT and _issue_ids(m, "agentops.content_not_inlined") == []


# ------------------------------------------------------------------------------------------------ AU-RC-1, AU-RC-2
def _citations_resolve(record: dict[str, Any]) -> None:
    """Every scoped citation, ``evf`` key and ``ext.agentops.redacted`` pointer names a field the record holds."""
    from agentprov.aer.locators import pointer_exists

    for ref in record.get("rule", []):
        _rid, sep, pointer = ref.partition("#")
        assert not sep or pointer_exists(record, pointer) or pointer in record.get("unk", {}), ref
    for entry in record.get("ext", {}).get("agentops", {}).get("redacted", []):
        assert pointer_exists(record, entry["p"]), entry
    for pointer in record.get("evf", {}):
        assert pointer_exists(record, pointer), pointer


@pytest.mark.parametrize(("label", "result"), [("account path", "see /Users/alice/x " + BIG), ("lone surrogate", BIG + "\ud83d")])
def test_a_cited_text_over_1_mib_moves_with_its_citations(label, result):
    """AU-RC-1 (D-1063): a tool output over 1 MiB that the D-608 redaction or the D-378 surrogate pass cited at
    ``/parts/0/text`` takes the citation, its ``evf`` tag and its ``ext.agentops.redacted`` entry to ``/parts/0/value``;
    before, they dangled (``aer.ref.dangling``) and the run sealed ``adapter_defect``."""
    steps = [step(1, [_call("run_python")], [_result("run_python", result)]), step(2, [], [], reasoning="done")]
    m = _map(run_json(steps))
    tool = [r for r in m.of("message") if r["role"] == "tool"][0]
    part = tool["parts"][0]
    assert "text" not in part and set(part["value"]) == {"not_inlined"}
    assert not any(r.endswith("#/parts/0/text") for r in tool["rule"])
    rule = "agentops.value_redacted@1" if label == "account path" else "agentops.lone_surrogate_replaced@1"
    assert f"{rule}#/parts/0/value" in tool["rule"] and "agentops.content_not_inlined@1#/parts/0/value" in tool["rule"]
    if label == "account path":
        assert [e["p"] for e in tool["ext"]["agentops"]["redacted"]] == ["/parts/0/value"]
    _citations_resolve(tool)


def test_a_utf16_argument_whose_base64_exceeds_1_mib_is_its_digest():
    """AU-RC-2 (D-1063): a tool argument holding a lone surrogate is ``{"$utf16": <base64>}``; when that base64 exceeds
    1 MiB the whole value becomes the digest of the decoded text (the writer measures the base64), never a digest inside
    the wrapper (``aer.schema.pattern``)."""
    text = "a" * 400_000 + "\ud800"
    steps = [step(1, [_call("run_python", {"code": text})], [_result("run_python", "ok")]), step(2, [], [], reasoning="done")]
    msg = _map(run_json(steps)).of("message")[0]
    raw = text.encode("utf-8", "surrogatepass")
    (call,) = [p for p in msg["parts"] if p["t"] == "tool_call"]
    k = msg["parts"].index(call)
    assert call["args"]["code"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert f"agentops.content_not_inlined@1#/parts/{k}/args/code" in msg["rule"]
    _citations_resolve(msg)


def test_a_short_utf16_argument_keeps_its_lossless_form():
    steps = [step(1, [_call("run_python", {"code": "a" * 1000 + "\ud800"})], [_result("run_python", "ok")]),
             step(2, [], [], reasoning="done")]
    m = _map(run_json(steps))
    (call,) = [p for p in m.of("message")[0]["parts"] if p["t"] == "tool_call"]
    assert set(call["args"]["code"]) == {"$utf16"} and _issue_ids(m, "agentops.content_not_inlined") == []
