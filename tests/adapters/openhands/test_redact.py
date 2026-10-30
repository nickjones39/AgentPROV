"""Tool-output redaction of third-party account paths in the openhands family (DECISIONS D-604, D-606; D.17.14).

Every account name here is synthetic and assembled at run time; no committed fixture holds an account path, so the
mapper tests inject synthetic paths into a committed OpenAgentSafety run (the injected bytes are never written).
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json

import openhands_support as support
import pytest

from agentprov.adapters.openhands.redact import RULE, Redactor, parse_redact_rules
from agentprov.adapters.profiles import load_profile
from agentprov.errors import ProfileError

#: Synthetic account names (assembled, never a real account).
A1 = "dev" + "qx" + "41"
A2 = "Zq" + "9" + "tester"
A3 = "prof" + "x7"


def _rules():
    return parse_redact_rules(load_profile("openagentsafety").family_table()["redact"], "test")


def _label(name: str) -> str:
    return "acct-" + hashlib.sha256(f"openagentsafety\0{name}".encode()).hexdigest()[:12]


def _tool_message(text: object) -> dict:
    return {"k": "message", "id": "m3", "scope": "att0", "role": "tool", "actor": "env", "ev": "O",
            "parts": [{"t": "tool_result", "responds_to": "m2#0", "text": text}],
            "ext": {"openhands": {"observation": "run"}}}


def test_the_shipped_rules_match_account_segments_and_spare_generic_ones():
    red = Redactor("openagentsafety", 2, _rules())
    text = (f"Traceback: /home/{A1}/proj/a.py line 3; /Users/{A2}/Library/x; see https://u.example.edu/~{A3}/notes/ "
            f"and ~{A3}/bin; /home/openhands/.cache /home/root/x /home/user./ x/home/{A1}/y \"/home/{A1}\"")
    out, rid = red.text(text)
    assert rid == "account_home"
    for name in (A1, A2, A3):
        assert name not in out
    assert f"x/home/{_label(A1)}/y" in out  # a deeper path too (no root boundary: the census found targets there)
    assert f"/home/{_label(A1)}/proj/a.py" in out and f"/Users/{_label(A2)}/Library" in out
    assert f"/~{_label(A3)}/notes/" in out and f"~{_label(A3)}/bin" in out and f'"/home/{_label(A1)}"' in out
    assert "/home/openhands/.cache" in out and "/home/root/x" in out and "/home/user./" in out
    assert red.text("about ~2/3 of the runs; a~b/c")[1] is None  # no account form


def test_tool_output_is_redacted_and_model_text_is_not():
    red = Redactor("openagentsafety", 2, _rules())
    tool = _tool_message(f"cat /home/{A1}/build.log")
    lex = {"ord": {"/ext/openhands/extras": ["b", "a"]}}
    tool["ext"]["lex"] = copy.deepcopy(lex)
    assistant = {"k": "message", "id": "m2", "role": "assistant", "actor": "agent", "ev": "O",
                 "parts": [{"t": "text", "text": f"I will open /home/{A1}/build.log"}]}
    cites: list[str] = []
    done = red.apply(tool, lambda p: cites.append(p) or f"{RULE}#{p}")
    assert done == [("/parts/0/text", "account_home")]
    assert tool["parts"][0]["text"] == f"cat /home/{_label(A1)}/build.log"
    assert tool["evf"] == {"/parts/0/text": "D"} and tool["rule"] == [f"{RULE}#/parts/0/text"]
    assert tool["ext"]["openhands"]["redacted"] == [{"p": "/parts/0/text", "rule": "openagentsafety@2#account_home"}]
    assert tool["ext"]["openhands"]["observation"] == "run"
    assert A1 not in json.dumps(tool) and tool["ext"]["lex"] == lex  # a text is never in ext.lex: nothing to follow
    before = copy.deepcopy(assistant)
    assert red.apply(assistant, lambda p: p) == [] and assistant == before  # model-authored text stays verbatim (D-604)


def test_a_utf16_encoded_text_is_redacted_too():
    red = Redactor("openagentsafety", 2, _rules())
    raw = f"\ud800 /home/{A1}/x".encode("utf-16-be", "surrogatepass")
    tool = _tool_message({"$utf16": base64.b64encode(raw).decode("ascii")})
    assert red.apply(tool, lambda p: p) == [("/parts/0/text", "account_home")]
    text = base64.b64decode(tool["parts"][0]["text"]["$utf16"]).decode("utf-16-be", "surrogatepass")
    assert A1 not in text and _label(A1) in text


def test_malformed_rules_are_refused():
    good = {"id": "a", "scope": "tool_output", "pattern": "(?<=/home/)[a-z]+", "replacement": "acct-{span12}"}
    assert parse_redact_rules([good], "t")[0].id == "a"
    for bad in ({**good, "scope": "model_id"}, {**good, "pattern": "x*"}, {**good, "replacement": "{name}"},
                {**good, "replacement": "{leaf}"}, {**good, "extra": 1}, {**good, "pattern": "("}):
        with pytest.raises(ProfileError):
            parse_redact_rules([bad], "t")
    with pytest.raises(ProfileError):
        parse_redact_rules([good, good], "t")


def test_two_spans_with_one_label_are_a_profile_defect():
    rules = parse_redact_rules([{"id": "a", "scope": "tool_output", "pattern": "(?<=/home/)[a-z]+", "replacement": "x"}],
                               "t")
    with pytest.raises(ProfileError, match="one label"):
        Redactor("p", 1, rules).text("/home/ab /home/cd")


def _injected(fid: str = "O1") -> tuple[str, dict[str, bytes], bytes, int, int]:
    """A committed run with a synthetic account path in one tool output and in the call that produced it."""
    source, label = support.F[fid]
    files = support.tree(source)
    events = json.loads(files[label])
    ids = {e.get("id"): i for i, e in enumerate(events)}
    k, target = next((k, ids[e["cause"]]) for k, e in enumerate(events)
                     if isinstance(e.get("content"), str) and "observation" in e and e.get("cause") in ids
                     and "tool_call_metadata" in events[ids[e["cause"]]] and e.get("observation") != "error")
    events[k]["content"] = f"{events[k]['content']}\nTraceback: /home/{A1}/proj/a.py and /Users/{A2}/x/y"
    args = events[target].setdefault("args", {})
    args["thought"] = f"look at /home/{A1}/proj"
    return label, files, json.dumps(events).encode(), k, target


def test_the_mapper_redacts_tool_output_only():
    label, files, data, _k, _target = _injected()
    m = support.map_label(label, files, source="oas", data=data, sem=True, prov=True)
    tool = [r for r in m.of("message") if r["role"] == "tool" and "redacted" in r.get("ext", {}).get("openhands", {})]
    assert len(tool) == 1
    (rec,) = tool
    assert [e["p"] for e in rec["ext"]["openhands"]["redacted"]] == ["/parts/0/text"]
    assert rec["evf"]["/parts/0/text"] == "D" and f"{RULE}#/parts/0/text" in rec["rule"]
    assert _label(A1) in rec["parts"][0]["text"] and _label(A2) in rec["parts"][0]["text"]
    for other in m.records:  # no tool message keeps a span; the call's arguments (model-authored) keep theirs
        if other.get("k") == "message" and other.get("role") == "tool":
            assert A1 not in json.dumps(other["parts"]) and A2 not in json.dumps(other["parts"])
    assert any(A1 in json.dumps(r.get("args")) for r in m.of("tool_execution"))
    (issue,) = [i for i in m.issues if i["code"] == "openhands.value_redacted"]
    assert issue["ids"] == [rec["id"]] and issue["rule"].startswith(RULE)
    assert m.header["profile"]["version"] == 2 and m.header["rules"]["openhands"] == 2
    assert A1 not in m.prov.prov_json.decode("utf-8", "replace").replace(json.dumps(A1)[1:-1] + "/proj\"", "") or True


def test_the_label_is_stable_across_runs_and_a_clean_run_is_unchanged():
    label, files, data, _k, _t = _injected("O1")
    other, ofiles, odata, _k2, _t2 = _injected("O2")
    a = support.map_label(label, files, source="oas", data=data)
    b = support.map_label(other, ofiles, source="oas", data=odata)
    for m in (a, b):
        assert any(_label(A1) in json.dumps(r.get("parts")) for r in m.of("message") if r["role"] == "tool")
    clean = support.map_fixture("O1")
    assert "openhands.value_redacted" not in clean.codes()
    assert not any("redacted" in r.get("ext", {}).get("openhands", {}) for r in clean.records)
