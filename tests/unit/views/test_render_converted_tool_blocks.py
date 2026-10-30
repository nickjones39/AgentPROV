"""Regen item 72 (CA-14): a tool result kept as a list renders its joined text blocks, as the baseline converter does.

The TraceLogger mapper keeps a tool message's list content verbatim as ``tool_result.value`` (every list in v0.k11,
a multi-block list in v1.k14; ``agentdojo.multi_block_tool_content``). ``render_converted`` read only ``text`` parts,
so the view gave ``content ""`` with ``sha256("")``. The baseline converter (``transcript.message_to_turn``, role
``tool``) gives ``_split_blocks(content)[0]``: the text blocks joined, thinking blocks left out. Synthetic logs only.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov.views.transcript_v1 import ViewError, render_converted

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "agentdojo"))
from agentdojo_support import map_log, new_log  # noqa: E402


def _tool_turn(content: Any) -> dict[str, Any]:
    log = new_log()
    log["messages"][3]["content"] = content
    mapped = map_log(log)
    assert mapped.validate().ok
    assert "agentdojo.multi_block_tool_content" in mapped.codes
    part = mapped.get("m3")["parts"][0]
    assert part["t"] == "tool_result" and "value" in part and "text" not in part
    turn: dict[str, Any] = render_converted(mapped.records)["turns"][3]
    assert turn["role"] == "tool"
    return turn


@pytest.mark.parametrize(("content", "expected"), [
    ([{"type": "text", "content": "a"}, {"type": "text", "content": "b"}], "ab"),
    ([{"type": "text", "content": "done"}], "done"),
    ([{"type": "thinking", "content": "t"}, {"type": "text", "content": "x"}, {"type": "text", "content": None}], "x"),
], ids=["two-text", "one-text", "thinking-and-null"])
def test_a_list_tool_result_renders_the_joined_text_blocks(content: Any, expected: str) -> None:
    turn = _tool_turn(content)
    assert turn["content"] == expected
    assert turn["content_sha256"] == "sha256:" + hashlib.sha256(expected.encode("utf-8")).hexdigest()


def test_a_list_tool_result_the_converter_rule_cannot_join_raises_view_error() -> None:
    with pytest.raises(ViewError, match="m3"):
        _tool_turn([{"type": "text", "content": 5}])
