"""The ``whistlebench`` ``[withhold]`` rule and redaction, end to end with no injection (D-601; D-234..D-236, D-450).

The policy is read from the shipped profile everywhere it is read (the import worker, sealing, ``verify --level chain``
and the deposit builder): nothing is monkeypatched. The input is a ``final_runs/`` tree assembled at test time (never
committed) whose files a test pin check vouches for at the profile's pin: two synthetic ``.eval`` logs in the producer
band. One log's header names a clone URL whose userinfo carries a test-made value of the GitHub token shape (assembled at
run time, never printed), in ``header.json`` and in the unselected ``_journal/start.json``, as in the 28
``awareness_blackbox`` logs; the other is clean, and one of its samples keeps an earlier attempt's error whose traceback
names a made-up home directory. Checked:

The import annotates with the registry part's ``inspect.whistlebench@2`` (D-601 addenda): a sealed index row records
a SEM stage (H.3.1).

* import (release mode) maps all three samples; their AERs hold the redacted URL and label only (D-601);
* seal (release) withholds the token log's ``header.json`` (basis ``profile_rule``, scope ``object``) and its ``.eval``
  container (basis ``container``; the decoded scan of D-450 reaches the same container through ``_journal/start.json``
  and leaves that basis), and no execution;
* ``verify --level chain --release`` passes on the sealed corpus (the D-236 backstop re-applies the profile's rule);
* no sealed or deposited byte holds the value; the private sidecar does; ``WITHHELD.json`` names the rule id only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "security", _TESTS / "corpus", _TESTS / "unit" / "release", _TESTS / "adapters",
              _TESTS / "adapters" / "inspect", _TESTS.parent / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import inspect_support as isp  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402

cli = harness.cli

PROFILE = "whistlebench"
SEM = "inspect.whistlebench@2"
#: A test-made value of the GitHub token shape (never a real credential; assembled at run time).
TOKEN = "gh" + "p_" + "Synth0" * 6
USERINFO = "x-access-token:" + TOKEN
ACCOUNT = "made-up-home-7"
DIR = "final_runs/awareness_blackbox/snitchbench"
TOKEN_LOG = f"{DIR}/2025-09-20T00-00-00-07-00_high-agency-awareness_SyntheticTokenLog0000a.eval"
CLEAN_LOG = f"{DIR}/2025-09-20T00-00-01-07-00_high-agency-awareness_SyntheticCleanLog0000a.eval"
SPEC = '''corpus_id = "whistlebench"
corpus_version = "0.1.0"
title = "WhistleBench logs with a test-made token-shaped value (test corpus)"
mode = "import"

[[sources]]
source_id = "whistlebench"
profile = "whistlebench@2"
parts = ["final-runs"]

[[sources.snapshots]]
snapshot_id = "final-runs"
origin = { kind = "git", repo = "https://github.com/legobridge/whistlebench", commit = "9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc", subtree = "final_runs" }
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["inspect.whistlebench@2"]
prov_specs = ["agentprov-prov/0.1"]
views = []
options = { context_encoding = "members" }

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

A test corpus of WhistleBench-shaped logs.

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


def _holds(data: bytes) -> bool:
    return TOKEN.encode() in data


def _log(*, token: bool, samples: dict[str, dict[str, Any]]) -> tuple[bytes, bytes]:
    """A band ``.eval`` (inspect_ai 0.3.130) and its ``header.json`` bytes."""
    header = isp.synthetic_header("0.3.130")
    origin = "https://github.com/legobridge/whistlebench.git"
    if token:
        origin = origin.replace("https://", f"https://{USERINFO}@")
    header["eval"]["revision"] = {"type": "git", "origin": origin, "commit": "9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc",
                                  "dirty": False}
    start = json.dumps({"version": 2, "eval": header["eval"], "plan": header["plan"]}).encode()
    return isp.build_eval(header, samples, extra={"_journal/start.json": start}), json.dumps(header).encode()


def _retry_sample(sid: str) -> dict[str, Any]:
    trace = f'Traceback (most recent call last):\n  File "/Users/{ACCOUNT}/work/run.py", line 3\nTimeoutError: x'
    sample = isp.basic_sample(sid)
    sample["error_retries"] = [{"message": "TimeoutError: x", "traceback": trace, "traceback_ansi": trace}]
    return sample


def _tree(root: Path) -> dict[str, str]:
    token_log, token_header = _log(token=True, samples={"s1_epoch_1.json": isp.basic_sample("s1"),
                                                         "s2_epoch_1.json": isp.basic_sample("s2")})
    clean_log, _ = _log(token=False, samples={"s3_epoch_1.json": _retry_sample("s3")})
    for label, data in ((TOKEN_LOG, token_log), (CLEAN_LOG, clean_log)):
        (root / label).parent.mkdir(parents=True, exist_ok=True)
        (root / label).write_bytes(data)
    assert _holds(token_log) is False  # compressed: the stored container does not hold the value literally
    return {"header": hashlib.sha256(token_header).hexdigest(), "container": hashlib.sha256(token_log).hexdigest()}


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    import import_support as support

    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    profile = load_profile(PROFILE)
    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("primary") is True)
    base = tmp_path_factory.mktemp("whistlebench-withhold")
    source = base / "in"
    planted = _tree(source)
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, LocalTree(source), corpus=writer, profile_id=PROFILE, part="final-runs",
                               mode="release", workers=1, pin=pin,
                               pin_check=support.vouch(source, repo=pin["repo"], commit=pin["commit"]))
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 3 and report.counters["degenerate"] == 0, report.counters
    return {"partial": base / "c.partial", **planted}


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

    package = resources.files("agentprov").joinpath("adapters", "inspect")
    node = package.joinpath("semantics", "inspect.whistlebench-2")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", f"{PROFILE}.profile.toml").read_bytes(),
        semantics_profiles={SEM: {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
                                  if c.is_file()}},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)")},
        producer=ProducerFacts(git_commit="0123456789abcdef0123456789abcdef01234567", git_tree_clean=True,
                               distributions_sha256="sha256:" + "0" * 64, zlib_version="1.2.12"),
        checker=CHECKER,
        registry_date="2026-10-21",
    )


def _seal(working: dict[str, Any]) -> Any:
    from agentprov.corpus.package import ReleaseArgs, seal

    return seal(working["root"], corpus_version="0.1.0", inputs=_inputs(), release=ReleaseArgs(release_date="2026-10-21"))


def _rows(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]


def test_the_working_aers_hold_the_redacted_copies_only(working_template):
    partial = working_template["partial"]
    aers = [p for p in (partial / "aer").rglob("*.aer.jsonl")]
    assert len(aers) == 3
    labels, repos = set(), set()
    for path in aers:
        data = path.read_bytes()
        assert not _holds(data) and f"/Users/{ACCOUNT}/".encode() not in data
        for line in data.splitlines():
            record = json.loads(line)
            if record.get("k") == "actor" and record.get("id") == "bench":
                repos.add(record["code"]["repo"])
            for entry in record.get("ext", {}).get("inspect", {}).get("redacted", []):
                labels.add(entry["rule"])
    assert labels == {"whistlebench@2#origin_userinfo", "whistlebench@2#retry_account"}
    assert repos == {"https://redacted@github.com/legobridge/whistlebench.git", "https://github.com/legobridge/whistlebench.git"}
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    assert [r["stages"]["sem"] for r in rows] == [{SEM: "ok"}] * 3  # the registry part's semantics profile, each
    # the raw header the AER points at still holds the value (raw is never edited, invariant 3)
    assert any(_holds(p.read_bytes()) for p in (partial / "raw").rglob("*") if p.is_file())


def test_the_shipped_profile_withholds_the_header_and_its_container_only(cli, working):
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_objects"] == 2 and report.counters["withheld_executions"] == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    by_sha = {e.sha256: e for e in document.entries}
    assert set(by_sha) == {working["header"], working["container"]}
    header = by_sha[working["header"]]
    assert (header.reason, header.basis, header.affected_executions) == ("secret", "profile_rule", ())
    assert header.finding is not None and header.finding.rule == f"{PROFILE}@2:github-token-shape"
    assert by_sha[working["container"]].basis == "container"  # the decoded _journal/start.json hit leaves this basis
    assert [p.to_json()["rules"] for p in document.policies] == [[
        {"id": "github-token-shape", "kind": "pattern", "scope": "object"}]]
    assert document.executions == ()
    assert len(_rows(root)) == 3  # every execution is released
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_or_deposited_byte_holds_the_value(working, tmp_path):
    import release_support as rs

    _seal(working)
    root = working["root"]
    holding = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and _holds(p.read_bytes()))
    assert holding == []  # names only
    sidecar = root.with_name("c.withheld")
    assert any(_holds(p.read_bytes()) for p in sidecar.rglob("*") if p.is_file())
    rs.build([root], tmp_path / "deposit")
    assert not any(_holds(p.read_bytes()) for p in (tmp_path / "deposit").rglob("*") if p.is_file())
    assert not any(p.name.startswith(working["container"]) for p in (tmp_path / "deposit").rglob("*"))


def test_withheld_json_names_rule_ids_never_a_pattern_or_match(working):
    _seal(working)
    data = (working["root"] / "WITHHELD.json").read_bytes()
    assert not _holds(data) and b"gh[pousr]" not in data
    assert json.loads(data)["policies"][0]["profile"]["id"] == PROFILE


def test_the_datasheet_discloses_the_raw_traceback_account(working):
    """D-601 (user decision 2026-10-21): the raw sample members ship as pinned (D-186 (c)); the datasheet says so."""
    _seal(working)
    sheet = (working["root"] / "DATASHEET.md").read_text(encoding="utf-8")
    known = sheet.split("## Known issues", 1)[1] if "## Known issues" in sheet else sheet
    assert "third-party workstation account" in known and "260" in known and "722" in known
    assert "D-601" in known  # the decision is named with the statement
    manifest = json.loads((working["root"] / "corpus.json").read_bytes())
    assert "whistlebench-retry-traceback-account" in json.dumps(manifest["datasheet"])
