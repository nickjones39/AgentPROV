"""Regeneration-batch item 28 (i) (routed from phase 10n, R-10n-2): an Inspect string whose UTF-8 encoding exceeds 1 MiB
is not inlined (C.2.1(6)): its SHA-256, size and media type are recorded instead, under ``inspect.content_not_inlined@1``
(the OpenHands precedent). Synthetic samples only.
"""

from __future__ import annotations

import hashlib
from typing import Any

import inspect_support as support
from test_item16 import TOOLS, _frame, cites, codes, run

RULE = "inspect.content_not_inlined@1"


def noise(n: int, seed: str) -> str:
    """``n`` deterministic hex characters (incompressible enough for the archive ratio limit, unlike a repeated one)."""
    out, block, size = [], seed.encode(), 0
    while size < n:  # a running total: re-summing the list each round was quadratic (5-16 s at import, per process)
        block = hashlib.sha256(block).digest()
        out.append(block.hex())
        size += len(out[-1])
    return "".join(out)[:n]


BIG_PNG = "data:image/png;base64," + noise(1024 * 1024 + 8, "png")
BIG_TEXT = noise(1024 * 1024 + 1, "text")
EXACT_MIB = noise(1024 * 1024, "edge")


def digest(value: str) -> dict[str, Any]:
    raw = value.encode("utf-8")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def sample(user_content: Any, tool_output: str = "synthetic tool output", transmitted: str | None = None,
           state: str | None = None) -> dict[str, Any]:
    s = support.Sample()
    gen, system, _ = _frame(s)
    user = s.msg("user", user_content, source="input")
    call = {"id": "call_big_1", "function": "get_x", "arguments": {"q": "a"}, "type": "function"}
    a1 = s.msg("assistant", "Calling.", source="generate", model="synthetic", tool_calls=[call])
    r1 = s.msg("tool", tool_output, tool_call_id=call["id"], function="get_x")
    final = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    extra = {"call": {"request": {"contents": [{"inlineData": {"data": transmitted}}]}}} if transmitted else {}
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], a1, tools=TOOLS, **extra)
    s.tool(gen, call, r1)
    s.model(gen, "ollama/synthetic-agent:1b", [system, user, a1, r1], final, tools=TOOLS)
    if state is not None:
        s.event("state", gen, changes=[{"op": "add", "path": "/metadata/pr_diff", "value": state}])
    s.end(gen)
    s.messages.extend([system, user, a1, r1, final])
    return s.build()


def issue_ids(unit: support.Unit) -> list[str]:
    return [i for issue in unit.info.issues if issue["code"] == "inspect.content_not_inlined" for i in issue["ids"]]


def test_a_data_uri_over_1_mib_is_an_other_part_with_its_digest(tmp_path):
    u = run(tmp_path, sample([{"type": "text", "text": "Look."}, {"type": "image", "image": BIG_PNG, "detail": "auto"}]))
    user = next(m for m in u.of_kind("message") if m["role"] == "user")
    assert user["parts"][1] == {"t": "other", "type": "image",
                                "value": {"not_inlined": {**digest(BIG_PNG), "media": "image/png"}}}
    assert user["evf"]["/parts/1/value"] == "D" and cites(user, RULE)
    assert user["ext"]["inspect"]["part_extra"]["1"] == {"detail": "auto"}
    assert issue_ids(u) == [user["id"]]


def test_a_tool_output_over_1_mib_is_its_results_value_digest(tmp_path):
    u = run(tmp_path, sample("Synthetic task prompt.", tool_output=BIG_TEXT))
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert result["parts"][0]["value"] == {"not_inlined": digest(BIG_TEXT)} and "text" not in result["parts"][0]
    assert result["evf"]["/parts/0/value"] == "D" and cites(result, RULE)
    assert issue_ids(u) == [result["id"]]


def test_a_text_or_reasoning_item_over_1_mib_is_an_other_part_of_its_type(tmp_path):
    u = run(tmp_path, sample([{"type": "reasoning", "reasoning": BIG_TEXT, "signature": "sig"},
                              {"type": "text", "text": BIG_TEXT}]))
    user = next(m for m in u.of_kind("message") if m["role"] == "user")
    assert [(p["t"], p["type"]) for p in user["parts"]] == [("other", "reasoning"), ("other", "text")]
    assert all(p["value"] == {"not_inlined": digest(BIG_TEXT)} for p in user["parts"])
    assert user["ext"]["inspect"]["part_extra"] == {"0": {"signature": "sig"}}


def test_a_transmitted_string_over_1_mib_is_replaced_in_place(tmp_path):
    u = run(tmp_path, sample("Synthetic task prompt.", transmitted=BIG_TEXT))
    mc = next(r for r in u.of_kind("model_call") if "transmitted" in r.get("params", {}))
    pointer = "/params/transmitted/contents/0/inlineData/data"
    assert mc["params"]["transmitted"]["contents"][0]["inlineData"]["data"] == {"not_inlined": digest(BIG_TEXT)}
    assert mc["evf"][pointer] == "D" and cites(mc, RULE)
    assert issue_ids(u) == [mc["id"]]


def test_a_sample_metadata_string_over_1_mib_is_not_inlined_in_the_header(tmp_path):
    # wave 2: ControlArena's pr_diff metadata (over 1 MiB) left the header unsealable under aer/0.2 (AER-V01)
    s = sample("Synthetic task prompt.")
    s["metadata"] = {**s["metadata"], "pr_diff": BIG_TEXT}
    u = run(tmp_path, s)
    header = u.header
    assert header["ext"]["inspect"]["sample_metadata"]["pr_diff"] == {"not_inlined": digest(BIG_TEXT)}
    assert header["ext"]["inspect"]["sample_metadata"]["category"] == "Synthetic"
    assert header["evf"]["/ext/inspect/sample_metadata/pr_diff"] == "D" and cites(header, RULE)
    assert issue_ids(u) == ["exec"]


def test_a_state_patch_value_over_1_mib_is_not_inlined(tmp_path):
    u = run(tmp_path, sample("Synthetic task prompt.", state=BIG_TEXT))
    st = next(r for r in u.of_kind("state_change") if r["patch"][0]["path"] == "/metadata/pr_diff")
    assert st["patch"][0]["value"] == {"not_inlined": digest(BIG_TEXT)}
    assert st["evf"]["/patch/0/value"] == "D" and cites(st, RULE)
    assert issue_ids(u) == [st["id"]]


def test_strings_up_to_1_mib_stay_inline(tmp_path):
    u = run(tmp_path, sample("Synthetic task prompt.", tool_output=EXACT_MIB))
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert result["parts"][0]["text"] == EXACT_MIB
    assert "inspect.content_not_inlined" not in codes(u)
