"""The capture mapper reads content blocks with the TraceLogger mapper's rule (regeneration-batch item 47, the capture
half of core review D's CD-13; RD-1's ``content_block_parts``).

The C.13.8 session with its final assistant message's content replaced by blocks: a thinking block keeps its ``id`` as
the reasoning part's ``signature``, a text block with an extra key or non-string content is kept as an ``other`` part
with ``agentdojo.unknown_message_shape``, and a text block whose content is null is a null text part
listed in ``ext.agentdojo.null_text_blocks``. Nothing is truncated.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from capture_support import MappedSession, c13_8_session, map_built


def _with_final_content(content: list[dict[str, Any]]) -> MappedSession:
    s = c13_8_session()
    for event in s.events:
        if event["type"] == "pass.end":
            ref = event["data"]["messages"]["$blob"]
            native = json.loads(s.blobs[ref.removeprefix("sha256:")])
            native[4]["content"] = content
            event["data"]["messages"] = s.blob(native)
    return map_built(s)


def test_capture_content_blocks_follow_the_tracelogger_rule():
    m = _with_final_content([
        {"type": "thinking", "content": "hmm", "id": "SIG"},
        {"type": "text", "content": "Your balance is 1810.0.", "extra_key": "X"},
        {"type": "text", "content": None},
        {"type": "text", "content": 5},
    ])
    final = m.get("m4")  # the native message no longer matches the wire reply (capture_reply_mismatch); content is read anyway
    parts = final["parts"]
    assert parts[0] == {"t": "reasoning", "text": "hmm", "signature": "SIG"}
    assert [p["t"] for p in parts[1:]] == ["other", "text", "other"]
    assert parts[2] == {"t": "text", "text": None}
    assert final["ext"]["agentdojo"]["null_text_blocks"] == [2]
    unknown = [i for i in m.info.issues if i["code"] == "agentdojo.unknown_message_shape"]
    assert [i["ids"] for i in unknown] == [[final["id"]]]  # raised per block; identical issues collapse in the seal
    assert hashlib.sha256(m.data).hexdigest() == hashlib.sha256(_with_final_content([
        {"type": "thinking", "content": "hmm", "id": "SIG"},
        {"type": "text", "content": "Your balance is 1810.0.", "extra_key": "X"},
        {"type": "text", "content": None},
        {"type": "text", "content": 5},
    ]).data).hexdigest()  # deterministic
