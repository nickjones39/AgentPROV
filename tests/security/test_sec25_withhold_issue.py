"""A source-profile ``[withhold]`` issue rule end to end (D-311; D-289 (c): withholding executions the source itself
flags; HL H.4.5; G.9.4, G.9.5; D-234..D-236).

Synthetic only: one Inspect ``.eval`` built in code (an archive container holding three sample members) is imported in
release mode under the survey AgentHarm profile, so flagged and unflagged executions come from one raw object. Sample
``s1`` carries the seal issue ``inspect.sample_limit`` (a real, declared code of the ``inspect`` catalogue, used here as a
stand-in for MCPHunt's ``mcphunt.canary_flagged``, which no shipped mapper emits yet) and a fake canary in its tool
output; ``s2`` and ``s3`` carry neither. No shipped profile declares an issue rule, so the policy is injected at
``agentprov.corpus.withhold.policy_of_profile`` as in ``test_sec25_withhold_policy.py`` (sealing, ``chain`` and the
deposit builder all read it there). Checked:

* sealed under an issue rule plus an object-scope pattern backstop, exactly the flagged execution leaves with its member
  object and (AD-12) the container; the unflagged two stay released; ``WITHHELD.json`` is ``agentprov-withheld/0.2`` with
  its schema copy; ``chain`` passes in release mode and the deposit builds; no sealed or deposited byte holds the canary;
* the backstop: a corpus sealed without the policy fails ``chain`` (``withheld.issue_released``, from the register and the
  AER seal) and the deposit builder refuses it (``release.refused.withhold_issue``);
* an issue code the corpus's catalogue does not declare refuses the seal (``corpus.withhold.policy``, exit 4);
* a policy without an issue rule seals ``agentprov-withheld/0.1`` with the 0.1 schema copy, as before D-311.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest
import verify_support as vs
from corpus_harness import verify

cli = harness.cli

#: A fake canary (assembled at run time; never printed). The backstop pattern below matches it.
CANARY = "CNRY" + "-" + "QZXV7351904826AB"
FLAG = "inspect.sample_limit"
ISSUE_RULE = f'''
[[withhold.rules]]
id = "canary-flagged"
issue = "{FLAG}"
'''
PATTERN_RULE = '''
[[withhold.rules]]
id = "canary-shape"
pattern = "CNRY-[0-9A-Z]{16}"
scope = "object"
'''
HEAD = '''
[withhold]
reason = "secret"
public_note = "the source flags a planted canary in this execution; value never recorded"
'''


def _hits(data: bytes) -> int:
    return sum(1 for i in range(len(CANARY) - 7) if CANARY[i:i + 8].encode() in data)


def _policy(text: str) -> Any:
    from agentprov.corpus.withhold import parse_policy

    return parse_policy(tomllib.loads(text), profile_id="agent-security-tools-survey", profile_version=1,
                        profile_sha256="sha256:" + "0" * 64)


def _inject(monkeypatch: pytest.MonkeyPatch, text: str) -> Any:
    from agentprov.corpus import withhold

    policy = _policy(text)
    monkeypatch.setattr(withhold, "policy_of_profile", lambda data, *, profile_id, profile_version: policy)
    return policy


def _flagged_sample() -> dict[str, Any]:
    import inspect_support as isp

    def tune(s: Any, sample: dict[str, Any]) -> None:
        sample["events"].append({"uuid": "E-limit", "span_id": "SpanGenerate0000000000", "timestamp": isp.ts(6.0),
                                 "working_start": 6.0, "event": "sample_limit", "type": "message",
                                 "message": "Synthetic limit.", "limit": 20.0})
        sample["limit"] = {"type": "message", "limit": 20}

    text = json.dumps(isp.basic_sample("s1", tune=tune)).replace("synthetic tool output", f"tool output {CANARY}")
    return json.loads(text)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    import import_support as support
    import inspect_support as isp

    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    base = tmp_path_factory.mktemp("issue")
    source = base / "in"
    (source / harness.INSPECT_LABEL).parent.mkdir(parents=True)
    samples = {"s1_epoch_1.json": _flagged_sample(), "s2_epoch_1.json": isp.basic_sample("s2"),
               "s3_epoch_1.json": isp.basic_sample("s3")}
    (source / harness.INSPECT_LABEL).write_bytes(isp.build_eval(isp.synthetic_header(), samples))
    pin = {"commit": support.SURVEY_COMMIT, "kind": "git", "repo": support.SURVEY, "role": "git", "tree": "agentharm/results"}
    with CorpusWriter(base / "c") as writer:
        report = import_source("agent-security-tools-survey", LocalTree(source), corpus=writer, part="agentharm",
                               mode="release", workers=1, pin=pin,
                               pin_check=support.vouch(source, repo=support.SURVEY, commit=support.SURVEY_COMMIT))
    assert report.counters["mapped"] == 3, report.counters
    partial = base / "c.partial"
    register = [json.loads(line) for line in (partial / "register.jsonl").read_text("utf-8").splitlines()]
    flagged = {e["subject"]["ex"] for e in register if e["code"] == "map." + FLAG}
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text("utf-8").splitlines()]
    assert len(rows) == 3 and len(flagged) == 1
    return {"partial": partial, "flagged": flagged.pop(), "all": {r["ex"] for r in rows}}


@pytest.fixture
def corpus(working_template: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import test_sec26_package as p26

    from agentprov.cli import package

    monkeypatch.setattr(package, "git_facts", lambda repo=package.REPO_ROOT: ("0" * 40, True))  # a clean producer tree
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: True)
    partial = tmp_path / "c.partial"
    shutil.copytree(working_template["partial"], partial, symlinks=True)
    spec, licence = p26._agentharm_spec(tmp_path, personas=False)  # an issue-rule test: no address rule (D-810)
    return {**working_template, "root": tmp_path / "c", "partial": partial, "spec": spec, "licence": licence}


def _package(cli: Any, corpus: dict[str, Any]) -> Any:
    import test_sec26_package as p26

    return p26._package(cli, corpus["root"], corpus["spec"], corpus["licence"])


def _codes(root: Path) -> list[str]:
    return [json.loads(line)["code"] for line in (root / "register.jsonl").read_text("utf-8").splitlines()]


def test_an_issue_rule_withholds_only_the_flagged_execution_of_one_raw_object(cli, corpus, monkeypatch, tmp_path):
    import release_support as rs

    from agentprov.corpus.withheld import decode_withheld

    _inject(monkeypatch, HEAD + ISSUE_RULE + PATTERN_RULE)
    run = _package(cli, corpus)
    assert run.code == 0, run.err
    root = corpus["root"]
    assert _hits((run.out + run.err).encode()) == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    assert document.format == "agentprov-withheld/0.2"
    assert (root / "schemas" / "withheld-0.2.schema.json").is_file()
    assert not (root / "schemas" / "withheld-0.1.schema.json").exists()
    assert set(document.execution_map) == {corpus["flagged"]}
    bases = sorted(e.basis for e in document.entries)
    assert bases == ["container", "profile_rule"]  # the flagged sample's member, and the .eval that holds it (AD-12)
    rule_entry = next(e for e in document.entries if e.basis == "profile_rule")
    assert rule_entry.affected_executions == (corpus["flagged"],) and rule_entry.reason == "secret"
    assert rule_entry.finding is not None and rule_entry.finding.rule.endswith(":canary-flagged")
    assert [r["kind"] for p in document.to_json()["policies"] for r in p["rules"]] == ["issue", "pattern"]
    released = {json.loads(line)["ex"] for line in (root / "executions.jsonl").read_text("utf-8").splitlines()}
    assert released == corpus["all"] - {corpus["flagged"]}  # one raw object, two executions still released
    codes = _codes(root)
    assert codes.count("release.withheld") == 1 and codes.count("map." + FLAG) == 1  # the register keeps the flag
    check = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert check.code == 0 and check.codes() == {}, check.codes()
    assert {p.relative_to(root).as_posix(): n for p in root.rglob("*") if p.is_file() and (n := _hits(p.read_bytes()))} == {}
    assert any(_hits(p.read_bytes()) for p in root.with_name("c.withheld").rglob("*") if p.is_file())
    rs.build([root], tmp_path / "deposit")
    assert not any(_hits(p.read_bytes()) for p in (tmp_path / "deposit").rglob("*") if p.is_file())


def test_a_corpus_sealed_without_the_issue_rule_fails_chain_and_the_deposit(cli, corpus, monkeypatch, tmp_path):
    import release_support as rs

    from agentprov.release.builder import DepositRefusedError

    run = _package(cli, corpus)  # no policy: the flagged execution is released
    assert run.code == 0, run.err
    root = corpus["root"]
    assert not (root / "WITHHELD.json").exists()
    _inject(monkeypatch, HEAD + ISSUE_RULE)
    check = verify(cli, root, "--level", "chain")
    assert check.code == 1 and check.codes() == {"withheld.issue_released": 1}, check.codes()
    assert corpus["flagged"] in check.out + check.err and _hits((check.out + check.err).encode()) == 0
    with pytest.raises(DepositRefusedError) as refused:
        rs.build([root], tmp_path / "deposit")
    assert refused.value.code == "release.refused.withhold_issue" and refused.value.exit_code == 4
    assert not (tmp_path / "deposit").exists()


def test_the_seal_code_alone_is_enough_for_the_chain_backstop(cli, corpus, monkeypatch):
    """``chain`` also reads the AER seal: with the code gone from the register and the index rows, the AER seal of the
    released execution still shows it."""
    run = _package(cli, corpus)
    assert run.code == 0, run.err
    root = corpus["root"]
    policy = _inject(monkeypatch, HEAD + ISSUE_RULE)
    from agentprov.corpus.withhold import issue_backstop

    seen: dict[str, Any] = {}

    def spy(policy_: Any, register: Any, rows: Any, seal_codes: Any = None) -> Any:
        from dataclasses import replace

        seen["seal_codes"] = dict(seal_codes or {})
        bare = [replace(row, issues=()) for row in rows]
        assert issue_backstop(policy_, [], bare) == []  # without the seal, nothing would be found
        return issue_backstop(policy_, [], bare, seal_codes)

    monkeypatch.setattr("agentprov.corpus.withhold.issue_backstop", spy)
    check = verify(cli, root, "--level", "chain")
    assert check.codes() == {"withheld.issue_released": 1}, check.codes()
    assert FLAG in seen["seal_codes"][corpus["flagged"]] and policy.issue_rules


def test_an_issue_code_the_catalogue_does_not_declare_refuses_the_seal(cli, corpus, monkeypatch):
    _inject(monkeypatch, HEAD + ISSUE_RULE.replace(FLAG, "inspect.no_such_code"))
    run = _package(cli, corpus)
    assert run.code == 4 and "withhold_policy" in run.err and "not declared" in run.err, run.err
    assert not corpus["root"].exists() and not corpus["root"].with_name("c.withheld").exists()


def test_a_policy_without_an_issue_rule_seals_the_0_1_ledger_as_before(cli, corpus, monkeypatch):
    from agentprov.corpus.withheld import decode_withheld

    _inject(monkeypatch, HEAD + PATTERN_RULE.replace('scope = "object"', 'scope = "executions"'))
    run = _package(cli, corpus)
    assert run.code == 0, run.err
    root = corpus["root"]
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    assert document.format == "agentprov-withheld/0.1" and json.loads((root / "WITHHELD.json").read_bytes())["format"] == \
        "agentprov-withheld/0.1"
    assert (root / "schemas" / "withheld-0.1.schema.json").is_file()
    assert not (root / "schemas" / "withheld-0.2.schema.json").exists()
    assert set(document.execution_map) == {corpus["flagged"]}  # only the flagged sample's member holds the canary


def test_bf20_recompute_and_rederive_of_a_corpus_that_withholds_report_unverified(cli, corpus, monkeypatch):
    """BF-20 (H.4.5(6)): re-deriving a sealed corpus that withholds an object its released executions need reports those
    outputs ``unverified``. Here the withheld container also holds the two released samples (AD-12). Nothing refuses
    with ``raw.object.missing``."""
    _inject(monkeypatch, HEAD + ISSUE_RULE)
    assert _package(cli, corpus).code == 0
    root = corpus["root"]
    run = cli("recompute", "--corpus", str(root), "--dry-run", "--json")
    assert run.code == 0 and "raw.object.missing" not in run.err + run.out, run.err
    counters = run.json()["counters"]
    assert counters["unverified"] == 2 and counters["withheld_unavailable"] >= 1, counters
    assert counters["failed"] == counters["unexplained_change"] == 0
    run = verify(cli, root, "--level", "rederive")
    assert run.code == 0 and "raw.object.missing" not in run.err + run.out, run.err
    assert run.json()["counters"].get("rederive_unverified") == 2
