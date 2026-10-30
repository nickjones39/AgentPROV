"""D-607: the dtap family's redaction of listed account paths over every AER string (agentprov.adapters.dtap.redact).

Every account name here is synthetic and assembled at run time; its label is computed in the test from the name with
the shipped label function and listed in a test copy of the profile. The real profile's labels are never derived here.
"""

from __future__ import annotations

import json
import re

import dtap_support as support
import pytest

from agentprov.adapters.dtap import redact as redact_mod
from agentprov.adapters.dtap.redact import RULE, Redactor, parse_redact_rules, span_label
from agentprov.adapters.profiles import load_profile, parse_profile
from agentprov.errors import ProfileError

#: synthetic accounts, never a real one: assembled so that no literal sits in the file
LISTED = "zq" + "vexample" + "acct"
OTHER = "bench" + "mark" + "person"
SALT = "dtap-bench"


def _rule(listed: list[str], **over):
    profile = load_profile("dtap-bench")
    entry = dict(profile.family_table()["redact"][0])
    entry["labels"] = listed
    entry.update(over)
    return entry


def _redactor(labels=None, *, every_rule: bool = False) -> Redactor:
    labels = [span_label(LISTED, salt=SALT)] if labels is None else labels
    if not every_rule:
        return Redactor("dtap-bench", 2, parse_redact_rules([_rule(labels)], "t"))
    entries = [dict(e, labels=labels) for e in load_profile("dtap-bench").family_table()["redact"]]
    return Redactor("dtap-bench", 2, parse_redact_rules(entries, "t"))


def _acct(name: str = LISTED) -> str:
    return "acct-" + span_label(name, salt=SALT)


# ------------------------------------------------------------------------------------------------ grammar
@pytest.mark.parametrize("change, message", [
    ({"extra": 1}, "unknown keys"),
    ({"scope": "model_id"}, "scope"),
    ({"id": "Bad-Id"}, "id is"),
    ({"pattern": "(?P<x>a)"}, "no (?P<span>"),
    ({"pattern": "(?P<span>a*)"}, "empty string"),
    ({"pattern": "(?P<span>[)"}, "does not compile"),
    ({"replacement": "acct"}, "placeholder"),
    ({"replacement": "acct-{leaf}"}, "placeholder"),
    ({"replacement": "acct-{span12}}"}, "brace"),
    ({"labels": ["ABCDEF012345"]}, "12-hex"),
    ({"labels": ["0123456789ab", "0123456789ab"]}, "12-hex"),
    ({"labels": "0123456789ab"}, "12-hex"),
])
def test_rule_grammar_is_closed(change, message):
    with pytest.raises(ProfileError, match=re.escape(message)):
        parse_redact_rules([_rule([], **change)], "t")
    with pytest.raises(ProfileError, match="unique"):
        parse_redact_rules([_rule([]), _rule([])], "t")


def test_the_shipped_profile_lists_six_labels_and_no_name():
    profile = load_profile("dtap-bench")
    rules = parse_redact_rules(profile.family_table()["redact"], "shipped")
    assert profile.version == 3  # v3: D-934/D-935
    assert [r.id for r in rules] == ["host_account", "host_account_token", "host_account_dotted"]
    assert all(r.scope == "all_strings" and r.replacement == "acct-{span12}" for r in rules)
    # five PC-01 accounts and one other letter case of one of them; the same allowlist in every rule
    assert len({r.labels for r in rules}) == 1 and len(rules[0].labels) == 6
    assert all(re.fullmatch(r"[0-9a-f]{12}", x) for x in rules[0].labels)
    assert load_profile("dtap-bench", 1).family_table().get("redact") is None  # v1 archived unchanged (D-31)


def test_span_label_is_the_d476_construction():
    import hashlib

    assert span_label(LISTED, salt=SALT) == hashlib.sha256(f"{SALT}\0{LISTED}".encode()).hexdigest()[:12]


# ------------------------------------------------------------------------------------------------ strings
@pytest.mark.parametrize("form", [
    "/home/{n}/.ssh/config", "/Users/{n}/Library/x", "cd /home/{n}", "path=/Users/{n}.", "'/home/{n}'",
    "C:\\Users\\{n}\\Desktop", "C:\\\\Users\\\\{n}\\\\Desktop", "c:/users/{n}/x", "D:\\USERS\\{n}", "/mnt/c/Users/{n}/x",
    "\\/home\\/{n}\\/x", "file:///home/{n}/a", "(/home/{n})", "/home/{n}:/bin/bash", "[\"/Users/{n}\"]",
])
def test_a_listed_account_is_redacted_in_every_form(form):
    red = _redactor()
    text, rid = red.text(form.format(n=LISTED))
    assert rid == "host_account" and LISTED not in text and text == form.format(n=_acct())


@pytest.mark.parametrize("form", [
    "/home/{n}/x",  # an unlisted account (benchmark or model content)
    "https://example.com/home/{n}/",  # not an absolute path
    "/var/home/{n}/x", "/users/{n}/x",  # deeper or lower-case roots are outside D-457's forms
    "~{n}/x", "{n}",  # no account-path form
])
def test_unlisted_or_unstructured_text_is_untouched(form):
    red = _redactor()
    other = form.format(n=OTHER)
    assert red.text(other) == (other, None)
    if form not in ("/home/{n}/x",):
        listed = form.format(n=LISTED)
        assert red.text(listed) == (listed, None)


DOTTED = "zq" + "." + "vexample"


@pytest.mark.parametrize("form", [
    "-rw-r--r--  1 {n}  staff  120 Mar  5 12:34 notes.txt",  # ls -l owner column
    "/Users/x/.claude/projects/-Users-{n}-Desktop-repo/a.jsonl",  # a munged project directory
    "/srv/home/{n}/data", "\\n/home/{n}/x",  # a deeper root; a path right after an escaped newline
    "Mar  5 12:34 {n}\\n", "owner={n};", "{n}_backup",
])
def test_the_token_rules_close_the_contexts_the_path_rule_cannot_see(form):
    # a dotted name inside a longer dotted or munged token (`-Users-<a>.<b>-Desktop`, `<a>.<b>_backup`) is one token
    # with it and stays: a known limit, absent from the PC-01 data (the D-607 census residue is 0)
    names = (LISTED,) if "-Users-" in form or form.endswith("_backup") else (LISTED, DOTTED)
    for name in names:
        red = _redactor([span_label(name, salt=SALT)], every_rule=True)
        text, rid = red.text(form.format(n=name))
        assert rid is not None and name not in text and _acct(name) in text, (form, name)
        other = form.format(n=OTHER)
        assert red.text(other) == (other, None)


def test_a_token_rule_never_matches_inside_a_longer_token():
    red = _redactor(every_rule=True)
    for text in (f"x{LISTED}", f"{LISTED}9", f"{LISTED.capitalize()}"):  # another letter case is another label
        assert red.text(text) == (text, None)


def test_a_longer_name_with_the_listed_prefix_is_another_account():
    red = _redactor()
    longer = f"/home/{LISTED}x/y"
    assert red.text(longer) == (longer, None)


def test_pointers_are_redacted_token_by_token():
    red = _redactor()
    key = f"/home/{LISTED}/a"
    assert red.pointer("/parts/0/value/" + key.replace("/", "~1")) == "/parts/0/value/" + f"/home/{_acct()}/a".replace("/", "~1")
    # two tokens "home" and the name never form a path: a pointer's own slash is not a path separator
    nested = f"/parts/0/value/home/{LISTED}"
    assert red.pointer(nested) == nested
    assert red.citation(f"dtap.x@1#/ext/dtap/{key.replace('/', '~1')}").endswith(f"/home/{_acct()}/a".replace("/", "~1"))


def test_two_spans_with_one_label_are_a_profile_defect(monkeypatch):
    monkeypatch.setattr(redact_mod, "span_label", lambda span, *, salt: "0123456789ab")
    red = Redactor("dtap-bench", 2, parse_redact_rules([_rule(["0123456789ab"])], "t"))
    red.text(f"/home/{LISTED}/x")
    with pytest.raises(ProfileError, match="one label to two different strings"):
        red.text(f"/home/{OTHER}/x")


def test_apply_covers_values_keys_ext_lex_and_pointers_and_keeps_locators():
    red = _redactor()
    key = f"/home/{LISTED}/notes"
    esc = key.replace("/", "~1")
    record = {
        "k": "message", "id": "m1", "ev": "O", "by": "source",
        "parts": [{"t": "tool_result", "value": {"zeta": 1, key: f"see /Users/{LISTED}/x and /home/{OTHER}/y"}}],
        "src": [{"a": "a0", "p": "/trajectory/1"}],
        "evf": {f"/parts/0/value/{esc}": "I", "/actor": "I"},
        "unk": {f"/parts/0/value/{esc}/t": "not_recorded"},
        "rule": [f"dtap.tool_step_is_execution_unverified@1#/parts/0/value/{esc}"],
        "ext": {"dtap": {"server": f"/home/{LISTED}"}, "lex": {"ord": {"/parts/0/value": ["zeta", key]},
                                                                "flt": [f"/parts/0/value/{esc}"]}},
    }
    done = red.apply(record, lambda p: f"{RULE}#{p}")
    blob = json.dumps(record)
    assert LISTED not in blob and OTHER in blob and _acct() in blob
    new_key = f"/home/{_acct()}/notes"
    new_esc = new_key.replace("/", "~1")
    assert set(record["parts"][0]["value"]) == {"zeta", new_key}
    assert record["ext"]["lex"] == {"ord": {"/parts/0/value": ["zeta", new_key]}, "flt": [f"/parts/0/value/{new_esc}"]}
    assert record["src"] == [{"a": "a0", "p": "/trajectory/1"}]  # the locator stays on the raw field
    pointers = {p for p, _rid in done}
    assert pointers == {f"/parts/0/value/{new_esc}", "/ext/dtap/server"}  # the key (its value holds the listed path too)
    assert record["evf"][f"/parts/0/value/{new_esc}"] == "I"  # never raised above an existing I
    assert record["evf"]["/ext/dtap/server"] == "D"
    assert f"/parts/0/value/{new_esc}/t" in record["unk"]
    assert f"dtap.tool_step_is_execution_unverified@1#/parts/0/value/{new_esc}" in record["rule"]
    assert f"{RULE}#/ext/dtap/server" in record["rule"]
    assert {"p": "/ext/dtap/server", "rule": "dtap-bench@2#host_account"} in record["ext"]["dtap"]["redacted"]


def test_no_listed_label_means_no_change():
    record = {"k": "message", "id": "m", "ev": "O", "parts": [{"t": "text", "text": f"/home/{LISTED}/x"}]}
    before = json.dumps(record, sort_keys=True)
    assert Redactor("dtap-bench", 2, parse_redact_rules([_rule([])], "t")).apply(record, str) == []
    assert json.dumps(record, sort_keys=True) == before


# ------------------------------------------------------------------------------------------------ the mapper
@pytest.fixture
def listed_profile(monkeypatch):
    """The shipped profile with the synthetic account's label as its only listed label (a test copy, never shipped)."""
    import agentprov.adapters.runner as runner

    shipped = load_profile("dtap-bench")
    text = support.REPO.joinpath("src/agentprov/adapters/dtap/profiles/dtap-bench.profile.toml").read_text(encoding="utf-8")
    text = re.sub(r"labels = \[\n(?:  \"[0-9a-f]{12}\",[^\n]*\n)+\]\n", f'labels = ["{span_label(LISTED, salt=SALT)}"]\n', text)
    assert text.count(f'labels = ["{span_label(LISTED, salt=SALT)}"]') == 3
    test_profile = parse_profile(text.encode("utf-8"), source="test")
    assert test_profile.version == shipped.version
    real = runner.load_profile
    monkeypatch.setattr(runner, "load_profile", lambda pid, version=None: test_profile if pid == "dtap-bench" else real(pid, version))
    return test_profile


def _run_with_accounts():
    steps = [
        {**support.call("read_file", {"filepath": f"/home/{LISTED}/.ssh/config", "dirpath": f"/home/{OTHER}/data"}),
         "action": f"read_file(filepath='/home/{LISTED}/.ssh/config')"},
        {**support.result("read_file", state=f"cat: /Users/{LISTED}/Library/x: denied; owner /home/{OTHER}/data"),
         "metadata": {"tool_name": "read_file", "server": "s"}},
        support.call("list_dir", {"path": f"C:\\Users\\{LISTED}\\Desktop"}),
        {"role": "tool", "metadata": {"tool_name": "list_dir", "server": "s"},
         "state": {"zeta": 1, f"/home/{LISTED}/notes.txt": "x", f"/home/{OTHER}/b": "y"}},
    ]
    label, data = support.run(steps)
    value = json.loads(data)
    value["traj_info"]["agent_final_response"] = f"I read /home/{LISTED}/.ssh/config; /home/{OTHER}/data is empty."
    return label, json.dumps(value).encode()


def test_mapper_redacts_a_listed_account_everywhere_and_leaves_others(listed_profile):
    label, data = _run_with_accounts()
    m = support.map_label(label, runs={label: data}, tasks={}, sem=True, prov=True)
    assert LISTED.encode() not in m.data and OTHER.encode() in m.data  # every AER string; the unlisted name untouched
    sem = json.dumps([m.sem.header, *m.sem.records, m.sem.seal])
    assert LISTED not in sem and LISTED.encode() not in m.prov.prov_json and _acct().encode() in m.prov.prov_json
    from agentprov.validate import validate_prov

    assert [o.id for o in validate_prov(m.prov.prov_json, m.doc, sems=[m.sem]).failed()] == []
    acct = _acct()
    redacted = {(r["id"], e["p"]) for r in m.records for e in r.get("ext", {}).get("dtap", {}).get("redacted", [])}
    agent_args = {p for rid, p in redacted if rid == "m0"}
    assert any(p.endswith("/args/filepath") for p in agent_args), redacted  # agent tool-call arguments
    assert any(p == "/ext/dtap/action" for p in agent_args)  # the agent step's action display string
    assert ("exec", "/ext/dtap/final_response") in redacted  # the final response (model-authored, D-607)
    assert any(rid == "m1" and p == "/parts/0/text" for rid, p in redacted)  # tool output text
    assert any(rid == "m3" and p.startswith("/parts/0/value/") for rid, p in redacted)  # tool output object key
    assert any(rid.startswith("te") and p.startswith("/args/") for rid, p in redacted)  # tool execution arguments
    head = m.header
    assert acct in head["ext"]["dtap"]["final_response"] and OTHER in head["ext"]["dtap"]["final_response"]
    assert head["evf"]["/ext/dtap/final_response"] == "D" and f"{RULE}#/ext/dtap/final_response" in head["rule"]
    (issue,) = [i for i in m.issues if i["code"] == "dtap.value_redacted"]
    assert issue["rule"] == RULE and issue["ids"] == ["exec"] and int(issue["detail"]) == len(redacted)
    assert head["profile"]["version"] == 3 and head["rules"] == {"aer": 1, "dtap": 3}


def test_mapper_redacts_nothing_and_raises_no_issue_for_unlisted_accounts():
    label, data = _run_with_accounts()
    m = support.map_label(label, runs={label: data}, tasks={})
    assert LISTED.encode() in m.data and "dtap.value_redacted" not in m.codes()  # the shipped labels list neither name
    assert not any("redacted" in r.get("ext", {}).get("dtap", {}) for r in m.records)
