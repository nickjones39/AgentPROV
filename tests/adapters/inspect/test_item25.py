"""Regeneration-batch item 25 (routed from phase 10n, ATIA): tool events of inspect_ai 0.3.112 and earlier carry no
``message_id`` (0.3.113 adds the field), and audio and video content items are ``uri`` parts like images; both read
from the producer code at 0.3.112 and 0.3.113 (docs/reports/analysis/regen-batch.md item 25). Synthetic samples only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import inspect_support as support
import pytest
from agentprov.adapters.inspect.mapper import without_message_id
from agentprov.adapters.profiles import SourceProfile, parse_profile
from agentprov.aer.reader import load_aer
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator
from agentprov.prov.engine import derive
from agentprov.validate import validate_prov

REPO = Path(__file__).resolve().parents[3]
PROFILE = REPO / "src" / "agentprov" / "adapters" / "inspect" / "profiles" / "survey-agentharm.profile.toml"
NO_ID = "inspect.tool_event_no_message_id@1"
TOOLS = [{"name": "get_x", "description": "Synthetic tool.", "parameters": {"type": "object", "properties": {}}}]


def band_profile(producer: str) -> SourceProfile:
    """The AgentHarm profile with ``producer`` as its band (a dev-only variant for tests; ATIA's profile is phase 10n's)."""
    text = PROFILE.read_text(encoding="utf-8")
    old = 'producer_band = { inspect_ai = ["0.3.247.dev69+g53c1fa98b"] }'
    assert old in text
    return parse_profile(text.replace(old, f'producer_band = {{ inspect_ai = ["{producer}"] }}').encode("utf-8"),
                         source="test-variant")


def run(tmp_path: Path, sample: dict[str, Any], producer: str) -> support.Unit:
    """Import one synthetic sample under a header naming ``producer``; it validates, derives and passes tier 4."""
    used = band_profile(producer)
    data = support.build_eval(support.synthetic_header(producer), {"s1_epoch_1.json": sample})
    imported = support.import_log(data, tmp_path / "raw", profile=used)
    assert imported.register == [] and len(imported.units) == 1
    unit = imported.units[0]
    assert not unit.outcome.degenerate, unit.outcome.error_code
    validator = AerValidator(store=imported.store, catalogues=RuleRegistry.default(), mode="release",
                             profile_digests={(used.id, used.version): used.sha256})
    for line in unit.data.splitlines(keepends=True):
        validator.feed(line)
    report = validator.finish()
    assert report.ok, sorted({(f.code, f.pointer) for f in report.errors})
    path = tmp_path / "x.aer.jsonl"
    path.write_bytes(unit.data)
    doc = load_aer(path)
    result = validate_prov(derive(doc).prov_json, doc)
    assert result.ok, [(o.id, sorted(o.codes())) for o in result.outcomes if o.status == "fail"]
    return unit


def cites(record: dict[str, Any], rule: str) -> bool:
    return any(r.split("#", 1)[0] == rule for r in record.get("rule", []))


def codes(unit: support.Unit) -> set[str]:
    return {str(i["code"]) for i in unit.info.issues}


def no_message_id_sample(content: Any = "Synthetic task prompt.") -> dict[str, Any]:
    """One call and its result, the tool event written without ``message_id`` as inspect_ai 0.3.112 writes it."""
    s = support.Sample()
    init = s.span("SpanInit00000000000000", "init", "init")
    s.event("sample_init", init, sample={"input": "Synthetic task prompt.", "target": "", "id": s.sid, "metadata": {}},
            state={"messages": []})
    s.end(init)
    gen = s.span("SpanGenerate0000000000", "solver", "generate")
    system, user = s.msg("system", "You are a synthetic agent."), s.msg("user", content, source="input")
    call = {"id": "call_old_1", "function": "get_x", "arguments": {"q": "a"}, "type": "function"}
    a1 = s.msg("assistant", "Calling.", source="generate", model="synthetic", tool_calls=[call])
    r1 = s.msg("tool", "synthetic tool output", tool_call_id=call["id"], function="get_x")
    final = s.msg("assistant", "Synthetic final answer.", source="generate", model="synthetic")
    s.model(gen, "ollama/synthetic-agent:1b", [system, user], a1, tools=TOOLS)
    del s.tool(gen, call, r1)["message_id"]
    s.model(gen, "ollama/synthetic-agent:1b", [system, user, a1, r1], final, tools=TOOLS)
    s.end(gen)
    s.messages.extend([system, user, a1, r1, final])
    return s.build()


@pytest.mark.parametrize(("producer", "expected"), [
    ("0.3.112", True), ("0.3.111", True), ("0.3.112.dev4+g1234abc", True), ("0.2.60", True),
    ("0.3.113", False), ("0.3.113.dev2+gabc", False), ("0.3.130", False), ("0.3.247.dev69+g53c1fa98b", False),
    ("0.3.112.post1", False), ("v0.3.112", False), ("", False), (None, False), (112, False),
])
def test_the_producer_version_gate(producer, expected):
    assert without_message_id(producer) is expected


def test_a_tool_event_without_message_id_links_by_call_id_before_0_3_113(tmp_path):
    u = run(tmp_path, no_message_id_sample(), "0.3.112")
    te = u.of_kind("tool_execution")[0]
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert result["parts"][0]["responds_to"] == te["call"] and result["generated_by"] == te["id"]
    assert cites(result, NO_ID)
    assert not codes(u) & {"missing_tool_result", "dangling_source_ref", "orphan_tool_result"}
    assert u.info.accounting.status == "consistent"


def test_from_0_3_113_a_missing_message_id_is_not_linked(tmp_path):
    """From 0.3.113 the log is written with ``exclude_none``: an absent ``message_id`` is a ``None``, never this rule."""
    u = run(tmp_path, no_message_id_sample(), "0.3.113")
    result = next(m for m in u.of_kind("message") if m["role"] == "tool")
    assert "generated_by" not in result and not cites(result, NO_ID)
    assert "missing_tool_result" in codes(u)


def test_audio_and_video_items_are_uri_parts(tmp_path):
    content = [{"type": "text", "text": "Describe these."},
               {"type": "audio", "audio": "data:audio/mp3;base64,AAAA", "format": "mp3"},
               {"type": "video", "video": "https://example.invalid/clip.mp4", "format": "mp4"}]
    u = run(tmp_path, no_message_id_sample(content), "0.3.112")
    user = next(m for m in u.of_kind("message") if m["role"] == "user")
    assert [p["t"] for p in user["parts"]] == ["text", "uri", "uri"]
    assert user["parts"][1]["uri"] == "data:audio/mp3;base64,AAAA" and user["parts"][2]["uri"].endswith("clip.mp4")
    assert user["ext"]["inspect"]["part_extra"] == {"1": {"format": "mp3"}, "2": {"format": "mp4"}}
    assert "inspect.unknown_content_type" not in codes(u)
