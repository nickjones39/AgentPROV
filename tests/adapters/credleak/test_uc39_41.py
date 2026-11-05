"""D-1063 (regen-batch row 176; review UC-40, UC-41, and the UC-39 class): source values the AER cannot hold in a typed
field no longer turn a run into a degenerate ``adapter_defect`` AER. Cells built here in memory (never written to disk).

* UC-40: a lone UTF-16 surrogate in a typed text field (and in an object key) is replaced by U+FFFD with the D-378
  disclosure (``credleak.lone_surrogate_replaced@1``);
* UC-41: a string over 1 MiB of UTF-8 is not inlined (``credleak.content_not_inlined@1``); a string of exactly 1 MiB is;
* the UC-39 class: a ``toolCallCount`` beyond the AER's count domain makes the count check unverifiable instead of a
  seal the writer refuses.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import credleak_support as support
import pytest

from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records

CUT = "cut mid-emoji \ud83d"
BIG = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1 << 15 + 1))[: (1 << 20) + 1]
EXACT = BIG[: 1 << 20]


def _map(cell: dict[str, Any]) -> support.Mapped:
    [m] = support.map_cell("cell.json", json.dumps(cell).encode(), sem=False, prov=False)
    assert "adapter_defect" not in m.codes(), m.codes()
    for mode in ("dev", "release"):
        report = validate_records([*m.doc.records, m.doc.seal], store=None, catalogues=RuleRegistry.default(), mode=mode)
        assert report.ok, (mode, [(f.code, f.pointer) for f in report.findings][:5])
    return m


def _cell(**turn: Any) -> dict[str, Any]:
    cell = json.loads(support.synthetic_cell())
    cell["runs"][0]["turns"][0].update(turn)
    return cell


def _issue_ids(m: support.Mapped, code: str) -> list[str]:
    return [i for issue in m.issues if issue["code"] == code for i in issue["ids"]]


def _messages(m: support.Mapped, role: str) -> list[dict[str, Any]]:
    return [r for r in m.records if r["k"] == "message" and r.get("role") == role]


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    cell = _cell(userMessage=CUT, assistantResponse=CUT)
    cell["runs"][0]["turns"][0]["toolCalls"][0].update(output=CUT, input={"k\ud800": CUT})
    m = _map(cell)
    (user,) = _messages(m, "user")
    assert user["parts"][0]["text"] == "cut mid-emoji \N{REPLACEMENT CHARACTER}" and user["evf"]["/parts/0/text"] == "D"
    assert "credleak.lone_surrogate_replaced@1#/parts/0/text" in user["rule"]
    (tool,) = _messages(m, "tool")
    assert tool["parts"][0]["text"] == "cut mid-emoji \N{REPLACEMENT CHARACTER}"
    call = _messages(m, "assistant")[0]
    args = call["parts"][0]["args"]  # the key is replaced (scrub_keys); the Json value keeps its lossless $utf16 form
    assert list(args) == ["k\N{REPLACEMENT CHARACTER}"] and set(args["k\N{REPLACEMENT CHARACTER}"]) == {"$utf16"}
    ids = _issue_ids(m, "credleak.lone_surrogate_replaced")
    assert "exec" in ids and user["id"] in ids and tool["id"] in ids
    (issue,) = [i for i in m.issues if i["code"] == "credleak.lone_surrogate_replaced"]
    assert issue["rule"] == "credleak.lone_surrogate_replaced@1"


def _digest(value: str) -> dict[str, Any]:
    raw = value.encode()
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def test_a_string_over_1_mib_is_not_inlined():
    cell = _cell(userMessage=BIG)
    cell["runs"][0]["turns"][0]["toolCalls"][0]["output"] = BIG
    m = _map(cell)
    (user,) = _messages(m, "user")
    assert user["parts"] == [{"t": "other", "type": "text", "value": _digest(BIG)}]
    assert user["evf"]["/parts/0/value"] == "D" and "credleak.content_not_inlined@1#/parts/0/value" in user["rule"]
    (tool,) = _messages(m, "tool")
    part = tool["parts"][0]
    assert part["t"] == "tool_result" and "text" not in part and part["value"] == _digest(BIG)
    assert tool["evf"]["/parts/0/value"] == "D"
    assert sorted(_issue_ids(m, "credleak.content_not_inlined")) == sorted([user["id"], tool["id"]])


def test_a_string_of_exactly_1_mib_stays_inline():
    cell = _cell()
    cell["runs"][0]["turns"][0]["toolCalls"][0]["output"] = EXACT
    m = _map(cell)
    (tool,) = _messages(m, "tool")
    assert tool["parts"][0]["text"] == EXACT and _issue_ids(m, "credleak.content_not_inlined") == []


@pytest.mark.parametrize("count", [2**53, 2**60])
def test_a_tool_call_count_beyond_the_aer_range_is_unverifiable(count):
    cell = json.loads(support.synthetic_cell(toolCallCount=count))
    m = _map(cell)
    (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "credleak.acc.tool_call_count@1"]
    assert check["verdict"] == "unverifiable" and check["reason"] == "count_out_of_range"
    assert check["observed"] == {"tool_calls": 1, "turns": 1}


def test_a_tool_call_count_in_range_is_compared_as_before():
    m = _map(json.loads(support.synthetic_cell(toolCallCount=1)))
    (check,) = [c for c in m.doc.seal["accounting"]["checks"] if c["id"] == "credleak.acc.tool_call_count@1"]
    assert check["verdict"] == "consistent" and check["observed"]["tool_call_count"] == 1


# ------------------------------------------------------------------------------------------------ AU-RC-1, AU-RC-2
def _citations_resolve(record: dict[str, Any]) -> None:
    """Every scoped citation, ``evf`` key and ``ext.credleak.redacted`` pointer names a field the record holds."""
    from agentprov.aer.locators import pointer_exists

    for ref in record.get("rule", []):
        _rid, sep, pointer = ref.partition("#")
        assert not sep or pointer_exists(record, pointer) or pointer in record.get("unk", {}), ref
    for entry in record.get("ext", {}).get("credleak", {}).get("redacted", []):
        assert pointer_exists(record, entry["p"]), entry
    for pointer in record.get("evf", {}):
        assert pointer_exists(record, pointer), pointer


@pytest.mark.parametrize(("label", "output"), [("account path", "/home/alice/x " + BIG), ("lone surrogate", BIG + "\ud83d")])
def test_a_cited_output_over_1_mib_moves_with_its_citations(label, output):
    """AU-RC-1 (D-1063): a tool output over 1 MiB that the D-605 redaction or the D-378 surrogate pass cited at
    ``/parts/0/text`` takes the citation, its ``evf`` tag and its ``ext.credleak.redacted`` entry to ``/parts/0/value``;
    before, they dangled (``aer.ref.dangling``) and the run sealed ``adapter_defect``."""
    m = _map(json.loads(support.synthetic_cell(output=output)))
    (tool,) = _messages(m, "tool")
    part = tool["parts"][0]
    assert "text" not in part and set(part["value"]) == {"not_inlined"}
    assert not any(r.endswith("#/parts/0/text") for r in tool["rule"])
    rule = "credleak.value_redacted@1" if label == "account path" else "credleak.lone_surrogate_replaced@1"
    assert f"{rule}#/parts/0/value" in tool["rule"] and "credleak.content_not_inlined@1#/parts/0/value" in tool["rule"]
    if label == "account path":
        assert [e["p"] for e in tool["ext"]["credleak"]["redacted"]] == ["/parts/0/value"]
    _citations_resolve(tool)


def test_a_utf16_argument_whose_base64_exceeds_1_mib_is_its_digest():
    """AU-RC-2 (D-1063): a tool input string holding a lone surrogate whose ``$utf16`` base64 exceeds 1 MiB becomes the
    digest of the decoded text as a whole (the writer measures the base64), never a digest inside the wrapper."""
    text = "a" * 400_000 + "\ud800"
    cell = _cell()
    cell["runs"][0]["turns"][0]["toolCalls"][0]["input"] = {"code": text}
    m = _map(cell)
    call = _messages(m, "assistant")[0]
    raw = text.encode("utf-8", "surrogatepass")
    assert call["parts"][0]["args"]["code"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert "credleak.content_not_inlined@1#/parts/0/args/code" in call["rule"]
    _citations_resolve(call)
