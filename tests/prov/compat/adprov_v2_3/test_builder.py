"""Ported baseline builder, emitter, labelling and validator tests (K.3.1; J.3.3 "the ported tests run too").

Baseline ``tests/test_prov_builder.py`` @ 579a908 with the imports pointed at the compat port. In the compat profile these
pin the *legacy* behaviour of ``adprov-v2.3-compat``; in ``agentprov-prov/0.1`` the same cases assert the corrected
behaviour. Tests that need ``agentdojo`` or the in-loop observer (``TestProvObserver``,
``TestObserverTurnAwareTaint``, the placeholder-string, in-loop-naming and suite-tool-table tests) belong to the backend
project (R-01), and the flow-graph test belongs to ``analysis/`` (deferred); they are not ported. The marker tests are in
``test_marker_yaml_styles.py``.
"""
from __future__ import annotations

import json

from agentprov.prov.compat.adprov_v2_3.build_prov import build_prov
from agentprov.prov.compat.adprov_v2_3.labeling import Label, NodeRole, SINK_TOOLS, classify_activity
from agentprov.prov.compat.adprov_v2_3.prov_emit import ProvDocumentBuilder
from agentprov.prov.compat.adprov_v2_3.validate import validate_prov_document


# ---------------------------------------------------------------------------
# labeling
# ---------------------------------------------------------------------------

class TestLabeling:
    def test_sink_tools_classified_as_sink(self):
        for tool in SINK_TOOLS:
            assert classify_activity(tool) == NodeRole.SINK

    def test_read_tool_is_neutral(self):
        assert classify_activity("get_received_emails") == NodeRole.NEUTRAL
        assert classify_activity("search_files") == NodeRole.NEUTRAL

    def test_unknown_tool_is_neutral(self):
        assert classify_activity("totally_fake_tool") == NodeRole.NEUTRAL

    def test_label_values(self):
        assert Label.TRUSTED.value == "trusted"
        assert Label.UNTRUSTED.value == "untrusted"


# ---------------------------------------------------------------------------
# prov_emit
# ---------------------------------------------------------------------------

class TestProvDocumentBuilder:
    def _minimal_doc(self) -> tuple[ProvDocumentBuilder, dict]:
        b = ProvDocumentBuilder()
        ag = b.add_agent("ag_llm", "llm_agent", "trusted")
        act = b.add_activity("a_read", "get_received_emails", "neutral", "T", "T")
        ent = b.add_entity("e_read_out", "get_received_emails_output", "untrusted", "sha256:abc")
        b.add_was_generated_by(ent, act, "T")
        b.add_was_associated_with(act, ag)
        return b, b.build()

    def test_build_has_required_sections(self):
        _, doc = self._minimal_doc()
        assert "prefix" in doc
        assert "entity" in doc
        assert "activity" in doc
        assert "agent" in doc
        assert "wasGeneratedBy" in doc
        assert "wasAssociatedWith" in doc

    def test_prefix_contains_flint(self):
        _, doc = self._minimal_doc()
        assert "adprov" in doc["prefix"]

    def test_entity_integrity_set(self):
        _, doc = self._minimal_doc()
        ent = doc["entity"]["adprov:e_read_out"]
        assert ent["adprov:integrity"] == "untrusted"

    def test_used_relation_created(self):
        b = ProvDocumentBuilder()
        b.add_agent("ag_llm", "llm_agent", "trusted")
        act1 = b.add_activity("a_read", "get_received_emails", "neutral", "T", "T")
        ent1 = b.add_entity("e_out1", "read_output", "untrusted")
        b.add_was_generated_by(ent1, act1, "T")

        act2 = b.add_activity("a_send", "send_email", "sink", "T", "T")
        b.add_used(act2, ent1, "T")

        doc = b.build()
        used_vals = list(doc["used"].values())
        assert any(u["prov:activity"] == "adprov:a_send" and u["prov:entity"] == "adprov:e_out1"
                   for u in used_vals)

    def test_build_is_json_serialisable(self):
        _, doc = self._minimal_doc()
        serialised = json.dumps(doc)
        assert len(serialised) > 0

    def test_no_time_means_no_time_attribute(self):
        # None (or an empty string) omits the attribute rather than writing a
        # literal that is not a time; the node or relation itself is unaffected.
        for none in (None, ""):
            b = ProvDocumentBuilder()
            a1 = b.add_activity("a_1", "get_received_emails", "neutral", none, none)
            a2 = b.add_activity("a_2", "send_email", "sink", none, "T")
            e1 = b.add_entity("e_1", "out", "untrusted")
            b.add_was_generated_by(e1, a1, none)
            b.add_used(a2, e1, none)
            b.add_was_informed_by(a2, a1, none)
            doc = b.build()
            assert doc["activity"][a1] == {"prov:label": "get_received_emails", "adprov:role": "neutral"}
            assert doc["activity"][a2] == {"prov:label": "send_email", "adprov:role": "sink",
                                           "prov:endTime": "T"}
            assert list(doc["wasGeneratedBy"].values()) == [{"prov:entity": e1, "prov:activity": a1}]
            assert list(doc["used"].values()) == [{"prov:activity": a2, "prov:entity": e1}]
            assert list(doc["wasInformedBy"].values()) == [{"prov:informed": a2, "prov:informant": a1}]


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

class TestValidator:
    def test_valid_document_passes(self):
        b = ProvDocumentBuilder()
        ag = b.add_agent("ag_llm", "llm_agent", "trusted")
        t0 = "2026-01-01T00:00:00+00:00"
        act = b.add_activity("a_read", "get_received_emails", "neutral", t0, t0, step=1, turn=1)
        ent = b.add_entity("e_out", "get_received_emails_output", "untrusted")
        b.add_was_generated_by(ent, act, t0)
        b.add_was_associated_with(act, ag)

        result = validate_prov_document(b.build())
        assert result.ok, str(result)

    def test_dangling_reference_fails(self):
        doc = {
            "prefix": {"adprov": "https://nickjones39.github.io/agentdojo-prov/ns#"},
            "entity": {"adprov:e1": {"prov:label": "x", "adprov:integrity": "untrusted"}},
            "activity": {"adprov:a1": {"prov:label": "read", "adprov:role": "neutral"}},
            "wasGeneratedBy": {
                "adprov:wgb1": {
                    "prov:entity": "adprov:e1",
                    "prov:activity": "adprov:a_NONEXISTENT",  # bad ref
                    "prov:time": "T",
                }
            },
        }
        result = validate_prov_document(doc)
        assert not result.ok
        assert any("NONEXISTENT" in e for e in result.errors)

    def test_stats_count_correctly(self):
        b = ProvDocumentBuilder()
        b.add_agent("ag_llm", "llm_agent", "trusted")
        for i in range(3):
            act = b.add_activity(f"a_{i}", "get_emails", "neutral", "T", "T")
            ent = b.add_entity(f"e_{i}", "email_output", "untrusted")
            b.add_was_generated_by(ent, act, "T")
        b.add_activity("a_sink", "send_email", "sink", "T", "T")

        result = validate_prov_document(b.build())
        assert result.stats["entities"] == 3
        assert result.stats["sink_activities"] == 1
        assert result.stats["untrusted_entities"] == 3


# ── context taint follows what the model had seen ──────────────────────────────
def _call(cid, fn, content=""):
    return ({"id": cid, "function": fn, "args": {}},
            {"role": "tool", "tool_call_id": cid, "function": fn, "args": {},
             "content": content, "error": None})


def _sink_used(doc):
    """(sink activity id, entity id) pairs of the graph's `used` relations."""
    acts = {k for k, v in doc.get("activity", {}).items() if v.get("adprov:role") == "sink"}
    return {(r["prov:activity"], r["prov:entity"]) for r in doc.get("used", {}).values()
            if r["prov:activity"] in acts and not r["prov:entity"].endswith("e_user_query")}


def test_a_sink_does_not_use_a_read_from_its_own_batch():
    from agentprov.prov.compat.adprov_v2_3.build_prov import build_prov
    rc, rt = _call("r1", "get_webpage", "page text")
    sc, st = _call("s1", "send_email", "sent")
    doc = build_prov({"meta": {}, "turns": [
        {"role": "user", "content": "go"},
        {"role": "assistant", "text": "", "tool_calls": [rc, sc]}, rt, st]})
    assert not any(e.endswith("e_r1") for _, e in _sink_used(doc))


def test_a_sink_uses_a_read_returned_before_its_turn():
    from agentprov.prov.compat.adprov_v2_3.build_prov import build_prov
    rc, rt = _call("r1", "get_webpage", "page text")
    sc, st = _call("s1", "send_email", "sent")
    doc = build_prov({"meta": {}, "turns": [
        {"role": "user", "content": "go"},
        {"role": "assistant", "text": "", "tool_calls": [rc]}, rt,
        {"role": "assistant", "text": "", "tool_calls": [sc]}, st]})
    assert any(e.endswith("e_r1") for _, e in _sink_used(doc))








# ── defence placeholders ───────────────────────────────────────────────────────
def test_a_pi_detector_placeholder_is_marked_and_keeps_its_integrity():
    from agentprov.prov.compat.adprov_v2_3.build_prov import PI_DETECTOR_PLACEHOLDER, build_prov
    from agentprov.prov.compat.adprov_v2_3.conformance import ProvValidator
    rc, rt = _call("r1", "get_webpage", PI_DETECTOR_PLACEHOLDER)
    oc, ot = _call("r2", "get_webpage", "a page that merely quotes " + PI_DETECTOR_PLACEHOLDER)
    doc = build_prov({"meta": {}, "turns": [
        {"role": "user", "content": "go"},
        {"role": "assistant", "text": "", "tool_calls": [rc, oc]}, rt, ot]})
    ents = {k.split(":")[-1]: v for k, v in doc["entity"].items()}
    assert ents["e_r1"]["adprov:defence_omitted"] is True
    assert ents["e_r1"]["adprov:integrity"] == ents["e_r2"]["adprov:integrity"] == "untrusted"
    # only the exact placeholder: an output that contains it is real content
    assert "adprov:defence_omitted" not in ents["e_r2"]
    assert "adprov:defence_omitted" not in ents["e_user_query"]
    assert validate_prov_document(doc).ok
    report = ProvValidator(checks=("schema", "round_trip", "completeness")).validate(doc)
    assert report.valid, report






def _call_pair(cid, fn, **tool):
    call = {"id": cid, "function": fn, "args": {}}
    return call, {"role": "tool", "tool_call_id": cid, "function": fn, "args": {},
                  "content": "out", "error": None, **tool}


def _one_call_transcript(call_id, content="out", injections=None, **tool):
    call = {"id": call_id, "function": "get_webpage", "args": {}}
    turn = {"role": "tool", "tool_call_id": call_id, "function": "get_webpage", "args": {},
            "content": content, "error": None, **tool}
    return {"meta": {"injections": injections or {}},
            "turns": [{"role": "user", "content": "q"},
                      {"role": "assistant", "text": "", "tool_calls": [call]}, turn,
                      {"role": "assistant", "text": "done"}]}


def test_a_tool_call_id_cannot_overwrite_the_user_query_entity():
    from agentprov.prov.compat.adprov_v2_3.validate import validate_prov_document
    doc = build_prov(_one_call_transcript("user_query"))
    assert "adprov:e_user_query" in doc["entity"] and len(doc["entity"]) == 2
    assert doc["entity"]["adprov:e_user_query"]["prov:label"] == "user_query"
    assert validate_prov_document(doc).ok


def test_a_tool_call_id_with_characters_an_iri_forbids_still_conforms():
    from agentprov.prov.compat.adprov_v2_3.conformance import ProvValidator
    doc = build_prov(_one_call_transcript("call a<b>\"c"))
    assert all(" " not in k and "<" not in k for k in doc["activity"])
    assert ProvValidator(("schema", "round_trip", "completeness")).validate(doc).valid




def test_an_untimed_call_states_no_time_when_other_calls_were_timed():
    """Falling back to the run's start would put the call before the calls that informed it."""
    c1, t1 = _call_pair("a", "get_webpage", started_at="2026-01-01T00:00:05+00:00",
                        ended_at="2026-01-01T00:00:06+00:00")
    c2, t2 = _call_pair("b", "read_file")                                    # no timestamps
    t = {"meta": {"started_at": "2026-01-01T00:00:00+00:00"},
         "turns": [{"role": "user", "content": "q"},
                   {"role": "assistant", "text": "", "tool_calls": [c1]}, t1,
                   {"role": "assistant", "text": "", "tool_calls": [c2]}, t2]}
    acts = build_prov(t)["activity"]
    assert "prov:startTime" in acts["adprov:a_a"] and "prov:startTime" not in acts["adprov:a_b"]
    del t1["started_at"], t1["ended_at"]                                     # none timed: fall back
    assert build_prov(t)["activity"]["adprov:a_a"]["prov:startTime"] == "2026-01-01T00:00:00+00:00"


def test_read_inbox_is_the_slack_dm_inbox_not_email():
    doc = build_prov({"meta": {}, "turns": [
        {"role": "user", "content": "q"},
        {"role": "assistant", "text": "", "tool_calls": [{"id": "c", "function": "read_inbox", "args": {}}]},
        {"role": "tool", "tool_call_id": "c", "function": "read_inbox", "args": {}, "content": "x",
         "error": None}]})
    assert doc["entity"]["adprov:e_c"]["adprov:source_channel"] == "message"














def test_three_way_id_collisions_still_give_distinct_nodes():
    """ids x_3, x, x: step 3's first fallback x_3 is step 1's, so the suffix is re-tested in a loop."""
    turns = [{"role": "user", "content": "q"}]
    for cid in ("x_3", "x", "x"):
        call, tool = _call_pair(cid, "get_webpage")
        turns += [{"role": "assistant", "text": "", "tool_calls": [call]}, tool]
    doc = build_prov({"meta": {}, "turns": turns})
    assert len(doc["activity"]) == 3 and len(doc["entity"]) == 4
    assert validate_prov_document(doc).ok




