"""The semantics profile ``dtap.tools@2`` (``@1`` on catalogue ``dtap`` 2, D-607; docs/architecture D.16.6, D.16.9): markers, exposure classes, labels,
outcomes, and the observed/inferred line (no class-O or core statement rests on a configured-only payload)."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

import dtap_support as support

from agentprov.adapters.dtap.matcher import match, needles, normalise, windows
from agentprov.adapters.dtap.semantics.tools import CITED_RULES, CLASSES, DATA_FILES, ProfileDataError, parse_tables
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.aer.rules import load_catalogue
from agentprov.sem.validate import validate_sem_document


GOLDEN = Path(__file__).resolve().parent / "golden" / "sem_prov_digests.json"


def test_golden_sem_and_prov_bytes_per_fixture(mapped):
    """The SEM (``dtap.tools@2``) and PROV bytes of every fixture are pinned beside the AER goldens (test_mapper): a change
    of the semantics tables or code shows here and nowhere else (AGENTPROV_REGEN_DTAP_GOLDEN=1 regenerates)."""
    digests = {fid: {"sem": m.sem.file_sha256, "prov": m.prov.digests["prov_json"]} for fid, m in sorted(mapped.items())}
    if os.environ.get("AGENTPROV_REGEN_DTAP_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(digests, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == digests


def _exposure(m):
    return {(a["value"]["channel"], a["value"]["class"]): a for a in m.annotations("dtap.exposure")}


def test_matcher_is_the_census_normaliser():
    assert normalise("Héllo\\nWORLD — ＡＢＣ 12") == "hélloworldabc12"
    assert needles({"a": "short", "b": ["x" * 30, "x" * 30]}) == ["x" * 30]
    text = normalise("alpha " * 20)
    assert match([text], "zz" + text) == "full" and match(["q" * 100], text) == "none"
    assert len(windows("a" * 100)) == 3 and windows("abc") == ["abc"]
    assert match(["a" * 40 + "b" * 60], "a" * 40) == "partial"


def test_every_fixture_document_validates_tier3(mapped):
    profile = load_semantics_profile("dtap.tools", 3)  # D-934: the shipped profile
    for fid, m in mapped.items():
        report = validate_sem_document(m.sem, m.doc, mode="release", profile=profile)
        assert report.ok and not report.errors, fid


def test_exposure_observed_tool_output_f03(mapped):
    m = mapped["F03"]
    env = _exposure(m)[("environment", "observed_tool_output")]
    assert env["ev"] == "D" and env["target"] == "run" and env["rule"] == ["dtap.exposure_class@1"]
    present = [a for a in m.annotations("injection_marker") if a["value"]["status"] == "present"]
    assert present and present[0]["ev"] == "D" and present[0]["value"]["normaliser"] == "dtap.alnum_norm@1"
    assert _exposure(m)[("tool", "configured_only")]["ev"] == "I"


def test_exposure_observed_description_log_f07(mapped):
    m = mapped["F07"]
    tool = _exposure(m)[("tool", "observed_description_log")]
    assert tool["ev"] == "D"
    marker = m.annotations("dtap.description_marker")[0]
    assert marker["value"]["placement"] == "entry" and marker["value"]["status"] == "present" and marker["at"].startswith("/content/terminal/")


def test_exposure_observed_user_step_f02(mapped):
    m = mapped["F02"]
    assert _exposure(m)[("prompt", "observed_user_step")]["ev"] == "D"
    author = m.annotations("author")
    assert author and author[0]["value"] == {"actor": "att"} and author[0]["ev"] == "I"
    integrity = [a for a in m.annotations("integrity") if a["target"] == author[0]["target"]]
    assert integrity[0]["value"] == "untrusted" and integrity[0]["rule"] == ["dtap.integrity_prompt_payload@1"]


def test_exposure_configured_only_and_logged_absent_f04(mapped):
    m = mapped["F04"]
    exposures = _exposure(m)
    configured = exposures[("tool", "configured_only")]
    assert configured["ev"] == "I" and configured["rule"] == ["dtap.configured_exposure_unverified@1"]
    absent = exposures[("environment", "logged_absent")]
    assert absent["ev"] == "D" and all(a["value"]["status"] == "absent" for a in m.annotations("injection_marker"))


def test_no_verified_configuration_means_no_exposure(mapped):
    for fid in ("F12", "F14", "F15", "F09", "F10", "F01"):
        assert mapped[fid].annotations("dtap.exposure") == [], fid


def test_exposure_classes_are_the_declared_vocabulary(mapped):
    seen = Counter(a["value"]["class"] for m in mapped.values() for a in m.annotations("dtap.exposure"))
    assert set(seen) <= set(CLASSES) and {"observed_tool_output", "observed_description_log", "observed_user_step",
                                          "configured_only", "logged_absent"} <= set(seen)


def test_configured_only_reaches_no_class_o_or_core_statement(mapped):
    """D.16.6 the observed/inferred line: a configured-only payload has no observed statement, no core-bundle statement,
    and its fixture entity lives in an inference bundle."""
    m = mapped["F04"]
    configured = _exposure(m)[("tool", "configured_only")]
    fid = configured["value"]["fixture"]
    doc = json.loads(m.prov.prov_json)
    core = {k: v for k, v in doc.get("bundle", {}).items() if ".core." in k}
    blob = json.dumps(core)
    assert f"x:{fid}\"" not in blob and f"x:{fid}." not in blob  # the payload entity is not in the core bundle
    inference = json.dumps({k: v for k, v in doc.get("bundle", {}).items() if ".inf." in k})
    assert f"x:{fid}" in inference
    assessment = json.dumps({k: v for k, v in doc.get("bundle", {}).items() if ".assess." in k or "assessment" in k})
    for stmt in re.findall(r'"apv:annotationValue": "([^"]*configured_only[^"]*)"', assessment):
        assert "configured_only" in stmt
    assert '"apv:evidenceClass": {"$": "apv:Observed"' not in json.dumps(configured)


def test_outcomes_and_non_informative(mapped):
    f09 = mapped["F09"]
    kinds = {a["target"]: a["type"] for a in f09.annotations() if a["target"].startswith("j")}
    j0 = next(j["id"] for j in f09.of("judgement") if j["name"] == "task_success")
    assert kinds[j0] == "dtap.non_informative"
    control = mapped["F10"]
    claims = [a["value"]["claim"] for a in control.annotations("outcome")]
    assert "dtap.attack_judge_on_control" in claims and "attack_succeeded" not in claims
    rejudged = mapped["X01"]
    assert len([a for a in rejudged.annotations("outcome") if a["value"]["claim"] == "attack_succeeded"]) == 2


def test_tool_labels_are_fail_closed(mapped):
    m = mapped["F07"]
    roles = {a["target"]: a["value"] for a in m.annotations("role")}
    assert set(map(tuple, roles.values())) <= {("execute_sink",), ("unknown",)}
    assert ("execute_sink",) in set(map(tuple, roles.values()))  # terminal execute_command via the openclaw prefix split
    results = [a for a in m.annotations("integrity") if "#" in a["target"] and m.get(a["target"].split("#")[0])["role"] == "tool"]
    assert results and {a["value"] for a in results} == {"unknown"}
    profile = load_semantics_profile("dtap.tools", 3)
    assert profile.taint_policy is not None and "unknown" in profile.taint_policy.subject_roles


def test_partial_window_marker_is_ambiguous_and_declares_its_assumption():
    needle = support.payload("F03", "environment")

    def window_only(value):
        for step in value["trajectory"]:
            if step["role"] == "tool":
                step["state"] = needle[:40] + " (rest not logged)"

    m = support.modified("F03", window_only)
    ambiguous = [a for a in m.annotations("injection_marker") if a["value"]["status"] == "ambiguous"]
    assert ambiguous and all(a["ev"] == "I" and a["rule"] == ["dtap.marker_partial_window@1"] for a in ambiguous)
    assert _exposure(m)[("environment", "partial_match")]["ev"] == "I"
    assert load_catalogue("dtap", 3).get("dtap.marker_partial_window@1").assumptions == ("dtap:PartialWindowIsContainment",)


def test_agent_output_only_marker():
    needle = support.payload("F04", "environment")

    def quoted_by_agent(value):
        for step in value["trajectory"]:
            if step["role"] == "agent" and step.get("action") == "send_message_to_user":
                step["metadata"]["message"] = step["metadata"]["message"] + " " + needle
                break

    m = support.modified("F04", quoted_by_agent)
    markers = m.annotations("dtap.agent_output_marker")
    assert markers and markers[0]["ev"] == "D" and markers[0]["value"]["status"] == "present"
    assert _exposure(m)[("environment", "agent_output_only")]["ev"] == "D"


def test_every_sem_rule_is_cited(mapped):
    catalogue = load_catalogue("dtap", 3)
    for ref in CITED_RULES:
        assert catalogue.get(ref) is not None and catalogue.get(ref).citable, ref
    docs = [m.sem for m in mapped.values()]
    docs.append(support.modified("F04", lambda v: v["trajectory"][-1]["metadata"].update(
        message=v["trajectory"][-1]["metadata"].get("message", "") + " " + support.payload("F04", "environment"))).sem)
    docs.append(support.modified("F01", _unknown_server).sem)  # dtap.unknown_server_domain_match@1 (no fixture logs it)
    cited = {r.split("#", 1)[0] for doc in docs for a in doc.annotations for r in a["rule"]}
    cited |= {a["value"]["normaliser"] for doc in docs for a in doc.annotations if isinstance(a["value"], dict) and "normaliser" in a["value"]}
    profile = load_semantics_profile("dtap.tools", 3)
    cited.add(profile.taint_policy.rule)  # the policy is cited by the engine's taint assessments, not by an annotation
    assert set(CITED_RULES) <= cited


# ------------------------------------------------------------------------------------------------ tool tables (D.16.9)
def _table_files() -> dict[str, bytes]:
    root = support.REPO / "src" / "agentprov" / "adapters" / "dtap" / "semantics" / "dtap.tools-2"
    return {name: (root / name).read_bytes() for name in DATA_FILES}


def _unknown_server(value):
    """F01 (openaisdk, domain code) with its execute_command calls logged as openaisdk logs a failed MCP call."""
    for step in value["trajectory"]:
        if step["role"] == "agent" and step["metadata"].get("tool_name") == "execute_command":
            step["metadata"]["server"] = "unknown"


_ENTRY = ('server = "gmail"\ntool = "send_email"\nroles = ["send_sink"]\nintegrity = "unknown"\n'
          'evidence = ["description"]\nreason = "r"\n')


def test_tool_tables_hold_the_evidence_policy():
    """Every entry names roles of the E.7.1 vocabulary, an output integrity that is never trusted, evidence that is
    description or observed (config only corroborates; a name alone is not enough) and a reason; every labelled
    server is a configured server (or a logged spelling of one) or OpenClaw's own tools."""
    import tomllib

    tables = parse_tables(_table_files())
    assert len(tables.labels) > 500 and len(tables.builtins) >= 15
    for (server, tool), (roles, integrity) in tables.labels.items():
        assert tool in tables.servers[server] and integrity in ("untrusted", "unknown") and roles != ("unknown",)

    def canon(name: str) -> str:
        return name.lower().replace(" server", "").replace("_server", "").replace("-", "")

    configured = {canon(s) for servers in tables.domains.values() for s in servers}
    labelled = {server for server, _tool in tables.labels}
    assert {s for s in labelled if s != "openclaw" and canon(s) not in configured} == set()
    assert not any(s.startswith("claude_ai_") or s == "playwright" for s in labelled)  # operator connectors stay unknown
    doc = tomllib.loads(_table_files()["labels.toml"].decode("utf-8"))
    assert all(e["evidence"][0] in ("description", "observed") for e in doc["label"])
    by_config = [e for e in doc["label"] if "config" in e["evidence"]]
    assert by_config and all(e["integrity"] == "untrusted" for e in by_config)


def test_malformed_tool_table_entries_are_refused():
    import pytest

    bad = (
        [_ENTRY.replace('integrity = "unknown"', 'integrity = "trusted"')],  # no tool code is verified
        [_ENTRY.replace('["description"]', '["config"]')],  # config only corroborates
        [_ENTRY.replace('["description"]', "[]")],
        [_ENTRY.replace('["send_sink"]', '["unknown", "send_sink"]')],
        [_ENTRY.replace('["send_sink"]', '["reply_sink"]')],  # outside E.7.1
        [_ENTRY.replace('reason = "r"', 'reason = ""')],
        [_ENTRY.replace('"send_email"', '"teleport"')],  # not in the server's inventory
        [_ENTRY, _ENTRY],  # repeated
    )
    for entries in bad:
        files = _table_files()
        files["labels.toml"] = "".join("[[label]]\n" + e for e in entries).encode()
        with pytest.raises(ProfileDataError):
            parse_tables(files)
    files = _table_files()
    files["labels.toml"] = ("[[label]]\n" + _ENTRY).encode()
    assert parse_tables(files).labels == {("gmail", "send_email"): (("send_sink",), "unknown")}


#: Representative labels: at least one per configured server family, each harness naming, and the harness tools.
_EXPECTED = {
    ("send_email", "gmail"): (("send_sink",), "unknown"),
    ("search_messages", "Gmail"): (("content_source",), "untrusted"),
    ("channels_history", "slack"): (("content_source",), "untrusted"),
    ("post_message_dm", "slack"): (("send_sink",), "unknown"),
    ("get_me", "slack"): (("neutral",), "unknown"),
    ("create_event", "calendar"): (("write_sink", "send_sink"), "unknown"),
    ("read_file", "OS-filesystem"): (("content_source",), "untrusted"),
    ("delete_file", "OS-filesystem"): (("write_sink",), "unknown"),
    ("execute_command", "terminal"): (("execute_sink",), "unknown"),
    ("execute_command", "Research Server"): (("execute_sink",), "unknown"),
    ("upload_arxiv_paper", "Research"): (("send_sink",), "unknown"),
    ("click", "windows-os"): (("execute_sink",), "unknown"),
    ("wait", "macos-os"): (("neutral",), "unknown"),
    ("request_other_test", "HospitalClient"): (("write_sink", "content_source"), "untrusted"),
    ("chat_with_patient", "HospitalClient"): (("send_sink", "content_source"), "untrusted"),
    ("search", "legal"): (("content_source",), "untrusted"),
    ("create_draft", "legal"): (("write_sink",), "unknown"),
    ("trade_stock", "finance"): (("write_sink",), "unknown"),
    ("create_payout", "paypal"): (("send_sink",), "unknown"),
    ("refund_order", "customer_service"): (("send_sink", "write_sink"), "unknown"),
    ("get_case_activities", "customer_service"): (("content_source",), "untrusted"),
    ("delete_record", "salesforce"): (("write_sink",), "unknown"),
    ("verify_refund_eligibility", "travel-suite"): (("endorser",), "unknown"),
    ("query_accommodation", "travel-suite"): (("content_source",), "untrusted"),
    ("add_ticket", "telecom"): (("write_sink",), "unknown"),
    ("query_forum_post", "telecom"): (("content_source",), "untrusted"),
    ("browser_navigate", "browser"): (("egress_read", "content_source"), "untrusted"),
    ("createJiraIssue", "atlassian"): (("write_sink",), "unknown"),
    ("getAccessibleAtlassianResources", "atlassian"): (("neutral",), "unknown"),
    ("meetings_create", "zoom"): (("write_sink",), "unknown"),
    ("sql_exec_tool", "snowflake"): (("content_source",), "untrusted"),
    ("send_whatsapp_message", "whatsapp"): (("send_sink",), "unknown"),
    ("get_document", "googledocs"): (("content_source",), "untrusted"),
    ("submit", "google-form"): (("send_sink",), "unknown"),
    ("send_message", "telegram"): (("send_sink",), "unknown"),
    ("databricks-dbsql-exec", "databricks"): (("content_source",), "unknown"),
    # OpenClaw: prefixed MCP tools (longest prefix), the double-underscore naming, and OpenClaw's own tools
    ("gmail_send_email", "openclaw"): (("send_sink",), "unknown"),
    ("OS-filesystem_read_file", "openclaw"): (("content_source",), "untrusted"),
    ("gmail__search_messages", "openclaw"): (("content_source",), "untrusted"),
    ("exec", "openclaw"): (("execute_sink",), "unknown"),
    ("web_fetch", "openclaw"): (("egress_read",), "unknown"),
    # harness tools logged with server "unknown"
    ("Bash", "unknown"): (("execute_sink",), "unknown"),
    ("ToolSearch", "unknown"): (("neutral",), "unknown"),
    ("load_skill", "unknown"): (("content_source",), "unknown"),
}


def test_representative_tool_labels():
    profile = load_semantics_profile("dtap.tools", 3)
    for (name, server), (roles, integrity) in _EXPECTED.items():
        got = profile.tool_label(name, server)
        assert got[:2] == (roles, integrity), (server, name, got)
        assert got[2][0] == "dtap.tool_table@1"
        assert ("dtap.openclaw_prefix_split@1" in got[2]) == (server == "openclaw")


def test_unlabelled_tools_are_fail_closed():
    profile = load_semantics_profile("dtap.tools", 3)
    unknown = (("unknown",), "unknown")
    for name, server in (("search_threads", "claude_ai_Gmail"), ("browser_run_code", "playwright"),
                         ("Agent", "unknown"), ("Task", "unknown"), ("analyze_document", "terminal"),
                         ("teleport", "gmail"), ("send_email", "no-such-server"), (None, "gmail")):
        assert profile.tool_label(name, server) == (*unknown, ("dtap.unknown_tool@1",)), (server, name)
    for name in ("browser", "sessions_spawn", "no_such_server_tool"):  # OpenClaw: no label, or no declared prefix
        assert profile.tool_label(name, "openclaw") == (*unknown, ("dtap.unknown_tool@1", "dtap.openclaw_prefix_split@1"))


def test_unknown_server_resolves_by_domain_or_stays_unknown():
    """D.16.9: a call logged with server "unknown" (a failed MCP call) takes the label of the one server of the run's
    domain whose inventory holds the name (dtap.unknown_server_domain_match@1, I, the domain a premise); a name no
    domain server holds stays unknown, and a listed harness built-in is looked up first."""
    profile = load_semantics_profile("dtap.tools", 3)
    rules = ("dtap.tool_table@1", "dtap.unknown_server_domain_match@1")
    assert profile.tool_label("request_other_test", "unknown", "medical") == (("write_sink", "content_source"), "untrusted", rules)
    assert profile.tool_label("shell", "unknown", "windows") == (("execute_sink",), "unknown", rules)
    assert profile.tool_label("shell", "unknown", "code")[0] == ("unknown",)  # the code domain configures no shell
    assert profile.tool_label("shell", "unknown", None)[0] == ("unknown",)
    assert profile.tool_label("Bash", "unknown", "code")[2] == ("dtap.tool_table@1",)
    entry = load_catalogue("dtap", 3).get("dtap.unknown_server_domain_match@1")
    assert entry is not None and entry.cls == "I" and entry.assumptions == ("dtap:UnknownServerIsFailedMcpCall",)
    m = support.modified("F01", _unknown_server)  # domain code: terminal is the domain's only server
    roles = [a for a in m.annotations("role") if a["rule"] == list(rules)]
    assert roles and all(a["value"] == ["execute_sink"] and a["ev"] == "I" for a in roles)
    assert all({"id": "exec", "p": "/ext/dtap/path_facets/domain"} in a["premises"] for a in roles)
    report = validate_sem_document(m.sem, m.doc, mode="release", profile=profile)
    assert report.ok and not report.errors


def test_version_1_stays_on_the_archived_catalogue_and_version_2_differs_only_in_it():
    """D-607 (the D-31 addendum's option B): the scratch corpora record dtap.tools@1 (digest dec908044648) on catalogue
    dtap 1; @2 is the same tables and code on catalogue dtap 2, so a corpus reads one catalogue version (H.2.5)."""
    v1, v2 = load_semantics_profile("dtap.tools", 1), load_semantics_profile("dtap.tools", 2)
    assert v1.sha256.removeprefix("sha256:").startswith("dec908044648")
    assert dict(v1.rules) == {"dtap": 1} and dict(v2.rules) == {"dtap": 2}
    assert v1.tables == v2.tables and dict(v1.classes) == dict(v2.classes)
    root = support.REPO / "src" / "agentprov" / "adapters" / "dtap" / "semantics"
    assert all((root / "dtap.tools-1" / n).read_bytes() == (root / "dtap.tools-2" / n).read_bytes()
               for n in DATA_FILES if n != "profile.toml")
    v3 = load_semantics_profile("dtap.tools", 3)  # D-934: version 2's tables on catalogue dtap 3
    assert dict(v3.rules) == {"dtap": 3} and v3.tables == v2.tables and dict(v3.classes) == dict(v2.classes)
    assert all((root / "dtap.tools-2" / n).read_bytes() == (root / "dtap.tools-3" / n).read_bytes()
               for n in DATA_FILES if n != "profile.toml")


def test_item_54_applies_only_under_version_2():
    """Regen item 54 is version-gated (D-31 owner ruling 2026-10-21; D-607): for a payload with neither a vector nor a
    content member, ``@2`` takes the channel from the configured step type and cites ``/kind``; ``@1`` keeps its
    behaviour as before item 54 (channel ``other``, premises ``/content`` and ``/vector``)."""
    from test_core_d_dtap import _indirect, _payload_fixtures

    from agentprov.sem.engine import annotate

    m = _indirect("        - type: environment\n")
    [fx] = _payload_fixtures(m)
    assert "vector" not in fx and "content" not in fx
    out = {}
    for version in (1, 2):
        sem = annotate(m.doc, load_semantics_profile("dtap.tools", version))
        out[version] = next(a for a in sem.annotations if a["type"] == "dtap.exposure" and a["value"]["fixture"] == fx["id"])
    assert out[2]["value"]["channel"] == "environment" and out[1]["value"]["channel"] == "other"
    assert {"id": fx["id"], "p": "/kind"} in out[2]["premises"]
    assert {"id": fx["id"], "p": "/kind"} not in out[1]["premises"]
    assert {"id": fx["id"], "p": "/content"} in out[1]["premises"]


def test_versions_1_and_2_annotate_every_fixture_identically(mapped):
    """The pinned fixtures hold no payload without a vector or content (the D-607 census): ``@1`` and ``@2`` give the
    same annotations on every one of them."""
    from agentprov.sem.engine import annotate

    v1, v2 = load_semantics_profile("dtap.tools", 1), load_semantics_profile("dtap.tools", 2)
    for fid, m in mapped.items():
        assert annotate(m.doc, v1).annotations == annotate(m.doc, v2).annotations, fid
