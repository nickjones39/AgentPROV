"""The first shipped ``[withhold]`` profile, end to end with no injection (D-234; D-235, D-236; HL H.4.5; G.9.4-G.9.6).

D-234 asked the first shipped profile that declares ``[withhold]`` to replace the test injection at
``agentprov.corpus.withhold.policy_of_profile`` (``tests/security/test_sec25_withhold_policy.py``) with a real end-to-end
chain. Here the policy is read from the shipped ``credleak-p15b`` profile everywhere it is read (the T1 import worker,
sealing, ``verify --level chain`` and the deposit builder): nothing is monkeypatched.

The archive input is a deposit zip assembled at test time (never committed) in the layout of Zenodo 22737462: three
committed single-run fixture cells (unedited, no planted value) and two single-run cells generated here whose tool call
carries a test-made sentinel of the study's planted-credential shapes (the tag, an AWS-style key; assembled at run time,
never printed). A cell holds one run so that the current runner maps it as a whole file (multi-run cells wait for the
routed runner item R-10k-1). Checked:

* import (release mode, archive input with a Zenodo test pin) -> seal (release) withholds both sentinel cells (basis
  ``profile_rule``, scope ``object``), their two executions (a derived-file hit escalates, D-235) and the deposit zip
  (basis ``container``); the three clean executions stay released;
* ``verify --level chain --release`` passes on the sealed corpus (the D-236 backstop re-applies the profile's rules to
  every released file);
* no sealed or deposited byte holds a sentinel; the private sidecar does;
* the release secret scan (gitleaks, ``tools/release_scan.py``) finds nothing in the sealed corpus, while the same scan
  over the sidecar finds the AWS-style sentinel (the control); skipped when gitleaks is not installed.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "security", _TESTS / "corpus", _TESTS / "unit" / "release", _TESTS / "adapters",
              _TESTS.parent / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import credleak_support as support  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402

cli = harness.cli

PIN_FILE = "deposit.zip"
DOI = "10.5281/zenodo.1"
SPEC = f'''corpus_id = "credleak-test"
corpus_version = "0.1.0"
title = "Credential-leak cells with test-made sentinels (test corpus)"
mode = "import"

[[sources]]
source_id = "credleak-p15b"
profile = "credleak-p15b@2"
parts = ["head"]

[[sources.snapshots]]
snapshot_id = "head"
origin = {{ kind = "zenodo", doi = "{DOI}", file = "{PIN_FILE}" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["credleak.tools@2"]
prov_specs = ["agentprov-prov/0.1"]
views = []
options = {{ context_encoding = "members" }}

[licence]
derived = "inherit"
decided_by = "test"
files = ["LICENSE"]

[layout]
shard_depth = 1
'''
CARD = """---
mode: import
---

## Motivation

A test corpus of credential-leak cells.

## Composition

The corpus holds {v:/counts/executions} execution records.

## Maintenance

Test only.
"""
CHANGES = '''[[change]]
version = "0.1.0"
bump = "initial"
summary = "Test corpus."
'''
#: Test-made sentinels (never a deposited value): the study's tag inside a value, and an AWS-style key the release
#: scan's gitleaks rules recognise (16 base-32 characters after the prefix).
TAG = support.sentinel("tag")
AWS = "AK" + "IA" + "TESTSENTINELWXYZ"
SENTINELS = (TAG.encode(), AWS.encode())


#: A made-up workstation account (assembled at run time; never a deposited name) and the two D-605 cells.
ACCOUNT = "tst" + "acct" + "9"
ACCOUNT_LABELS = {
    "tool": "p15b-run-data/01-injection-map/T-CMD-command-output/test-model/run__TCMD__test-model__TCMD.8__2026-06-11T08-00-00-000Z.json",
    "model": "p15b-run-data/01-injection-map/T-CMD-command-output/test-model/run__TCMD__test-model__TCMD.9__2026-06-11T08-00-00-000Z.json",
}


def _account_cell(command: str, output: str, scenario: str) -> bytes:
    turn = {"turnNumber": 0, "userMessage": "do the task", "assistantResponse": "done",
            "toolCalls": [{"tool": "Bash", "input": {"command": command}, "output": output}],
            "timestamp": "2026-06-11T08:00:00.000Z"}
    return support.synthetic_cell(turns=[turn], scenario=scenario, technique="TCMD")


ACCOUNT_CELLS = {
    ACCOUNT_LABELS["tool"]: _account_cell("pwd", f"/home/{ACCOUNT}/project\n", "TCMD.8"),
    ACCOUNT_LABELS["model"]: _account_cell(f"cat /home/{ACCOUNT}/project/a.txt", "ok\n", "TCMD.9"),
}


def _holds(data: bytes) -> bool:
    return any(s in data for s in SENTINELS)


def _zip(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """The test deposit zip; returns its pin and the member labels of the sentinel cells -> their sha256."""
    members: dict[str, bytes] = {}
    for criterion in ("single_run_excluded", "single_run_roster"):
        for entry in [e for e in support.source_entries() if criterion in e["criteria"]]:
            members[entry["label"]] = support.cell_bytes(entry)
    assert len(members) == 3
    planted = {
        "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.8__2026-06-11T08-00-00-000Z.json":
            support.synthetic_cell(output=f"API_TOKEN={TAG}\n", scenario="T1.8", technique="T1"),
        "p15b-run-data/04-hygiene/output-T-EMIT/test-model/run__TEMIT__test-model__TEMIT.8__2026-06-11T08-00-00-000Z.json":
            support.synthetic_cell(output=f"aws_access_key_id = {AWS}\n", scenario="TEMIT.8", technique="TEMIT"),
    }
    members.update(planted)
    members["p15b-run-data/README.md"] = b"not selected\n"
    # a not-selected member whose label carries the tag between underscores, as two collector-log labels of the
    # deposit do: raw/members.jsonl lists it and is released, so the tag rule must spare it (found by part C2)
    members["p15b-run-data/03-egress-axis/external-canary-collector-log/EXTERNAL_" + "CAN" + "ARY" + "_VALIDITY.md"] = b"x\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in sorted(members.items()):
            zf.writestr(label, data)
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": DOI, "record": 1, "version": "v1", "file": path.name,
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return pin, {label: hashlib.sha256(raw).hexdigest() for label, raw in planted.items()}


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed credleak fixtures are absent")
    base = tmp_path_factory.mktemp("credleak-withhold")
    pin, planted = _zip(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(base / "c") as writer:
        report = import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                               workers=1, mode="release")
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 5 and report.counters["degenerate"] == 0
    return {"partial": base / "c.partial", "planted": planted, "container": pin["sha256"]}


@pytest.fixture
def working(working_template: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    partial = tmp_path / "c.partial"
    shutil.copytree(working_template["partial"], partial, symlinks=True)
    return {**working_template, "root": tmp_path / "c", "partial": partial}


def _inputs() -> Any:
    from importlib import resources

    from agentprov.adapters.registry.claims import CHECKER
    from agentprov.corpus.datasheet import load_statements
    from agentprov.corpus.package import LicenceFile, ProducerFacts, SealInputs

    package = resources.files("agentprov").joinpath("adapters", "credleak")
    node = package.joinpath("semantics", "credleak.tools-2")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", "credleak-p15b.profile.toml").read_bytes(),
        semantics_profiles={"credleak.tools@2": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
                                                 if c.is_file()}},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)")},
        producer=ProducerFacts(git_commit="0123456789abcdef0123456789abcdef01234567", git_tree_clean=True,
                               distributions_sha256="sha256:" + "0" * 64, zlib_version="1.2.12"),
        checker=CHECKER,
        registry_date="2026-10-11",
    )


def _seal(working: dict[str, Any], **kwargs: Any) -> Any:
    from agentprov.corpus.package import ReleaseArgs, seal

    return seal(working["root"], corpus_version="0.1.0", inputs=_inputs(), release=ReleaseArgs(release_date="2026-10-13"),
                **kwargs)


def _rows(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]


def test_the_shipped_profile_withholds_the_sentinel_cells_and_their_runs(cli, working):
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_objects"] == 3 and report.counters["withheld_executions"] == 2
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    by_sha = {e.sha256: e for e in document.entries}
    for sha in working["planted"].values():
        entry = by_sha[sha]
        assert (entry.reason, entry.basis) == ("secret", "profile_rule")
        assert entry.finding is not None and entry.finding.rule.startswith("credleak-p15b@2:")
    assert by_sha[working["container"]].basis == "container"
    assert [p.to_json()["rules"] for p in document.policies] == [[
        {"id": "account-path-home", "kind": "pattern", "scope": "object"},  # D-605 part 1 (no fixture cell hits it)
        {"id": "account-path-users", "kind": "pattern", "scope": "object"},
        {"id": "aws-key-shape", "kind": "pattern", "scope": "object"},
        {"id": "canary-tag", "kind": "pattern", "scope": "object"},
        {"id": "canary-tag-left", "kind": "pattern", "scope": "object"},
        {"id": "sk-key-shape", "kind": "pattern", "scope": "object"},
    ]]
    assert len(document.executions) == 2
    released = _rows(root)
    assert len(released) == 3  # the three clean single-run fixture cells
    assert not {r["source_key"].split("#", 1)[0].removeprefix("sha256:") for r in released} & set(working["planted"].values())
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_or_deposited_byte_holds_a_sentinel(working, tmp_path):
    import release_support as rs

    _seal(working)
    root = working["root"]
    holding = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and _holds(p.read_bytes()))
    assert holding == []  # names only
    sidecar = root.with_name("c.withheld")
    assert any(_holds(p.read_bytes()) for p in sidecar.rglob("*") if p.is_file())
    rs.build([root], tmp_path / "deposit")
    assert not any(_holds(p.read_bytes()) for p in (tmp_path / "deposit").rglob("*") if p.is_file())


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks (the G.9.4 release scanner) is not installed")
def test_the_release_secret_scan_finds_no_planted_value_in_the_sealed_corpus(working, tmp_path):
    import release_scan
    import release_support as rs

    from agentprov.adapters.profiles import load_profile

    scan_rules = set(load_profile("credleak-p15b").data["withhold"]["scan_rules"])
    _seal(working)
    root = working["root"]
    executable = str(shutil.which("gitleaks"))
    document = release_scan.scan(root, gitleaks=executable, needles={})
    assert [f for f in document["findings"] if f["rule"] in scan_rules] == []
    # the control: the same scanner over the private sidecar sees the withheld AWS-style sentinel
    control, _resolved = release_scan.run_gitleaks(executable, root.with_name("c.withheld"))
    assert any(f.rule == "aws-access-token" for f in control)
    rs.build([root], tmp_path / "deposit", scan=lambda path, digest: replace_root(document, digest))


def replace_root(document: dict[str, Any], digest: str) -> dict[str, Any]:
    """The scan document as the deposit builder reads it (bound to the corpus's root digest)."""
    assert document["target"]["root_digest"] == digest
    return document


def test_withheld_json_names_rule_ids_never_a_marker_or_match(working):
    _seal(working)
    data = (working["root"] / "WITHHELD.json").read_bytes()
    assert not _holds(data)
    assert b"AKIA[0-9A-Z]" not in data and b"[^_]" not in data  # the profile's rules stay in the profile
    assert json.loads(data)["policies"][0]["profile"]["id"] == "credleak-p15b"



@pytest.fixture
def account_working(tmp_path: Path) -> dict[str, Any]:
    """D-605: a deposit zip of the two account-path cells only (a made-up account in a tool's output, redacted in the
    AER, and one in a model-written command, kept verbatim, D-604), imported in release mode."""
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in sorted(ACCOUNT_CELLS.items()):
            zf.writestr(label, data)
    path = tmp_path / PIN_FILE
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": DOI, "record": 1, "version": "v1", "file": path.name,
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                               workers=1, mode="release")
    assert report.exit_code == 0 and report.counters["mapped"] == 2, report.counters
    return {"root": tmp_path / "c", "partial": tmp_path / "c.partial"}


def test_a_tool_output_account_path_is_redacted_and_the_model_authored_one_is_withheld(cli, account_working):
    """D-605 end to end (import -> seal -> verify --level chain --release), parts 1 and 2:

    * the tool-output run is released: its AER, SEM, PROV and views hold the salted label, never the made-up name, and
      the account-path rules (`personal_data`, object scope) never match the label;
    * both raw cells hold the path, so both are withheld at object scope (and the deposit zip as their container);
    * the model-written command keeps the path verbatim (D-604), so that run's derived files hit the rule and it is
      withheld through D-235;
    * no released byte holds the name; the private sidecar does."""
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(account_working)
    root = account_working["root"]
    digests = {kind: hashlib.sha256(ACCOUNT_CELLS[label]).hexdigest() for kind, label in ACCOUNT_LABELS.items()}
    assert report.counters["withheld_objects"] == 3 and report.counters["withheld_executions"] == 1
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    by_sha = {e.sha256: e for e in document.entries}
    for sha in digests.values():
        entry = by_sha[sha]
        assert (entry.reason, entry.basis) == ("personal_data", "profile_rule")
        assert entry.finding is not None and entry.finding.rule.startswith("credleak-p15b@2:account-path-")
    rows = {r["source_key"].split("#", 1)[0].removeprefix("sha256:"): r for r in _rows(root)}
    assert set(rows) == {digests["tool"]}  # the model-command run is withheld, the tool-output run released
    needle = ACCOUNT.encode()
    ex = rows[digests["tool"]]["ex"]
    tool_files = [p for p in root.rglob("*") if p.is_file() and ex in p.name]
    assert tool_files
    aer = next(p for p in tool_files if p.name.endswith(".aer.jsonl")).read_bytes()
    assert b"/home/acct-" in aer and b"credleak.value_redacted@1" in aer
    assert [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and needle in p.read_bytes()] == []
    assert any(needle in p.read_bytes() for p in root.with_name("c.withheld").rglob("*") if p.is_file())
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
