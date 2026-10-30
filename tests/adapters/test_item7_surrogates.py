"""Regeneration-batch item 7 (escaping audit F-01, D-23, D-378): a lone UTF-16 surrogate in source text no longer turns the
execution into a degenerate ``adapter_defect`` AER. In a typed string position (a part's ``text``, a tool ``name``) and
in an object key it is replaced by U+FFFD, the pointer is tagged and cites ``<ns>.lone_surrogate_replaced@1``, and an
info issue lists the records; a ``$utf16`` value in a ``Json`` position is kept (lossless there). aer/0.1 is unchanged.
Synthetic sources only (written with ``ensure_ascii``, so the surrogate is an escape, as in the audit's input)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "agentdojo"))
sys.path.insert(0, str(_HERE / "inspect"))

import inspect_support as isup  # noqa: E402
from test_agentdyn import _block, _call, a_log, map_a  # noqa: E402

from agentprov.adapters.surrogates import has_lone_surrogate, scrub_keys, scrub_record  # noqa: E402

CUT = "cut mid-emoji \ud83d"


def test_scrub_record_replaces_typed_positions_and_keeps_json_values():
    import base64

    utf16 = {"$utf16": base64.b64encode(CUT.encode("utf-16-be", "surrogatepass")).decode("ascii")}
    record = {"k": "message", "id": "m3", "ev": "O", "parts": [{"t": "text", "text": dict(utf16)},
                                                                {"t": "tool_call", "name": "x", "args": {"q": dict(utf16)}}]}
    replaced = scrub_record(record, lambda p: f"tst.r@1#{p}")
    assert replaced == ["/parts/0/text"]
    assert record["parts"][0]["text"] == "cut mid-emoji �" and record["parts"][1]["args"] == {"q": utf16}
    assert record["evf"] == {"/parts/0/text": "D"} and record["rule"] == ["tst.r@1#/parts/0/text"]


def test_scrub_keys_returns_the_object_when_nothing_changes():
    doc: dict[str, Any] = {"a": [{"b": "c"}]}
    assert scrub_keys(doc) == (doc, False) and scrub_keys(doc)[0] is doc
    assert scrub_keys({"k\ud800": 1}) == ({"k�": 1}, True)


def test_a_tracelogger_log_with_lone_surrogates_maps_and_validates():
    call = _call("get_shopping_account_user_information", {"k\ud800": "v"}, "call_1")
    doc = a_log(messages=[
        {"role": "system", "content": _block("You are a helpful assistant.")},
        {"role": "user", "content": _block("Show my account.")},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "content": _block("tool output " + CUT), "tool_call_id": "call_1", "tool_call": call, "error": None},
        {"role": "assistant", "content": _block(CUT), "tool_calls": []},
    ])
    m = map_a(doc)
    assert "adapter_defect" not in m.codes
    report = m.validate()
    assert report.ok and report.passed, [(f.code, f.pointer) for f in report.errors]
    final = m.of_kind("message")[-1]
    assert final["parts"][0]["text"] == "cut mid-emoji �" and final["evf"]["/parts/0/text"] == "D"
    assert "agentdojo.lone_surrogate_replaced@1#/parts/0/text" in final["rule"]
    (issue,) = m.issues("agentdojo.lone_surrogate_replaced")
    assert "exec" in issue["ids"] and final["id"] in issue["ids"]  # the key was replaced too
    assert not any(has_lone_surrogate(line) for line in m.data.decode("utf-8").splitlines())


def test_an_inspect_sample_with_a_lone_surrogate_maps_and_validates(tmp_path):
    def tune(s: isup.Sample, sample: dict[str, Any]) -> None:
        for message in sample["messages"]:
            if message["role"] == "assistant" and message["content"] == "Synthetic final answer.":
                message["content"] = CUT
        for message in sample["events_data"]["messages"]:
            if message["role"] == "assistant" and message["content"] == "Synthetic final answer.":
                message["content"] = CUT
        for e in sample["events"]:
            for choice in (e.get("output") or {}).get("choices", []):
                if choice["message"]["content"] == "Synthetic final answer.":
                    choice["message"]["content"] = CUT
    data = isup.build_eval(isup.synthetic_header(), {"s1_epoch_1.json": isup.basic_sample(tune=tune)})
    imported = isup.import_log(data, tmp_path / "raw")
    (unit,) = imported.units
    assert not {i["code"] for i in unit.info.issues} & {"adapter_defect"}
    assert "inspect.lone_surrogate_replaced" in {i["code"] for i in unit.info.issues}
    texts = [p.get("text") for m in unit.of_kind("message") for p in m["parts"]]
    assert "cut mid-emoji �" in texts
