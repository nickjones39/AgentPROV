"""A source-profile ``[withhold]`` policy on synthetic fixtures with fake canaries (D-146's planted canary credentials;
HL H.4.5; G.9.4, G.9.5; D-234..D-236).

No real source is profiled here. The first shipped profile that declares a ``[withhold]`` table, ``credleak-p15b``
(phase 10k, D-265), has the real end-to-end chain with no injection in ``tests/adapters/credleak/test_withhold_e2e.py``
(D-234); the tests below keep the injection for the cases a shipped profile cannot show (a corpus sealed without the
policy, triage of a scan finding). A release-mode import reloads its profile by id in
the T1 worker, so the policy is injected where every reader takes it from:
``agentprov.corpus.withhold.policy_of_profile`` (sealing, ``verify --level chain`` and the deposit builder all call it).

Two synthetic AgentDojo logs are imported (release mode); one tool output carries a fake AWS-style canary assembled at
run time. Checked:

* sealed under the policy, the canary's object and execution are withheld (basis ``profile_rule``, finding = rule id and
  fingerprint, never the match), ``chain`` passes in release mode, and no sealed or deposited byte holds the canary;
* the backstop: a corpus sealed **without** the policy fails ``chain`` (``withheld.rule_hit``) and the deposit builder
  refuses it (``release.refused.withhold_rule``); a release-scan finding of a rule the policy's ``scan_rules`` names
  refuses the deposit unless triaged ``false-positive``, so a missed canary never passes as ``synthetic-benchmark``;
* the profile's ``public_note`` reaches the datasheet escaped (D-160..D-163), and the dry run withholds nothing on disk.
"""

from __future__ import annotations

import hashlib
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

#: A fake canary credential (assembled at run time; never printed). The pattern below matches it.
CANARY = "AKIA" + "QZXVCANARY" + "7351904826"
NOTE = "planted <b>canary</b> | credential (benchmark design); value never recorded"
POLICY = f'''
[withhold]
reason = "secret"
public_note = "{NOTE}"
scan_rules = ["aws-access-token"]

[[withhold.rules]]
id = "canary-key"
pattern = "AKIA[0-9A-Z]{{20}}"
'''


def _canary_hits(data: bytes) -> int:
    return sum(1 for i in range(len(CANARY) - 7) if CANARY[i:i + 8].encode() in data)


def _policy() -> Any:
    import seal_support as ss

    from agentprov.corpus.withhold import parse_policy

    return parse_policy(tomllib.loads(POLICY), profile_id="agentdojo-upstream", profile_version=2,
                        profile_sha256="sha256:" + hashlib.sha256(ss.source_profile()).hexdigest())


@pytest.fixture
def with_policy(monkeypatch: pytest.MonkeyPatch) -> Any:
    from agentprov.corpus import withhold

    policy = _policy()
    monkeypatch.setattr(withhold, "policy_of_profile",
                        lambda data, *, profile_id, profile_version: policy if profile_id == "agentdojo-upstream" else None)
    return policy


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    import agentdojo_support as ad
    import withheld_harness as wh

    base = tmp_path_factory.mktemp("canary")
    inp = base / "in"
    planted = ad.base_log()
    planted["messages"][3]["content"] = f"aws_access_key_id = {CANARY}"
    clean = ad.base_log(user_task_id="user_task_2")
    for doc in (planted, clean):
        path = inp / ad.path_of(doc)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ad.log_bytes(doc))
    assert wh._import(inp, base / "c").exit_code == 0
    sha = hashlib.sha256((inp / ad.path_of(planted)).read_bytes()).hexdigest()
    return {"partial": base / "c.partial", "sha": sha}


@pytest.fixture
def working(working_template: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    partial = tmp_path / "c.partial"
    shutil.copytree(working_template["partial"], partial, symlinks=True)
    return {**working_template, "root": tmp_path / "c", "partial": partial}


def _seal(working: dict[str, Any], **kwargs: Any) -> Any:
    import seal_support as ss

    from agentprov.corpus.package import ReleaseArgs, seal

    return seal(working["root"], corpus_version="0.1.0", inputs=ss.inputs(), release=ReleaseArgs(release_date="2026-10-12"),
                **kwargs)


def test_the_policy_withholds_the_canary_and_the_corpus_verifies_in_release_mode(cli, working, with_policy, tmp_path):
    import release_support as rs

    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_objects"] == 1 and report.counters["withheld_executions"] == 1
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    (entry,) = document.entries
    assert entry.sha256 == working["sha"] and (entry.reason, entry.basis) == ("secret", "profile_rule")
    assert entry.finding is not None and entry.finding.rule == "agentdojo-upstream@2:canary-key"
    assert entry.finding.fingerprint.endswith(":canary-key") and entry.decided_on == "2026-10-12"
    assert [p.to_json()["rules"] for p in document.policies] == [[{"id": "canary-key", "kind": "pattern",
                                                                   "scope": "executions"}]]
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
    holding = {p.relative_to(root).as_posix(): n for p in root.rglob("*") if p.is_file()
               and (n := _canary_hits(p.read_bytes()))}
    assert holding == {}  # names and counts only
    assert any(_canary_hits(p.read_bytes()) for p in root.with_name("c.withheld").rglob("*") if p.is_file())
    rs.build([root], tmp_path / "deposit")
    assert not any(_canary_hits(p.read_bytes()) for p in (tmp_path / "deposit").rglob("*") if p.is_file())


def test_the_public_note_reaches_the_datasheet_escaped(working, with_policy):
    _seal(working)
    text = (working["root"] / "DATASHEET.md").read_text("utf-8")
    line = next(line for line in text.splitlines() if line.startswith("| secret |"))
    assert "&lt;b>canary&lt;/b>" in line and "\\|" in line and "<b>" not in text
    assert "a withholding rule of the source profile matched" in line


def test_a_dry_run_reports_the_counts_and_moves_nothing(working, with_policy):
    before = {p.relative_to(working["partial"]).as_posix() for p in working["partial"].rglob("*")}
    report = _seal(working, dry_run=True)
    assert report.dry_run and report.root_digest is None and report.counters["withheld_objects"] == 1
    assert {p.relative_to(working["partial"]).as_posix() for p in working["partial"].rglob("*")} == before
    assert not working["root"].with_name("c.withheld").exists()


def test_a_corpus_sealed_without_the_policy_fails_the_chain_backstop_and_the_deposit(cli, working, monkeypatch, tmp_path):
    import release_support as rs

    from agentprov.corpus import withhold
    from agentprov.release.builder import DepositRefusedError

    report = _seal(working)  # no policy: the canary is released
    assert "withheld_objects" not in report.counters
    policy = _policy()
    monkeypatch.setattr(withhold, "policy_of_profile", lambda data, *, profile_id, profile_version: policy)
    root = working["root"]
    run = verify(cli, root, "--level", "chain")
    found = run.codes()
    assert run.code == 1 and set(found) == {"withheld.rule_hit"} and found["withheld.rule_hit"] >= 2  # raw and AER
    assert _canary_hits((run.out + run.err).encode()) == 0
    with pytest.raises(DepositRefusedError) as refused:
        rs.build([root], tmp_path / "deposit")
    assert refused.value.code == "release.refused.withhold_rule" and refused.value.exit_code == 4
    assert not (tmp_path / "deposit").exists()


@pytest.mark.parametrize(("triage", "refused"), [("synthetic-benchmark", True), ("real", True), ("false-positive", False)])
def test_a_scan_finding_of_a_policy_rule_must_be_a_false_positive(cli, working, with_policy, tmp_path, triage, refused):
    import release_support as rs

    from agentprov.release.metadata import ScanRefusedError

    _seal(working)
    root = working["root"]

    def scan(path: Path, digest: str) -> dict[str, Any]:
        finding = {"detector": "gitleaks", "fingerprint": "DATASHEET.md:aws-access-token:1", "line": 1,
                   "path": "DATASHEET.md", "reason": "test triage", "rule": "aws-access-token", "triage": triage}
        return rs.scan_document(path, digest, [finding])

    if not refused:
        rs.build([root], tmp_path / "deposit", scan=scan)
        return
    with pytest.raises(ScanRefusedError) as error:
        rs.build([root], tmp_path / "deposit", scan=scan)
    expected = "release.refused.scan_real" if triage == "real" else "release.refused.withhold_scan"
    assert error.value.code == expected


def test_withheld_json_never_holds_the_canary(working, with_policy):
    _seal(working)
    data = (working["root"] / "WITHHELD.json").read_bytes()
    assert _canary_hits(data) == 0
    assert b"AKIA[0-9A-Z]" not in data  # the pattern stays in the profile, the ledger records rule ids
    assert json.loads(data)["policies"][0]["profile"]["id"] == "agentdojo-upstream"
