"""D-601 (bug pass bugpass-perf-10, 2026-10-21; user decision 2026-10-21): WhistleBench redaction and withholding.

* ``redact.HARNESS_POINTERS`` gains the bench actor's ``/code/repo`` (the mapper copies ``eval.revision.origin`` there)
  and the run scope's ``/ext/inspect/error_retries`` (earlier attempts' errors with their tracebacks);
* a ``harness_text`` rule may narrow itself with ``pointers``;
* the shipped ``whistlebench@2`` profile redacts the clone URL's userinfo with a literal (no digest of a credential) and
  the account segment of ``error_retries`` tracebacks with a salted label, never the logger events, which quote the
  model's tool arguments, and never content;
* its ``[withhold]`` rule hits the token shape at object scope.

Synthetic values only: the token-shaped value is assembled at run time; the account is made up.
"""

from __future__ import annotations

import json
from typing import Any

import inspect_support as support
import pytest

from agentprov.adapters.inspect.redact import HARNESS_POINTERS, Redactor, parse_redact_rules
from agentprov.adapters.profiles import load_profile
from agentprov.errors import ProfileError

TOKEN = "gh" + "p_" + "Synth1" * 6
OTHER = "gh" + "o_" + "Synth2" * 6
ACCOUNT = "made-up-home-3"
SCENARIO = "scenario-person"  # a home directory inside the benchmark's scenario (content, never redacted)
ORIGIN = f"https://x-access-token:{TOKEN}@github.com/legobridge/whistlebench.git"
USERINFO = {"id": "origin_userinfo", "scope": "harness_text", "pattern": r'(?<=://)[^/@\s"]{1,256}(?=@)',
            "replacement": "redacted", "pointers": ["/ext/inspect/revision", "/code/repo"]}
ACCOUNT_RULE = {"id": "retry_account", "scope": "harness_text", "pattern": r"(?<=/Users/)[^/\s\"'<>\\]{1,64}(?=/)",
                "replacement": "<account:{span12}>", "pointers": ["/ext/inspect/error_retries"]}


def _cite(pointer: str) -> str:
    return "inspect.value_redacted@1#" + pointer


# ------------------------------------------------------------------------------------------------ the module
def test_the_harness_pointers_cover_code_repo_and_error_retries():
    assert "/code/repo" in HARNESS_POINTERS["actor"]
    assert "/ext/inspect/error_retries" in HARNESS_POINTERS["scope"]


def test_code_repo_and_revision_userinfo_are_redacted_with_a_literal():
    redactor = Redactor("p", 2, parse_redact_rules([USERINFO], "p"), [])
    bench = {"k": "actor", "id": "bench", "code": {"repo": ORIGIN, "commit": "0" * 40},
             "ext": {"inspect": {"revision": {"type": "git", "origin": ORIGIN}}}}
    done = redactor.apply(bench, _cite)
    assert sorted(p for p, _ in done) == ["/code/repo", "/ext/inspect/revision/origin"]
    assert TOKEN not in json.dumps(bench)
    assert bench["code"]["repo"] == "https://redacted@github.com/legobridge/whistlebench.git"
    assert bench["evf"] == {"/code/repo": "D", "/ext/inspect/revision/origin": "D"}


def test_a_literal_label_admits_one_span_per_unit():
    """Two distinct credentials in one unit under a literal label fail the unit closed (D.9.12), never collapse."""
    redactor = Redactor("p", 2, parse_redact_rules([USERINFO], "p"), [])
    bench = {"k": "actor", "id": "bench", "code": {"repo": ORIGIN},
             "ext": {"inspect": {"revision": {"origin": ORIGIN.replace(TOKEN, OTHER)}}}}
    with pytest.raises(ProfileError, match="one label to two different spans"):
        redactor.apply(bench, _cite)


def test_error_retries_tracebacks_get_a_salted_label_and_a_narrowed_rule_stays_in_its_pointers():
    redactor = Redactor("p", 2, parse_redact_rules([ACCOUNT_RULE], "p"), [])
    trace = f'File "/Users/{ACCOUNT}/work/run.py", line 3'
    run = {"k": "scope", "id": "run",
           "ext": {"inspect": {"error_retries": [{"traceback": trace, "traceback_ansi": trace}],
                               "error": {"traceback": trace}}}}
    done = redactor.apply(run, _cite)
    assert sorted(p for p, _ in done) == ["/ext/inspect/error_retries/0/traceback",
                                          "/ext/inspect/error_retries/0/traceback_ansi"]
    retry = run["ext"]["inspect"]["error_retries"][0]
    assert ACCOUNT not in json.dumps(retry) and retry["traceback"] == retry["traceback_ansi"]
    assert retry["traceback"].startswith('File "/Users/<account:') and retry["traceback"].endswith('>/work/run.py", line 3')
    assert run["ext"]["inspect"]["error"]["traceback"] == trace  # outside the rule's pointers
    again = dict(run)
    assert redactor.apply(again, _cite) == []  # a label is not matched again


@pytest.mark.parametrize("pointers", [[], "/code/repo", ["/messages"], ["/code"], ["/code/repo", "/code/repo"], [3]])
def test_malformed_pointers_are_refused(pointers: Any):
    with pytest.raises(ProfileError, match="pointers"):
        parse_redact_rules([{**USERINFO, "pointers": pointers}], "p")


def test_pointers_are_refused_on_a_model_id_rule():
    with pytest.raises(ProfileError, match="pointers"):
        parse_redact_rules([{"id": "m", "scope": "model_id", "pattern": "x", "replacement": "y", "pointers": ["/params"]}],
                           "p")


# ------------------------------------------------------------------------------------------------ the shipped profile
def _log(tmp_path) -> support.Imported:
    header = support.synthetic_header("0.3.130")
    header["eval"]["revision"] = {"type": "git", "origin": ORIGIN, "commit": "9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc",
                                  "dirty": False}
    trace = f'Traceback (most recent call last):\n  File "/Users/{ACCOUNT}/work/run.py", line 3\nTimeoutError: x'

    def tune(s: support.Sample, sample: dict[str, Any]) -> None:
        sample["error_retries"] = [{"message": "TimeoutError: x", "traceback": trace, "traceback_ansi": trace}]
        # a logger event quoting the model's tool arguments (as _call_tools.py logs them): harness text, but not a
        # pointer the profile's rules name, so it stays verbatim (D-604)
        sample["events"].append({"uuid": "E-log", "span_id": "SpanGenerate0000000000", "timestamp": support.ts(6.0),
                                 "working_start": 6.0, "event": "logger",
                                 "message": {"level": "info", "message": f"write_file /Users/{SCENARIO}/memo.txt",
                                             "created": 1.0, "filename": "_call_tools.py", "module": "_call_tools",
                                             "lineno": 1}})
        for m in sample["messages"]:
            if m["role"] == "assistant" and m["content"] == "Synthetic final answer.":
                m["content"] = f"I saved /Users/{SCENARIO}/memo.txt."  # model output: content
    sample = support.basic_sample(tune=tune)
    return support.import_log(support.build_eval(header, {"s1_epoch_1.json": sample}), tmp_path,
                              profile=load_profile("whistlebench"))


def test_the_shipped_profile_redacts_both_pointer_classes(tmp_path):
    imported = _log(tmp_path)
    (unit,) = imported.units
    assert not unit.outcome.degenerate and imported.register == []
    assert TOKEN.encode() not in unit.data and f"/Users/{ACCOUNT}/".encode() not in unit.data
    bench = next(r for r in unit.records if r["k"] == "actor" and r["id"] == "bench")
    assert bench["code"]["repo"] == "https://redacted@github.com/legobridge/whistlebench.git"
    assert bench["ext"]["inspect"]["revision"]["origin"] == bench["code"]["repo"]
    assert bench["evf"]["/code/repo"] == "D" and "inspect.value_redacted@1#/code/repo" in bench["rule"]
    assert {"p": "/code/repo", "rule": "whistlebench@2#origin_userinfo"} in bench["ext"]["inspect"]["redacted"]
    run = next(r for r in unit.records if r["k"] == "scope" and r["id"] == "run")
    pointer = "/ext/inspect/error_retries/0/traceback"
    assert run["evf"][pointer] == "D" and f"inspect.value_redacted@1#{pointer}" in run["rule"]
    assert {"p": pointer, "rule": "whistlebench@2#retry_account"} in run["ext"]["inspect"]["redacted"]
    issues = [i for i in unit.info.issues if i["code"] == "inspect.value_redacted"]
    assert len(issues) == 1 and set(issues[0]["ids"]) == {"bench", "run"}
    # the scenario's home directory stays verbatim in the logger event and in model output
    assert unit.data.count(f"/Users/{SCENARIO}/".encode()) >= 2


def test_the_label_is_stable_across_logs(tmp_path):
    labels = []
    for sub in ("a", "b"):
        (unit,) = _log(tmp_path / sub).units
        run = next(r for r in unit.records if r["k"] == "scope" and r["id"] == "run")
        labels.append(run["ext"]["inspect"]["error_retries"][0]["traceback"])
    assert labels[0] == labels[1]


def test_the_archived_version_1_leaves_both_classes_verbatim(tmp_path):
    """The recorded profile (version 1, D-31) has no rules: the gap D-601 closes."""
    header = support.synthetic_header("0.3.130")
    header["eval"]["revision"]["origin"] = ORIGIN
    imported = support.import_log(support.build_eval(header, {"s1_epoch_1.json": support.basic_sample()}), tmp_path,
                                  profile=load_profile("whistlebench", 1))
    assert TOKEN.encode() in imported.units[0].data


def test_the_withhold_rule_hits_the_token_shape_at_object_scope():
    from agentprov.corpus.withhold import policy_of_profile

    data = (support.REPO / "src/agentprov/adapters/inspect/profiles/whistlebench.profile.toml").read_bytes()
    policy = policy_of_profile(data, profile_id="whistlebench", profile_version=2)
    assert policy is not None and policy.ref == "whistlebench@2" and tuple(policy.scan_rules) == ("github-pat",)
    (rule,) = policy.rules
    assert (rule.id, rule.scope) == ("github-token-shape", "object")
    assert rule.hits(json.dumps({"origin": ORIGIN}).encode())
    assert not rule.hits(json.dumps({"origin": "https://github.com/legobridge/whistlebench.git"}).encode())
    assert not rule.hits(("gh" + "p_" + "short").encode())
