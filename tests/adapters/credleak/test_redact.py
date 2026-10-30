"""Tool-output redaction of third-party account paths (DECISIONS D-605, applying D-604; redact.py).

Every account name here is made up at run time (never a deposited value); no test prints source content.
"""

from __future__ import annotations

import json
import re
import sys

import credleak_support as support
import pytest

from agentprov.adapters.credleak.redact import ISSUE, RULE, Redactor, parse_redact_rules
from agentprov.adapters.profiles import load_profile
from agentprov.errors import ProfileError

sys.path.insert(0, str(support.REPO / "tools"))
from release_scan import ACCOUNT_ALLOWLIST  # noqa: E402

SYNTH_LABEL = "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.9__2026.json"
#: A made-up account name (assembled at run time) and a second one.
NAME = "tst" + "acct" + "7"
OTHER = "zz" + "person"


def _redactor() -> Redactor:
    profile = load_profile("credleak-p15b")
    rules = parse_redact_rules(profile.family_table()["redact"], "test")
    return Redactor(profile.id, profile.version, rules)


def _text(value: str) -> str:
    return _redactor().text(value)[0]


def _cell(command: str, output: object) -> bytes:
    turn = {"turnNumber": 0, "userMessage": "do the task", "assistantResponse": f"I ran ls /home/{NAME}/proj",
            "toolCalls": [{"tool": "Bash", "input": {"command": command}, "output": output}],
            "timestamp": "2026-06-11T08:00:00.000Z"}
    return support.synthetic_cell(turns=[turn])


def _map(data: bytes, **kwargs):
    (m,) = support.map_cell(SYNTH_LABEL, data, **kwargs)
    return m


def _result(m):
    (result,) = [r for r in m.of("message") if r["role"] == "tool"]
    return result


def test_a_tool_output_path_is_redacted_and_a_model_command_is_not():
    """The regression test of D-605: before it, the mapper copied the account name of tool output verbatim."""
    m = _map(_cell(f"ls /home/{NAME}/proj", f"/home/{NAME}/proj/a.txt\n"))
    result = _result(m)
    text = result["parts"][0]["text"]
    assert NAME not in json.dumps(result)
    assert re.fullmatch(r"/home/acct-[0-9a-f]{12}/proj/a\.txt\n", text)
    assert result["evf"]["/parts/0/text"] == "D" and f"{RULE}#/parts/0/text" in result["rule"]
    assert result["ext"]["credleak"]["redacted"] == [{"p": "/parts/0/text", "rule": "credleak-p15b@2#account_path"}]
    (issue,) = [i for i in m.issues if i["code"] == ISSUE]
    assert (issue["ids"], issue["detail"], issue["rule"]) == (["exec"], "1", RULE)
    # model-authored text stays verbatim (D-604): the call's input, the execution's args and the assistant text
    (call,) = [r for r in m.of("message") if r["role"] == "assistant" and r["parts"][0]["t"] == "tool_call"]
    assert NAME in call["parts"][0]["args"]["command"]
    (te,) = m.of("tool_execution")
    assert NAME in te["args"]["command"]
    assert any(NAME in json.dumps(r) for r in m.of("message") if r["role"] == "assistant" and r["parts"][0]["t"] == "text")
    # the source locator still names the raw field
    assert result["src"] == [{"a": "a0", "p": "/runs/0/turns/0/toolCalls/0/output"}]


def test_the_label_is_salted_stable_and_distinct():
    one = _text(f"/home/{NAME}/x")
    assert one == _text(f"cd /home/{NAME}/x")[3:] and one != _text(f"/home/{OTHER}/x")
    assert _text(f"/Users/{NAME}/x").removeprefix("/Users/") == one.removeprefix("/home/")
    import hashlib

    assert one == f"/home/acct-{hashlib.sha256(f'credleak-p15b{chr(0)}{NAME}'.encode()).hexdigest()[:12]}/x"


@pytest.mark.parametrize("form", [
    "/home/{n}/proj", "home/{n}/proj", "/Users/{n}/proj", "Users/{n}", "/home/{n}", "see /home/{n}.", "'/home/{n}'",
    "(/home/{n}:/bin/sh)", "/home/{n}\n", "x=/home/{n};", "/home/{n}..",
])
def test_every_path_form_of_the_rule_is_redacted(form):
    out = _text(form.format(n=NAME))
    assert NAME not in out and "acct-" in out
    assert out.count(".") == form.count(".")  # trailing dots stay outside the span


@pytest.mark.parametrize("form", [
    "my{h}/{n}/x", "/var{h}x/{n}", "{n}", "/{h}//x", "/home/" + "a" * 65 + "/",
])
def test_what_is_not_an_account_path_is_kept(form):
    value = form.format(h="home", n=NAME)
    assert _text(value) == value


def test_generic_names_are_never_redacted_and_the_list_is_release_scans():
    """The profile's allowlist is exactly the release scan's generic names within the name class (D-457, D-605)."""
    profile = load_profile("credleak-p15b")
    (rule,) = [r for r in profile.family_table()["redact"] if r["id"] == "account_path"]
    listed = set(re.search(r"\(\?i:([^)]*)\)", rule["pattern"]).group(1).split("|"))
    assert listed == {n for n in ACCOUNT_ALLOWLIST if re.fullmatch(r"[A-Za-z0-9._\-]+", n)}
    for name in sorted(listed):
        for form in (f"/home/{name}/x", f"/Users/{name.upper()}/x", f"/home/{name}.", f"home/{name}"):
            assert _text(form) == form, form
    assert _text("/home/.../x") == "/home/.../x"  # dots only
    longer = f"/home/user{NAME}/x"
    assert _text(longer) != longer  # a generic prefix of a longer name is not one


def test_a_value_output_redacts_strings_member_names_and_their_lex_copies():
    """A non-string output: member names and strings, an object with a $-name ($lit), a lone surrogate ($utf16), and
    ext.lex's source-order list, all hold the label; the redacted pointers follow the encoder."""
    surrogate = f"/home/{NAME}/\ud800"
    output = {"b": surrogate, f"/home/{NAME}/z": [f"/home/{NAME}/a"], "a": {"$k": f"/Users/{NAME}"}}
    m = _map(_cell("true", output))
    result = _result(m)
    dumped = json.dumps(result)
    assert NAME not in dumped and "acct-" in dumped
    value = result["parts"][0]["value"]
    (key,) = [k for k in value if k.startswith("/home/")]
    assert re.fullmatch(r"/home/acct-[0-9a-f]{12}/z", key)
    assert "$utf16" in value["b"]
    import base64

    decoded = base64.b64decode(value["b"]["$utf16"]).decode("utf-16-be", "surrogatepass")
    assert NAME not in decoded and decoded.endswith("/\ud800")
    escaped = key.replace("~", "~0").replace("/", "~1")
    pointers = [entry["p"] for entry in result["ext"]["credleak"]["redacted"]]
    assert sorted(pointers) == sorted(["/parts/0/value/" + escaped, f"/parts/0/value/{escaped}/0",
                                       "/parts/0/value/a/$lit/$k", "/parts/0/value/b"])
    assert result["ext"]["lex"]["ord"]["/parts/0/value"] == ["b", key, "a"]  # the source order, redacted
    assert all(result["evf"][p] == "D" for p in pointers)
    (issue,) = [i for i in m.issues if i["code"] == ISSUE]
    assert issue["detail"] == "4"


def test_the_archived_profile_version_1_copies_tool_output_verbatim():
    m = _map(_cell("true", f"/home/{NAME}/x"), profile_version=1, sem=False, prov=False)
    assert NAME in _result(m)["parts"][0]["text"] and ISSUE not in m.codes()


def test_the_rule_grammar_is_closed():
    good = {"id": "r", "scope": "tool_output", "pattern": "x", "replacement": "acct-{span12}"}
    assert parse_redact_rules([good], "t")[0].id == "r"
    for bad in ({**good, "extra": 1}, {**good, "scope": "model_id"}, {**good, "pattern": "x*"}, {**good, "pattern": "("},
                {**good, "replacement": "{other}"}, {**good, "replacement": "{leaf}"}, {**good, "replacement": "a}"},
                {**good, "id": "R"}, {**good, "replacement": ""}):
        with pytest.raises(ProfileError):
            parse_redact_rules([bad], "t")
    with pytest.raises(ProfileError, match="unique"):
        parse_redact_rules([good, good], "t")


def test_one_label_for_two_spans_is_a_profile_defect():
    rules = parse_redact_rules([{"id": "r", "scope": "tool_output", "pattern": "(?<=home/)[a-z]+", "replacement": "acct"}],
                               "t")
    redactor = Redactor("p", 1, rules)
    redactor.text(f"/home/{NAME}x")
    with pytest.raises(ProfileError, match="one label"):
        redactor.text(f"/home/{OTHER}")
    clash = Redactor("p", 1, parse_redact_rules([{"id": "r", "scope": "tool_output", "pattern": "(?<=home/)[0-9]",
                                                    "replacement": "acct-{span12}"}], "t"))
    with pytest.raises(ProfileError, match="member names"):
        clash.tool_output({"home/1": 1, "home/" + clash.text("home/1")[0].removeprefix("home/"): 2}, "/v")


# ------------------------------------------------------------------------------------------------ D-605 parts 2 and 1
def _shipped_ls_rules():
    profile = load_profile("credleak-p15b")
    return [r for r in profile.family_table()["redact"] if r["id"].startswith("ls_long_")]


def _ls_redactor(name: str) -> Redactor:
    """The shipped ls -l patterns with a labels list naming the made-up ``name`` (as the real profile lists account #1)."""
    import hashlib

    label = hashlib.sha256(f"credleak-p15b\0{name}".encode()).hexdigest()[:12]
    entries = [{**dict(r), "labels": [label]} for r in _shipped_ls_rules()]
    return Redactor("credleak-p15b", 2, parse_redact_rules(entries, "test"))


def _ls(owner: str, group: str, *, mode: str = "-rw-r--r--") -> str:
    return f"total 8\n{mode}  1 {owner} {group}  120 Jun 11 08:00 a.txt\ndrwxr-xr-x@ 3 {owner}  {group}   96 Jun 11 b\n"


def test_a_listed_account_is_redacted_in_the_ls_long_owner_and_group_columns_only():
    redactor = _ls_redactor(NAME)
    out, rid = redactor.text(_ls(NAME, NAME))
    assert NAME not in out and rid == "ls_long_owner"
    assert redactor.text(f"/home/{NAME}")[0] == f"/home/{NAME}"  # no path rule in this redactor
    lines = out.splitlines()
    assert lines[0] == "total 8"
    assert re.fullmatch(r"-rw-r--r--  1 acct-[0-9a-f]{12} acct-[0-9a-f]{12}  120 Jun 11 08:00 a\.txt", lines[1])
    assert lines[1].split()[2] == lines[1].split()[3] == lines[2].split()[2]  # one salted label per account
    assert lines[1].split()[2] == _text(f"/home/{NAME}").removeprefix("/home/")  # the path rule's label


def test_an_unlisted_owner_or_group_is_never_touched():
    redactor = _ls_redactor(NAME)
    for value in (_ls(OTHER, "staff"), _ls("root", "wheel"), _ls("www-data", OTHER)):
        assert redactor.text(value) == (value, None)
    mixed = redactor.text(_ls(OTHER, NAME))[0]
    assert OTHER in mixed and NAME not in mixed  # only the listed group column
    # not an ls -l column: the bare name elsewhere is left as it is (the rule is structural)
    for value in (f"{NAME}\n", f"uid=1000({NAME})", f"hello {NAME} there", f"x -rw-r--r-- 1 {NAME} {NAME} 1 a"):
        assert redactor.text(value)[0] == value


def test_the_shipped_ls_rules_list_only_labels_and_touch_no_made_up_owner():
    rules = _shipped_ls_rules()
    assert {r["id"] for r in rules} == {"ls_long_owner", "ls_long_group"}
    for r in rules:
        assert r["labels"] and all(re.fullmatch(r"[0-9a-f]{12}", x) for x in r["labels"])
    value = _ls(NAME, OTHER) + _ls("root", "root")
    assert _redactor().text(value)[0] == value  # collateral 0: an unlisted account is kept


def test_a_labelled_rule_needs_a_span_group_and_well_formed_labels():
    base = {"id": "r", "scope": "tool_output", "pattern": "(?P<span>[a-z]+)", "replacement": "acct-{span12}"}
    assert parse_redact_rules([{**base, "labels": ["0" * 12]}], "t")[0].labels == frozenset({"0" * 12})
    for bad in ({**base, "pattern": "[a-z]+", "labels": ["0" * 12]}, {**base, "labels": []}, {**base, "labels": ["0" * 11]},
                {**base, "labels": ["A" * 12]}, {**base, "labels": ["0" * 12, "0" * 12]}, {**base, "labels": "0" * 12}):
        with pytest.raises(ProfileError):
            parse_redact_rules([bad], "t")


def _policy():
    from agentprov.corpus.withhold import policy_of_profile

    data = (support.REPO / "src/agentprov/adapters/credleak/profiles/credleak-p15b.profile.toml").read_bytes()
    return policy_of_profile(data, profile_id="credleak-p15b", profile_version=2)


def test_the_account_path_withhold_rules_hit_paths_but_never_a_redaction_label():
    """D-605 part 1: generic structural rules; the name class leaves out '-', so an acct- label never matches."""
    from agentprov.corpus.withhold import scan_chunks

    rules = [r for r in _policy().rules if r.id.startswith("account-path")]
    assert {(r.id, r.scope, r.reason) for r in rules} == {("account-path-home", "object", "personal_data"),
                                                        ("account-path-users", "object", "personal_data")}
    for value in (f"/home/{NAME}/x", f"cd home/{NAME} ", f'"/Users/{NAME}"', "/home/ubuntu/x"):  # generic names too
        assert scan_chunks([value.encode()], rules), value
    labelled = _text(f"/home/{NAME}/x and /Users/{NAME}/y")
    assert "acct-" in labelled and scan_chunks([labelled.encode()], rules) == frozenset()
    m = _map(_cell("true", f"/home/{NAME}/x\n"), sem=False, prov=False)
    # the tool output is redacted; the assistant text of _cell still names the path (model-authored): a derived hit
    assert scan_chunks([_result(m)["parts"][0]["text"].encode()], rules) == frozenset()
    assert scan_chunks([m.data], rules)
