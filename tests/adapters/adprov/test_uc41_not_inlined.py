"""Review UC-41 for adprov (2026-11-01; 0.2.0 change batch D-1063, regeneration-batch item 180; the D-934 pattern):
a string whose UTF-8 encoding exceeds 1 MiB is not inlined. Before, the aer/0.2 writer refused it
(``aer.string.inline_limit``, AER-V01) and the whole transcript became ``adapter_defect``. A tool result's text becomes the
part's Json value, a text, reasoning or refusal part becomes an ``other`` part of its source type, any other Json
position holds ``{"not_inlined": {sha256, bytes}}``; each pointer is DERIVED under ``adprov.content_not_inlined@1`` (cited
as given: a transformation by AgentPROV), and one info issue lists the records. Synthetic transcripts only."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

MIB = 1 << 20
BIG = "x" * MIB + "é"  # one code point over the limit in UTF-8 (1 MiB + 2 bytes)
RULE = "adprov.content_not_inlined@1"


def _digest(text: str) -> dict[str, Any]:
    raw = text.encode("utf-8")
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def _sealed(v1: Any, doc: dict[str, Any]) -> Any:
    m = v1.map(v1.dump(doc))
    assert not m.outcome.degenerate, m.outcome.error_code
    assert "adapter_defect" not in m.issue_codes()
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})
    return m


def _issue(m: Any) -> dict[str, Any]:
    return next(i for i in m.info.issues if i["code"] == "adprov.content_not_inlined")


def _tool_doc(v1: Any, content: str) -> dict[str, Any]:
    doc = v1.released()
    call = doc["turns"][2]["tool_calls"][0]
    doc["turns"][3] = v1.tool_turn(call["id"], call["function"], call["args"], content,
                                   timing=(doc["turns"][3]["started_at"], doc["turns"][3]["ended_at"]))
    return doc


def test_a_tool_result_over_1_mib_is_its_digest_value(v1: Any):
    m = _sealed(v1, _tool_doc(v1, BIG))
    msg = m.by_id()["m3"]
    assert msg["parts"][0]["value"] == _digest(BIG) and "text" not in msg["parts"][0]
    assert msg["evf"]["/parts/0/value"] == "D" and f"{RULE}#/parts/0/value" in msg["rule"]
    issue = _issue(m)
    assert issue["ids"] == ["m3"] and issue["rule"] == RULE


def test_an_assistant_text_over_1_mib_is_an_other_part(v1: Any):
    doc = v1.released()
    doc["turns"][4]["text"] = BIG
    m = _sealed(v1, doc)
    part = m.by_id()["m4"]["parts"][0]
    assert part == {"t": "other", "type": "text", "value": _digest(BIG)}
    assert _issue(m)["ids"] == ["m4"]


def test_tool_arguments_and_a_payload_over_1_mib_are_digests(v1: Any):
    doc = v1.released(injections={"vector_a": BIG})
    doc["turns"][2]["tool_calls"][0]["args"] = {"z": BIG}
    doc["turns"][3]["args"] = {"z": BIG}
    m = _sealed(v1, doc)
    by_id = m.by_id()
    assert by_id["fx0"]["content"] == _digest(BIG)
    assert by_id["m2"]["parts"][1]["args"] == {"z": _digest(BIG)}
    assert by_id["te0"]["args"] == {"z": _digest(BIG)}
    assert by_id["te0"]["evf"]["/args/z"] == "D" and f"{RULE}#/args/z" in by_id["te0"]["rule"]
    assert _issue(m)["ids"] == ["fx0", "m2", "te0"]


@pytest.mark.parametrize("size", [MIB - 1, MIB])
def test_a_string_up_to_1_mib_is_unchanged(v1: Any, size: int):
    m = _sealed(v1, _tool_doc(v1, "y" * size))
    assert m.by_id()["m3"]["parts"][0]["text"] == "y" * size
    assert "adprov.content_not_inlined" not in m.issue_codes()


#: A string with a lone surrogate (C.11.3) whose UTF-8 is under 1 MiB (400,003 bytes) but whose ``$utf16`` base64, which
#: the writer measures (AER-V01), is over it (1,066,672 digits).
SPLIT = "a" * 400_000 + "\ud800"


def test_a_utf16_value_whose_base64_exceeds_1_mib_is_not_inlined(v1: Any):
    """Regen-batch row 186: a ``$utf16`` value is replaced whole when its base64 exceeds 1 MiB, by the digest of its
    decoded text (the AU-RC-2 rule; row 180's pass applies it)."""
    doc = v1.released()
    doc["turns"][2]["tool_calls"][0]["args"] = {"z": SPLIT}
    doc["turns"][3]["args"] = {"z": SPLIT}
    m = _sealed(v1, doc)
    raw = SPLIT.encode("utf-8", "surrogatepass")
    digest = {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    assert m.by_id()["te0"]["args"] == {"z": digest} and m.by_id()["m2"]["parts"][1]["args"] == {"z": digest}
    assert m.by_id()["te0"]["evf"]["/args/z"] == "D" and _issue(m)["ids"] == ["m2", "te0"]
