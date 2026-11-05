"""The transcript/v1 view of a not-inlined adprov turn (D-1063, regen-batch row 180 "left for the views owner"; review
UC-41; the D-934 pattern). A string over 1 MiB is not inlined in the AER (``adprov.content_not_inlined@1``): a tool
result's text becomes its part's ``value``, a text, reasoning or refusal part an ``other`` part of its source type, a Json
position holds ``{"not_inlined": {sha256, bytes}}``. Before, the view refused the tool turn (no text to digest) and
rendered the other turns ``null`` or the AER's digest object, which a reader cannot tell from source data. Now every such
member renders the documented marker ``{"agentprov:not_inlined": {"sha256", "bytes"}}`` (C.15.3): never a made-up text,
never a silent null; the view is lossy exactly there. Synthetic transcripts only."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from agentprov.prov.specs import load_compat_spec
from agentprov.views.transcript_v1 import NOT_INLINED_KEY, ViewError, render, serialise

MIB = 1 << 20
BIG = "x" * MIB + "é"  # one code point over the limit in UTF-8 (1 MiB + 2 bytes)
SHA = hashlib.sha256(BIG.encode("utf-8")).hexdigest()
MARKER = {"agentprov:not_inlined": {"sha256": SHA, "bytes": MIB + 2}}


def _view(v1: Any, doc: dict[str, Any]) -> dict[str, Any]:
    m = v1.map(v1.dump(doc))
    assert not m.outcome.degenerate, m.outcome.error_code
    assert "adprov.content_not_inlined" in m.issue_codes()
    return render(m.records[:-1])


def _tool_doc(v1: Any, content: str) -> dict[str, Any]:
    doc = v1.released()
    call = doc["turns"][2]["tool_calls"][0]
    doc["turns"][3] = v1.tool_turn(call["id"], call["function"], call["args"], content,
                                   timing=(doc["turns"][3]["started_at"], doc["turns"][3]["ended_at"]))
    return doc


def test_the_marker_key_is_the_documented_one():
    assert NOT_INLINED_KEY == "agentprov:not_inlined"


def test_a_tool_result_over_1_mib_renders_the_marker_and_its_true_digest(v1: Any):
    doc = _tool_doc(v1, BIG)
    out = _view(v1, doc)
    turn = out["turns"][3]
    assert turn["content"] == MARKER
    assert turn["content_sha256"] == doc["turns"][3]["content_sha256"] == "sha256:" + SHA
    expected = dict(doc["turns"][3], content=MARKER)
    assert serialise(turn) == serialise(expected)  # every other member and the member order are the source's
    # the rest of the document is byte-identical to the source
    assert serialise(dict(out, turns=out["turns"][:3] + out["turns"][4:])) == serialise(
        dict(doc, turns=doc["turns"][:3] + doc["turns"][4:]))


def test_a_recorded_content_hash_still_wins(v1: Any):
    doc = _tool_doc(v1, BIG)
    doc["turns"][3]["content_sha256"] = "sha256:" + "0" * 64  # the writer's hash disagrees: the importer keeps it
    out = _view(v1, doc)
    assert out["turns"][3]["content"] == MARKER and out["turns"][3]["content_sha256"] == "sha256:" + "0" * 64


@pytest.mark.parametrize(("turn", "member"), [(0, "content"), (1, "content"), (4, "text")])
def test_a_system_user_or_assistant_text_over_1_mib_renders_the_marker(v1: Any, turn: int, member: str):
    doc = v1.released()
    doc["turns"][turn][member] = BIG
    out = _view(v1, doc)
    assert out["turns"][turn][member] == MARKER
    assert serialise(out) == serialise(dict(doc, turns=[*doc["turns"][:turn], dict(doc["turns"][turn], **{member: MARKER}),
                                                        *doc["turns"][turn + 1:]]))


@pytest.mark.parametrize("member", ["reasoning", "refusal"])
def test_a_reasoning_or_refusal_over_1_mib_renders_the_marker(v1: Any, member: str):
    doc = v1.released()
    doc["turns"][4][member] = BIG
    out = _view(v1, doc)
    assert out["turns"][4] == dict(doc["turns"][4], **{member: MARKER})
    assert list(out["turns"][4]) == list(doc["turns"][4])


def test_tool_arguments_and_a_payload_over_1_mib_render_the_marker(v1: Any):
    doc = v1.released(injections={"vector_a": BIG})
    doc["turns"][2]["tool_calls"][0]["args"] = {"z": BIG, "a": 2.0}
    doc["turns"][3]["args"] = {"z": BIG, "a": 2.0}
    out = _view(v1, doc)
    assert out["meta"]["injections"] == {"vector_a": MARKER}
    assert out["turns"][2]["tool_calls"][0]["args"] == {"z": MARKER, "a": 2.0}
    assert out["turns"][3]["args"] == {"z": MARKER, "a": 2.0}
    assert '"a": 2.0' in serialise(out["turns"][3]).decode()  # lexical hints still apply beside the marker


def test_the_view_of_a_not_inlined_execution_is_deterministic(v1: Any):
    doc = _tool_doc(v1, BIG)
    doc["turns"][4]["text"] = BIG
    m = v1.map(v1.dump(doc))
    first = serialise(render(m.records[:-1]))
    assert first == serialise(render(v1.map(v1.dump(doc)).records[:-1]))
    assert first.count(b'"agentprov:not_inlined"') == 2 and BIG.encode() not in first


@pytest.mark.parametrize("size", [MIB - 1, MIB])
def test_a_string_up_to_1_mib_is_rendered_as_before(v1: Any, size: int):
    doc = _tool_doc(v1, "y" * size)
    raw = v1.dump(doc)
    assert serialise(render(v1.map(raw).records[:-1])) == raw  # the A2 byte gate


def test_source_data_holding_the_marker_member_is_refused(v1: Any):
    doc = v1.released()
    doc["turns"][2]["tool_calls"][0]["args"] = {"z": {"agentprov:not_inlined": {"sha256": SHA, "bytes": 1}}}
    doc["turns"][3]["args"] = doc["turns"][2]["tool_calls"][0]["args"]
    m = v1.map(v1.dump(doc))
    with pytest.raises(ViewError, match="reserved"):
        render(m.records[:-1])


def test_a_digest_object_in_source_data_is_not_a_marker(v1: Any):
    """Only a pointer the record cites under a ``content_not_inlined`` rule is a marker: a source object of the AER's
    digest shape renders as itself (byte gate)."""
    doc = v1.released()
    fake = {"not_inlined": {"sha256": SHA, "bytes": MIB + 2}}
    doc["turns"][2]["tool_calls"][0]["args"] = {"z": fake}
    doc["turns"][3]["args"] = {"z": fake}
    raw = v1.dump(doc)
    assert serialise(render(v1.map(raw).records[:-1])) == raw


def test_the_compat_graph_never_hashes_a_marker(v1: Any):
    """The frozen oracle reads a tool turn's content as text: on a marker it raises (derive records the compat graph
    failed), so no graph states a hash of anything but content. An assistant text it does not read."""
    spec = load_compat_spec()
    with pytest.raises(AttributeError):
        spec.build(_view(v1, _tool_doc(v1, BIG)))
    user = v1.released()
    user["turns"][1]["content"] = BIG
    with pytest.raises(AttributeError):
        spec.build(_view(v1, user))
    with pytest.raises(TypeError):
        spec.build(_view(v1, v1.released(injections={"vector_a": BIG})))
    doc = v1.released()
    doc["turns"][4]["text"] = BIG
    plain = spec.serialise(spec.build(render(v1.map(v1.dump(v1.released())).records[:-1])))
    assert spec.serialise(spec.build(_view(v1, doc))) == plain
