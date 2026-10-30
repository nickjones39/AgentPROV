"""The semantics profile ``wirelog.tools@1`` (docs/architecture D.20.8; C.14): labels, markers, authorship and outcomes
on the committed fixtures. No fixture content is printed."""

from __future__ import annotations

from agentprov.adapters.semantics_profiles import load_semantics_profile


def _by_target(m, type_):
    return {a["target"]: a for a in m.annotations(type_)}


def test_tool_labels(mapped):
    profile = load_semantics_profile("wirelog.tools", 1)
    assert profile.tool_label("read_file")[:2] == (("content_source",), "untrusted")
    assert profile.tool_label("send_email")[:2] == (("send_sink",), "unknown")
    assert profile.tool_label("delete_everything") == (("unknown",), "unknown", ("wirelog.unknown_tool@1",))
    m = mapped["tool_description_hijack"]
    roles = _by_target(m, "role")
    for te in m.of("tool_execution"):
        assert roles[te["id"]]["value"] == list(profile.tool_label(te["name"])[0])


def test_integrity_of_fixtures_and_prompts(mapped):
    m = mapped["system_prompt_explicit"]
    integrity = _by_target(m, "integrity")
    fixtures = {f["kind"]: f["id"] for f in m.of("fixture")}
    assert integrity[fixtures["injection_payload"]]["value"] == "untrusted"
    assert integrity[fixtures["tool_definitions"]]["value"] == "untrusted"  # the poisoned description
    assert integrity["m0#0"]["value"] == "trusted" and integrity["m0#0"]["rule"] == ["wirelog.integrity_system_prompt@1"]
    assert integrity["m1#0"]["value"] == "trusted" and integrity["m1#0"]["rule"] == ["wirelog.integrity_task_prompt@1"]
    clean = mapped["tool_result_multi_result"]
    tools_fx = next(f["id"] for f in clean.of("fixture") if f["kind"] == "tool_definitions")
    assert _by_target(clean, "integrity")[tools_fx]["value"] == "unknown"  # clean schema; the payload rides in a result
    for rec in m.of("message"):
        if rec["actor"] == "agent":
            assert all(integrity[f"{rec['id']}#{k}"]["value"] == "trusted" for k in range(len(rec["parts"])))


def test_injection_markers_and_author(mapped):
    m = mapped["tool_result_multi_result"]
    markers = m.annotations("injection_marker")
    present = [a for a in markers if a["value"]["status"] == "present"]
    assert present and all(a.get("span") and a["at"] == "/text" for a in present)
    authors = {a["target"] for a in m.annotations("author")}
    assert {a["target"] for a in present} == authors
    assert all(_by_target(m, "integrity")[t]["value"] == "untrusted" for t in authors)
    assert all(a["ev"] == "I" for a in m.annotations("author"))
    early = mapped["first_batch_attacked_early"]
    assert early.annotations("injection_marker") == []
    doc_authors = early.annotations("author")
    assert doc_authors and all("wirelog.first_batch_document@1" in a["rule"] for a in doc_authors)
    clean = mapped["first_batch_clean"]
    assert clean.annotations("author") == []


def test_outcomes(mapped):
    m = mapped["tool_description_hijack"]
    outcomes = {a["value"]["claim"]: a["value"]["holds"] for a in m.annotations("outcome")}
    hijack = next(j for j in m.of("judgement") if j["name"] == "hijack")
    assert outcomes["attack_succeeded"] is (hijack["value"] == "1")
    assert set(outcomes) == {"attack_succeeded", "wirelog.exfiltration", "wirelog.silent_send"}
    assert mapped["first_batch_clean"].annotations("outcome") == []  # no attack, no attack claim


def test_taint_policy():
    profile = load_semantics_profile("wirelog.tools", 1)
    assert profile.taint_policy is not None and profile.taint_policy.rule == "wirelog.taint_sink_untrusted@1"
    assert "send_sink" in profile.taint_policy.subject_roles
