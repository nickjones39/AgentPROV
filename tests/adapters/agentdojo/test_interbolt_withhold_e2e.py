"""D-456: the ``interbolt-agentdojo@2`` ``[withhold]`` policy end to end (pre-check PC-05; HL H.4.5; G.9.5).

The pinned snapshot's run manifests (context artefacts, never executions) hold a third-party workstation account path.
Version 2 of the profile withholds every stored object holding a macOS account home path at seal, object scope, reason
``personal_data``, its digest kept in ``WITHHELD.json``; the executions that cite the manifest as context stay released.

A synthetic tree in the snapshot's layout is built here (never committed): two TraceLogger logs of the strict arm (two
repeats), each repeat's ``run_manifest.json`` (one holding a test-made account path, assembled at run time and never
printed; one without) and a clean README. It is imported in release mode with the shipped profile (a test pin check that
vouches for every file), sealed with the shipped profile, and checked with ``verify --level chain --release``. Nothing is
monkeypatched. Assertions compare digests, rule ids and file names, never the path.
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
for _path in (_TESTS / "security", _TESTS / "adapters", _TESTS / "adapters" / "agentdojo"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import import_support as support  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402
from phase10d_support import SOURCES, synthetic_path  # noqa: E402
from source_support import call, final, log_with, result, turn  # noqa: E402

cli = harness.cli

SRC = next(s for s in SOURCES if s.profile == "interbolt-agentdojo")
PROFILE = "interbolt-agentdojo"
#: A test-made account name (never a real one), assembled at run time.
ACCOUNT = "tst" + "operator" + "x9"
PATH = ("/Us" + "ers/") + ACCOUNT + "/work/interbolt-agentdojo"
PIN = {"commit": SRC.commit, "kind": "git", "role": "head"}
SPEC = f'''corpus_id = "interbolt-test"
corpus_version = "0.1.0"
title = "Interbolt-shaped AgentDojo logs with a test account path in a run manifest (test corpus)"
mode = "import"

[[sources]]
source_id = "{PROFILE}"
profile = "{PROFILE}@2"
parts = ["head"]

[[sources.snapshots]]
snapshot_id = "head"
origin = {{ kind = "git", repo = "{SRC.repo}", commit = "{SRC.commit}", subtree = "" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["agentdojo.suites@2"]
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

A test corpus.

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
    return ACCOUNT.encode() in data


def _tree(root: Path) -> dict[str, str]:
    """The synthetic snapshot; returns the run manifests' labels -> sha256."""
    manifests: dict[str, str] = {}
    for repeat in (0, 1):
        c = call("send_money", {"recipient": "US133000000121212121212", "amount": 10.0}, "call_1")
        doc = log_with([turn(c), result(c, "Transaction sent."), final()], pipeline_name=SRC.synthetic_pipeline,
                       benchmark_version="v1.2.2", duration=3.0 + repeat)  # fmt: skip  (distinct bytes per repeat)
        label = synthetic_path(SRC, doc).replace("/repeat_0/", f"/repeat_{repeat}/")
        (root / label).parent.mkdir(parents=True, exist_ok=True)
        (root / label).write_bytes(json.dumps(doc, indent=4).encode("utf-8"))
        manifest = {"repeat": repeat, "command": ["uv", "run", "python", "-m", "interbolt_agentdojo.run"]}
        if repeat == 0:
            manifest["cwd"] = PATH  # the shape PC-05 found: an absolute path under one named account's home
        run_dir = label.split(f"/repeat_{repeat}/", 1)[0] + f"/repeat_{repeat}"
        target = root / run_dir / "run_manifest.json"
        target.write_bytes(json.dumps(manifest, indent=2).encode("utf-8"))
        manifests[f"{run_dir}/run_manifest.json"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (root / "README.md").write_bytes(b"# Interbolt on AgentDojo (test)\n")
    return manifests


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    base = tmp_path_factory.mktemp("interbolt-withhold")
    manifests = _tree(base / "in")
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, LocalTree(base / "in"), corpus=writer, profile_id=PROFILE, part="head", workers=1,
                               mode="release", pin_check=support.vouch(base / "in", repo=SRC.repo, commit=SRC.commit),
                               pin=PIN)  # fmt: skip
    assert report.exit_code == 0, (report.counters, report.failures[:2])
    assert report.counters["mapped"] == 2 and report.counters["degenerate"] == 0
    return {"partial": base / "c.partial", "manifests": manifests}


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

    package = resources.files("agentprov").joinpath("adapters", "agentdojo")
    node = package.joinpath("semantics", "agentdojo.suites-2")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", f"{PROFILE}.profile.toml").read_bytes(),
        semantics_profiles={"agentdojo.suites@2": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
                                                   if c.is_file()}},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)")},
        producer=ProducerFacts(git_commit="0123456789abcdef0123456789abcdef01234567", git_tree_clean=True,
                               distributions_sha256="sha256:" + "0" * 64, zlib_version="1.2.12"),
        checker=CHECKER,
        registry_date="2026-10-11",
    )


def _seal(working: dict[str, Any]) -> Any:
    from agentprov.corpus.package import ReleaseArgs, seal

    return seal(working["root"], corpus_version="0.1.0", inputs=_inputs(), release=ReleaseArgs(release_date="2026-10-21"))


def test_the_manifest_with_an_account_path_is_withheld_and_the_runs_stay_released(cli, working):
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    flagged, clean = (working["manifests"][k] for k in sorted(working["manifests"]))  # repeat_0, repeat_1
    assert report.counters["withheld_objects"] == 1 and report.counters.get("withheld_executions", 0) == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    (entry,) = document.entries
    assert entry.sha256 == flagged and (entry.reason, entry.basis) == ("personal_data", "profile_rule")
    assert entry.finding is not None and entry.finding.rule == f"{PROFILE}@2:macos-account-path"
    assert entry.affected_executions == () and document.executions == ()
    assert [p.to_json()["rules"] for p in document.policies] == [[
        {"id": "macos-account-path", "kind": "pattern", "scope": "object"}]]
    assert len([line for line in (root / "executions.jsonl").read_text().splitlines() if line]) == 2
    stored = {p.name.split(".", 1)[0] for p in (root / "raw").rglob("*") if p.is_file()}
    assert clean in stored and flagged not in stored
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_byte_holds_the_account_and_the_sidecar_does(working):
    _seal(working)
    root = working["root"]
    holding = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and _holds(p.read_bytes()))
    assert holding == []  # names only
    assert any(_holds(p.read_bytes()) for p in root.with_name("c.withheld").rglob("*") if p.is_file())
    data = (root / "WITHHELD.json").read_bytes()
    assert b"/Users/[" not in data  # the pattern stays in the profile


def test_version_1_has_no_policy_so_a_corpus_recorded_under_it_must_never_be_sealed():
    """The archived v1 (the pre-check scratch corpora's bytes) declares no [withhold]: such a corpus would release the
    path; the round re-imports at v2 (D-31 owner ruling 2026-10-15)."""
    from agentprov.adapters.profiles import load_profile

    assert "withhold" not in load_profile(PROFILE, 1).data
    assert load_profile(PROFILE).version == 2 and load_profile(PROFILE).data["withhold"]["reason"] == "personal_data"
