"""Review UC-41 (2026-11-01; 0.2.0 change batch D-1063, regen-batch row 179): a string over 1 MiB in a TraceLogger,
DRIFT, results-container or capture message is not inlined (C.2.1(6), AER-V01) but replaced by its digest under
``agentdojo.content_not_inlined@1`` (the D-934 pattern), instead of the writer refusing the whole execution. All content is
synthetic."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from agentdojo_support import map_log, new_log

from agentprov.adapters.agentdojo import citation
from agentprov.adapters.agentdojo.not_inlined import MIB, not_inlined
from agentprov.aer.rules import load_catalogue

RULE = "agentdojo.content_not_inlined@1"
ISSUE = "agentdojo.content_not_inlined"
BIG = "x" * (MIB + 10)
DIGEST = {"not_inlined": {"sha256": hashlib.sha256(BIG.encode()).hexdigest(), "bytes": MIB + 10}}


def _issue_ids(issues: Any) -> list[str]:
    return [i for issue in issues if issue["code"] == ISSUE for i in issue["ids"]]


def test_the_rule_is_declared_class_d_and_cited_as_given():
    entry = load_catalogue("agentdojo").get(RULE)
    assert entry is not None and entry.cls == "D" and entry.citable
    assert "content_not_inlined" in load_catalogue("agentdojo").issue_codes
    assert RULE in citation.INDEPENDENT  # a transformation by AgentPROV: never an _unverified twin


def test_a_string_of_exactly_1_mib_stays_inline():
    record = {"k": "message", "id": "m0", "ev": "O", "parts": [{"t": "text", "text": "y" * MIB}]}
    assert not_inlined([record], lambda p: f"{RULE}#{p}") == [] and record["parts"][0]["text"] == "y" * MIB


def test_a_tracelogger_tool_output_over_1_mib_is_its_value_digest():
    doc = new_log()
    doc["messages"][3]["content"] = BIG
    m = map_log(doc)
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})
    tool = next(r for r in m.records if r.get("k") == "message" and r.get("role") == "tool")
    part = tool["parts"][0]
    assert part["t"] == "tool_result" and "text" not in part and part["value"] == DIGEST
    assert f"{RULE}#/parts/0/value" in tool["rule"] and tool["evf"]["/parts/0/value"] == "D"
    assert _issue_ids(m.info.issues) == [tool["id"]]
    assert m.data == map_log(doc).data  # deterministic


def test_a_tracelogger_assistant_text_over_1_mib_becomes_an_other_part():
    doc = new_log()
    doc["messages"][4]["content"] = BIG
    m = map_log(doc)
    assert not m.outcome.degenerate, m.codes
    assert m.validate().ok
    final = [r for r in m.records if r.get("k") == "message" and r.get("role") == "assistant"][-1]
    assert final["parts"][0] == {"t": "other", "type": "text", "value": DIGEST}
    assert f"{RULE}#/parts/0/value" in final["rule"]


def test_a_results_row_tool_output_over_1_mib_is_its_value_digest():
    from test_rescont import container, ok, one, row

    r = row()
    r["messages"][3]["content"] = BIG
    m = one(container([r]))
    assert not m.outcome.degenerate, m.codes
    ok(m)
    tool = next(rec for rec in m.records if rec.get("k") == "message" and rec.get("role") == "tool")
    assert tool["parts"][0]["value"] == DIGEST and f"{RULE}#/parts/0/value" in tool["rule"]
    assert _issue_ids(m.info.issues) == [tool["id"]]


def test_a_drift_tool_output_over_1_mib_is_its_value_digest():
    from test_drift import _entry, _raw, map_drift

    entry = _entry("banking/user_task_12/important_instructions/injection_task_7")
    doc = json.loads(_raw(entry))
    tool = next(msg for msg in doc["conversations"] if isinstance(msg, dict) and msg.get("role") == "tool")
    if isinstance(tool["content"], str):
        tool["content"] = BIG
    else:  # content blocks
        block = next(b for b in tool["content"] if isinstance(b, dict) and isinstance(b.get("content", b.get("text")), str))
        block["content" if "content" in block else "text"] = BIG
    m = map_drift(json.dumps(doc, indent=4).encode(), entry["original_path"])
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})
    changed = _issue_ids(m.info.issues)
    assert changed and all(any(str(r).startswith(RULE) for r in m.get(i).get("rule", ())) for i in changed)
    assert DIGEST in [p.get("value") for i in changed for p in m.get(i).get("parts", ())]


def test_a_capture_tool_output_over_1_mib_is_its_value_digest():
    from test_uc_capture_findings import _ok, _seal, _session

    m = _seal(_session(tool_text=BIG))
    _ok(m)
    tool = next(r for r in m.of_kind("message") if r.get("role") == "tool")
    assert tool["parts"][0]["t"] == "tool_result" and tool["parts"][0]["value"] == DIGEST
    assert f"{RULE}#/parts/0/value" in tool["rule"]
    [te] = m.of_kind("tool_execution")
    assert te["returned"] == DIGEST  # a Json position keeps the digest object in place
    assert set(_issue_ids(m.info.issues)) == {tool["id"], te["id"]}


#: A string with a lone surrogate (C.11.3) whose UTF-8 is under 1 MiB but whose ``$utf16`` base64, which the writer
#: measures (AER-V01), is over it: 400,001 UTF-16 code units are 800,002 bytes, 1,066,672 base64 digits.
SPLIT = "a" * 400_000 + "\ud800"
SPLIT_DIGEST = {"not_inlined": {"sha256": hashlib.sha256(SPLIT.encode("utf-8", "surrogatepass")).hexdigest(),
                                "bytes": 400_003}}


def _utf16(text: str) -> dict[str, str]:
    return {"$utf16": base64.b64encode(text.encode("utf-16-be", "surrogatepass")).decode("ascii")}


def test_a_utf16_value_whose_base64_exceeds_1_mib_is_not_inlined():
    """Regen-batch row 186 (the AU-RC-2 rule): the writer refused the wrapper (``aer.string.inline_limit``) and the
    log sealed ``adapter_defect``; now the wrapper is replaced whole by the digest of its decoded text."""
    doc = new_log()
    args = {"recipient": SPLIT, "amount": 10.0}
    doc["messages"][2]["tool_calls"][0]["args"] = args
    doc["messages"][3]["tool_call"]["args"] = dict(args)
    m = map_log(doc)
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})
    [te] = [r for r in m.records if r.get("k") == "tool_execution"]
    assert te["args"]["recipient"] == SPLIT_DIGEST and te["evf"]["/args/recipient"] == "D"
    assert f"{RULE}#/args/recipient" in te["rule"] and te["id"] in _issue_ids(m.info.issues)


def test_a_utf16_value_whose_base64_is_at_most_1_mib_stays():
    wrapper = _utf16("a" * 393_215 + "\ud800")  # 786,432 bytes of UTF-16: exactly 1 MiB of base64
    assert len(wrapper["$utf16"]) == MIB
    record = {"k": "tool_execution", "id": "te0", "ev": "O", "args": {"q": dict(wrapper)}}
    assert not_inlined([record], lambda p: f"{RULE}#{p}") == [] and record["args"]["q"] == wrapper
    over = {"k": "tool_execution", "id": "te1", "ev": "O", "args": {"q": _utf16("a" * 393_216 + "\ud800")}}
    assert not_inlined([over], lambda p: f"{RULE}#{p}") == ["te1"] and "not_inlined" in over["args"]["q"]
