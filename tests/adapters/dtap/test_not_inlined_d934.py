"""D-934: a DTap string whose UTF-8 encoding exceeds 1 MiB is not inlined (C.2.1(6), AER-V01). A tool result's text becomes
its value digest, a user or agent text part becomes an ``other`` part of type ``text``; each is DERIVED under
``dtap.content_not_inlined@1`` and named by one info issue. Strings up to 1 MiB are unchanged. Synthetic runs only."""

from __future__ import annotations

import hashlib
import json

import dtap_support as support

RULE = "dtap.content_not_inlined@1"
BIG = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(1 << 15 + 1))[: (1 << 20) + 1]
EXACT = BIG[: 1 << 20]


def digest(value: str) -> dict[str, object]:
    raw = value.encode()
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def records(m: support.Mapped) -> dict[str, dict]:  # type: ignore[type-arg]
    return {r["id"]: r for r in m.outcome.records}


def issue_ids(m: support.Mapped) -> list[str]:
    return [i for issue in m.outcome.issues if issue["code"] == "dtap.content_not_inlined" for i in issue["ids"]]


def test_a_tool_result_over_1_mib_is_its_value_digest() -> None:
    m = support.map_steps([support.call("a", {}), support.result("a", state=BIG)])
    (msg,) = [r for r in m.outcome.records if r.get("k") == "message" and r.get("role") == "tool"]
    part = msg["parts"][0]
    assert part["t"] == "tool_result" and "text" not in part and part["value"] == digest(BIG)
    assert msg["evf"]["/parts/0/value"] == "D" and f"{RULE}#/parts/0/value" in msg["rule"]
    assert issue_ids(m) == [msg["id"]]


def test_a_user_text_over_1_mib_is_an_other_text_part() -> None:
    m = support.map_steps([{"role": "user", "state": BIG, "metadata": {}}, support.call("a", {}), support.result("a")])
    (msg,) = [r for r in m.outcome.records if r.get("k") == "message" and r.get("role") == "user"]
    assert msg["parts"] == [{"t": "other", "type": "text", "value": digest(BIG)}]
    assert msg["evf"]["/parts/0/value"] == "D" and issue_ids(m) == [msg["id"]]


def test_strings_up_to_1_mib_stay_inline() -> None:
    m = support.map_steps([support.call("a", {}), support.result("a", state=EXACT)])
    (msg,) = [r for r in m.outcome.records if r.get("k") == "message" and r.get("role") == "tool"]
    assert msg["parts"][0]["text"] == EXACT and issue_ids(m) == []
    assert not any(RULE in r for rec in m.outcome.records for r in rec.get("rule", ()))


def test_a_judge_only_unit_does_not_inline_a_judge_string_over_1_mib():
    """UC-41 (dtap's share): a judge-only directory's judge text over 1 MiB made the writer refuse the unit
    (``aer.string.inline_limit``); the judge-only path now runs the not-inlined pass too."""
    runs = support.runs_files()
    label = support.F["X02"]
    value = json.loads(runs[label])
    value["task_message"] = BIG
    m = support.map_label(label, runs={**runs, label: json.dumps(value).encode()}, tasks={})
    assert m.header["unit"] == "outcome_only"
    hits = [r for r in m.records for p, cls in r.get("evf", {}).items() if f"{RULE}#{p}" in r.get("rule", ())]
    assert hits and sorted({r["id"] for r in hits}) == issue_ids(m)
    assert BIG.encode() not in m.data
    assert json.dumps(digest(BIG), sort_keys=True, separators=(",", ":")).encode() in m.data


def test_a_utf16_value_whose_base64_exceeds_1_mib_is_its_digest() -> None:
    """AU-RC-2 (D-1063): 400,001 code units with a lone surrogate decode to under 1 MiB of UTF-8, but their ``$utf16``
    base64 (about 2.67 digits per unit) exceeds 1 MiB, which the writer measures (AER-V01). UC-38 measured only the
    decoded text, kept the wrapper and the writer refused the run (``aer.string.inline_limit``); the value now becomes
    the digest of its decoded text."""
    text = "a" * 400_000 + "\ud800"
    m = support.map_steps([support.call("a", {}), support.result("a", state={"big": text})])
    (msg,) = [r for r in m.outcome.records if r.get("k") == "message" and r.get("role") == "tool"]
    raw = text.encode("utf-8", "surrogatepass")
    assert msg["parts"][0]["value"]["big"] == {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert msg["evf"]["/parts/0/value/big"] == "D" and f"{RULE}#/parts/0/value/big" in msg["rule"]
    assert issue_ids(m) == [msg["id"]] and not m.outcome.degenerate


def test_a_short_utf16_value_keeps_its_lossless_form() -> None:
    m = support.map_steps([support.call("a", {}), support.result("a", state={"big": "a" * 1000 + "\ud800"})])
    (msg,) = [r for r in m.outcome.records if r.get("k") == "message" and r.get("role") == "tool"]
    assert set(msg["parts"][0]["value"]["big"]) == {"$utf16"} and issue_ids(m) == []
