"""The converted transcript/v1 view (``render_converted``) of a TraceLogger message whose content was not inlined (D-1063;
review UC-41; regen-batch rows 179 and 180). Before, a tool output over 1 MiB rendered ``""`` with the digest of ``""``
and an assistant text over 1 MiB rendered ``""``: a made-up text. Now each renders the documented marker
``{"agentprov:not_inlined": {"sha256", "bytes"}}`` (C.15.3), a tool turn's ``content_sha256`` is the content's true
digest, and a marker that the converter would have to join with other text is refused. All content is synthetic."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from agentdojo_support import map_log, new_log

from agentprov.views.transcript_v1 import ViewError, render_converted, serialise

MIB = 1 << 20
BIG = "x" * (MIB + 10)
SHA = hashlib.sha256(BIG.encode()).hexdigest()
MARKER = {"agentprov:not_inlined": {"sha256": SHA, "bytes": MIB + 10}}


def _view(doc: dict[str, Any]) -> dict[str, Any]:
    m = map_log(doc)
    assert not m.outcome.degenerate and "adapter_defect" not in m.codes, m.codes
    assert "agentdojo.content_not_inlined" in m.codes
    return render_converted(m.records[:-1])


def test_a_tool_output_over_1_mib_renders_the_marker_and_its_true_digest():
    doc = new_log()
    doc["messages"][3]["content"] = BIG
    out = _view(doc)
    plain = render_converted(map_log(new_log()).records[:-1])
    tool = out["turns"][3]
    assert tool["content"] == MARKER and tool["content_sha256"] == "sha256:" + SHA
    assert dict(tool, content="done", content_sha256=plain["turns"][3]["content_sha256"]) == plain["turns"][3]
    assert serialise(dict(out, turns=out["turns"][:3])) == serialise(dict(plain, turns=plain["turns"][:3]))


def test_an_assistant_text_over_1_mib_renders_the_marker():
    doc = new_log()
    doc["messages"][4]["content"] = BIG
    out = _view(doc)
    assert out["turns"][4] == {"role": "assistant", "text": MARKER}
    assert serialise(out) == serialise(_view(doc))  # deterministic


def test_a_marker_the_converter_would_join_with_other_text_is_refused():
    doc = new_log()
    doc["messages"][4]["content"] = [{"type": "text", "content": BIG}, {"type": "text", "content": " and more"}]
    m = map_log(doc)
    assert not m.outcome.degenerate, m.codes
    with pytest.raises(ViewError, match="joined with other text"):
        render_converted(m.records[:-1])
