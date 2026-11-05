"""AU-RB-1 (audit 2026-11-05; 0.2.0 change batch D-1063, regeneration-batch item 180): the item-28 not-inlined pass
(``inspect.content_not_inlined@1``) covered only some Json positions. A tool event's arguments, a sandbox output, the
sample error and the other ``ext`` copies were encoded as is, so a string over 1 MiB there made the aer/0.2 writer refuse
the sample (``aer.string.inline_limit``) and it sealed ``adapter_defect``. Now every Json position of a finished record
is slimmed, and the typed positions the audit lists get a not-inlined form beside the part: a reasoning item's signature
and a tool result's error go to ``ext.inspect.part_extra`` (a judgement's value is a Json position already). Each
pointer is D under the rule; the one info issue lists the records. Synthetic samples only."""

from __future__ import annotations

from typing import Any

import inspect_support as support
from test_item16 import TOOLS, _frame, cites, codes, run
from test_item28 import BIG_TEXT, digest, issue_ids, noise

RULE = "inspect.content_not_inlined@1"
DIGEST = {"not_inlined": digest(BIG_TEXT)}


def _sample(*, args: dict[str, Any] | None = None, sandbox: str | None = None, tool_error: str | None = None,
            assistant: Any = "Calling.", **extra: Any) -> dict[str, Any]:
    s = support.Sample()
    gen, system, _ = _frame(s)
    user = s.msg("user", "Synthetic task prompt.", source="input")
    call = {"id": "call_big_1", "function": "get_x", "arguments": args or {"q": "a"}, "type": "function"}
    a1 = s.msg("assistant", assistant, source="generate", model="synthetic", tool_calls=[call])
    r1 = s.msg("tool", "ok", tool_call_id=call["id"], function="get_x")
    fields: dict[str, Any] = {}
    if tool_error is not None:
        r1["error"] = fields["error"] = {"type": "unknown", "message": tool_error}
    final = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], a1, tools=TOOLS)
    s.tool(gen, call, r1, **fields)
    if sandbox is not None:
        s.event("sandbox", gen, action="exec", cmd=["cat", "x"], result=0, output=sandbox, completed=s.tick(0.1))
    s.model(gen, "ollama/synthetic-agent:1b", [system, user, a1, r1], final, tools=TOOLS)
    s.end(gen)
    s.messages.extend([system, user, a1, r1, final])
    return s.build(**extra)


def test_a_tool_events_arguments_over_1_mib_are_not_inlined(tmp_path):
    u = run(tmp_path, _sample(args={"path": "/tmp/x", "content": BIG_TEXT}))
    te = u.of_kind("tool_execution")[0]
    assert te["args"] == {"path": "/tmp/x", "content": DIGEST}
    assert te["evf"]["/args/content"] == "D" and cites(te, RULE)
    call_msg = next(m for m in u.of_kind("message") if m["role"] == "assistant" and len(m["parts"]) > 1)
    assert te["id"] in issue_ids(u) and call_msg["id"] in issue_ids(u)


def test_a_sandbox_output_over_1_mib_is_not_inlined(tmp_path):
    u = run(tmp_path, _sample(sandbox=BIG_TEXT))
    af = next(r for r in u.of_kind("artefact") if r["type"] == "inspect:sandbox_output")
    assert af["content"] == DIGEST and af["evf"]["/content"] == "D" and cites(af, RULE)
    assert issue_ids(u) == [af["id"]]


def test_a_sample_error_over_1_mib_is_not_inlined(tmp_path):
    u = run(tmp_path, _sample(error={"message": "boom", "traceback": BIG_TEXT, "traceback_ansi": ""}))
    run_scope = u.by_id()["run"]
    assert run_scope["status"] == "error"
    assert run_scope["ext"]["inspect"]["error"] == {"message": "boom", "traceback": DIGEST, "traceback_ansi": ""}
    assert run_scope["evf"]["/ext/inspect/error/traceback"] == "D" and cites(run_scope, RULE)
    assert issue_ids(u) == ["run"]


def test_a_reasoning_signature_over_1_mib_goes_beside_the_part(tmp_path):
    u = run(tmp_path, _sample(assistant=[{"type": "reasoning", "reasoning": "Short.", "signature": BIG_TEXT},
                                         {"type": "text", "text": "Calling."}]))
    msg = next(m for m in u.of_kind("message") if m["role"] == "assistant" and m["parts"][0]["t"] == "reasoning")
    assert msg["parts"][0] == {"t": "reasoning", "text": "Short."}
    assert msg["ext"]["inspect"]["part_extra"]["0"] == {"signature": DIGEST}
    assert msg["evf"]["/ext/inspect/part_extra/0/signature"] == "D" and cites(msg, RULE)


def test_a_tool_results_error_over_1_mib_goes_beside_the_part(tmp_path):
    u = run(tmp_path, _sample(tool_error=BIG_TEXT))
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert "error" not in result["parts"][0]
    assert result["ext"]["inspect"]["part_extra"]["0"] == {"error": DIGEST}
    assert result["ext"]["inspect"]["error"]["message"] == DIGEST
    assert result["evf"]["/ext/inspect/part_extra/0/error"] == "D" and cites(result, RULE)
    te = u.of_kind("tool_execution")[0]
    assert te["status"] == "error" and te["ext"]["inspect"]["error"]["message"] == DIGEST


def test_a_judgement_value_over_1_mib_is_not_inlined(tmp_path):
    u = run(tmp_path, _sample(scores={"grader": {"value": BIG_TEXT}}))
    j = u.of_kind("judgement")[0]
    assert j["value"] == DIGEST and j["evf"]["/value"] == "D" and cites(j, RULE)
    assert issue_ids(u) == [j["id"]]


def test_short_strings_in_these_positions_stay_inline(tmp_path):
    u = run(tmp_path, _sample(args={"content": "short"}, sandbox="short", tool_error="short",
                              error={"message": "boom", "traceback": "short", "traceback_ansi": ""}))
    assert "inspect.content_not_inlined" not in codes(u)
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert result["parts"][0]["error"] == "short"


#: A string with a lone surrogate (C.11.3) whose UTF-8 is under 1 MiB (400,003 bytes) but whose ``$utf16`` base64, which
#: the writer measures (AER-V01), is over it (1,066,672 digits).
SPLIT = noise(400_000, "split") + "\ud800"  # hex noise: incompressible enough for the archive ratio limit


def test_a_utf16_value_whose_base64_exceeds_1_mib_is_not_inlined(tmp_path):
    """Regen-batch row 186: a ``$utf16`` value is replaced whole when its base64 exceeds 1 MiB, by the digest of its
    decoded text (the AU-RC-2 rule; AU-RB-1's pass applies it), in a sandbox output and a tool event's arguments."""
    import hashlib

    u = run(tmp_path, _sample(args={"content": SPLIT}, sandbox=SPLIT))
    raw = SPLIT.encode("utf-8", "surrogatepass")
    digest = {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    te = u.of_kind("tool_execution")[0]
    assert te["args"] == {"content": digest} and te["evf"]["/args/content"] == "D" and cites(te, RULE)
    af = next(r for r in u.of_kind("artefact") if r["type"] == "inspect:sandbox_output")
    assert af["content"] == digest and af["id"] in issue_ids(u) and te["id"] in issue_ids(u)
