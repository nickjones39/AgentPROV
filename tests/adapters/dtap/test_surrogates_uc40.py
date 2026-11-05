"""UC-40 (dtap's share): the D-378 lone-surrogate pass. A lone UTF-16 surrogate in a typed text field (a tool result's
text, a tool name) or in an object key made the writer refuse the run (``adapter_defect``); it is now replaced by U+FFFD
under ``dtap.lone_surrogate_replaced@1`` and named by one info issue, while a ``$utf16`` value in a ``Json`` field is kept.
Synthetic runs only (``\\ud83d`` is half of an emoji, as a source written with ``ensure_ascii`` holds it)."""

from __future__ import annotations

import hashlib
import json

import dtap_support as support

RULE = "dtap.lone_surrogate_replaced@1"
ISSUE = "dtap.lone_surrogate_replaced"
FFFD = "�"


def _issue(m: support.Mapped) -> dict | None:  # type: ignore[type-arg]
    found = [i for i in m.issues if i["code"] == ISSUE]
    assert len(found) <= 1
    return found[0] if found else None


def _tool_message(m: support.Mapped) -> dict:  # type: ignore[type-arg]
    (msg,) = [r for r in m.records if r.get("k") == "message" and r.get("role") == "tool"]
    return msg


def test_a_lone_surrogate_in_a_typed_field_is_replaced():
    m = support.map_steps([support.call("a\ud83d", {}), support.result("a\ud83d", state="x \ud83d y")])
    msg = _tool_message(m)
    assert msg["parts"][0]["text"] == f"x {FFFD} y" and msg["parts"][0]["name"] == f"a{FFFD}"
    assert msg["evf"]["/parts/0/text"] == "D" and f"{RULE}#/parts/0/text" in msg["rule"]
    assert f"{RULE}#/parts/0/name" in msg["rule"]
    issue = _issue(m)
    assert issue is not None and issue["rule"] == RULE and msg["id"] in issue["ids"]
    assert m.header["rules"]["dtap"] == 4


def test_a_utf16_value_in_a_json_field_is_kept():
    m = support.map_steps([support.call("a", {"q": "\ud83d"}), support.result("a", state={"out": "\ud83d"})])
    value = _tool_message(m)["parts"][0]["value"]["out"]
    assert set(value) == {"$utf16"} and _issue(m) is None


def test_a_lone_surrogate_in_a_source_key_is_replaced_before_mapping():
    m = support.map_steps([support.call("a", {"k\ud83d": 1}), support.result("a", state={"q\ud83d": 1})])
    assert set(_tool_message(m)["parts"][0]["value"]) == {f"q{FFFD}"}
    issue = _issue(m)
    assert issue is not None and issue["ids"][0] == "exec"


def test_a_replaced_text_over_1_mib_is_then_not_inlined_with_its_citations():
    big = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1 << 15 + 1))[: (1 << 20) + 1]
    m = support.map_steps([support.call("a", {}), support.result("a", state=big + "\ud83d")])
    msg = _tool_message(m)
    raw = (big + FFFD).encode()
    assert msg["parts"][0]["value"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert f"{RULE}#/parts/0/value" in msg["rule"] and not any(r.endswith("#/parts/0/text") for r in msg["rule"])


def test_runs_without_a_lone_surrogate_raise_no_issue():
    m = support.map_steps([support.call("a", {}), support.result("a", state=json.dumps({"x": "é"}))])
    assert _issue(m) is None and not any(RULE in r for rec in m.records for r in rec.get("rule", ()))
