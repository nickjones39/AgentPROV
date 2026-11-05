"""The semantics profile ``wirelog.tools@1`` (docs/architecture D.20.8; C.14): labels, markers, authorship and outcomes
on the committed fixtures. No fixture content is printed."""

from __future__ import annotations

import wirelog_support as support

from agentprov.adapters.semantics_profiles import load_semantics_profile


def _by_target(m, type_):
    return {a["target"]: a for a in m.annotations(type_)}


def test_tool_labels(mapped):
    profile = load_semantics_profile("wirelog.tools", support.SEM_VERSION)
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


def _pad_results(requests: list) -> None:
    """Every tool result text of every request grows past 1 MiB (the payload, where present, stays inside it)."""
    for request in requests:
        for message in request["messages"]:
            for block in message["content"] if isinstance(message.get("content"), list) else ():
                result = block.get("toolResult") if isinstance(block, dict) else None
                for item in result.get("content", ()) if isinstance(result, dict) else ():
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        item["text"] += "\n" + "x" * (1 << 20)


def test_a_result_not_inlined_is_not_searched():
    """AU-RC-3 (D-1063, regen-batch row 181): a tool result over 1 MiB is a digest in the AER; ``wirelog.tools@2`` does
    not search the digest object for payloads (it marked them ``absent`` at D, dropped the attacker as author and fell
    back to the tool table): each marker is ``gap`` under ``wirelog.result_not_searched@1`` (I), no author is asserted,
    and the integrity is the table's ``untrusted`` or else ``unknown``. ``@1`` keeps its behaviour for the sealed corpus."""
    small = support.map_run("tool_result_multi_result", sem=True)
    present = {a["target"] for a in small.annotations("injection_marker") if a["value"]["status"] == "present"}
    assert present
    m = support.modified("tool_result_multi_result", requests=_pad_results, sem=True, prov=True)
    assert "wirelog.content_not_inlined" in m.codes()
    results = {f"{r['id']}#0": r for r in m.of("message") if r["parts"] and r["parts"][0]["t"] == "tool_result"}
    digested = {pid for pid, r in results.items() if "not_inlined" in (r["parts"][0].get("value") or {})}
    assert present <= digested
    markers = [a for a in m.annotations("injection_marker") if a["target"] in digested]
    assert markers and all(a["value"]["status"] == "gap" and a["ev"] == "I" for a in markers)
    assert all(a["rule"] == ["wirelog.result_not_searched@1"] and "span" not in a for a in markers)
    assert not any(a["target"] in digested for a in m.annotations("author"))
    integrity = _by_target(m, "integrity")
    assert all(integrity[pid]["value"] in ("untrusted", "unknown") for pid in digested)
    from agentprov.aer.rules import RuleRegistry
    from agentprov.sem.engine import annotate
    from agentprov.sem.validate import validate_sem_document
    from agentprov.validate import validate_prov

    profile = load_semantics_profile("wirelog.tools", support.SEM_VERSION)
    assert validate_sem_document(m.sem, m.doc, catalogues=RuleRegistry.default(), mode="release", profile=profile).ok
    assert validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed() == []
    old = annotate(m.doc, load_semantics_profile("wirelog.tools", 1))  # @1: as recorded, unchanged
    assert {a["value"]["status"] for a in old.annotations if a["type"] == "injection_marker" and a["target"] in digested} \
        == {"absent"}


def test_outcomes(mapped):
    m = mapped["tool_description_hijack"]
    outcomes = {a["value"]["claim"]: a["value"]["holds"] for a in m.annotations("outcome")}
    hijack = next(j for j in m.of("judgement") if j["name"] == "hijack")
    assert outcomes["attack_succeeded"] is (hijack["value"] == "1")
    assert set(outcomes) == {"attack_succeeded", "wirelog.exfiltration", "wirelog.silent_send"}
    assert mapped["first_batch_clean"].annotations("outcome") == []  # no attack, no attack claim


def test_taint_policy():
    profile = load_semantics_profile("wirelog.tools", support.SEM_VERSION)
    assert profile.taint_policy is not None and profile.taint_policy.rule == "wirelog.taint_sink_untrusted@1"
    assert "send_sink" in profile.taint_policy.subject_roles
