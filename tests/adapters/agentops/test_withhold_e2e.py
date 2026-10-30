"""D-608 end to end: the shipped ``agentops-bench-pilot`` profile redacts and withholds, with nothing monkeypatched
(import -> seal -> ``verify --level chain --release``; D-234..D-236, D-450, D-604; HL H.4.5).

The archive input is a gzip tar in the deposit's layout, assembled here (never committed): three agentops-shaped run
files made up for the test. One selected run's run_python output names a made-up ``/Users/<name>/`` path (its
assistant text does not); one selected run holds no path; one unselected (out-of-scope) member holds the path too, as
the deposit's 23 out-of-scope runs and 6 rollups do; an AppleDouble copy is never selected. Checked:

* the AER of the path-bearing run is redacted (salted label, ``agentops.value_redacted``) and its execution released;
* sealing withholds the run's raw object (basis ``profile_rule``, reason ``personal_data``, scope ``object``) and the
  tar (the container of a withheld member, and the decoded scan's hit in the unselected member); no execution;
* ``verify --level chain --release`` passes (the D-236 backstop re-applies the rule to every released file);
* no sealed byte holds the path or the name; the private sidecar does.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "security", _TESTS / "corpus", _TESTS / "unit" / "release", _TESTS / "adapters",
              _TESTS.parent / "tools", Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402
from agentops_support import _call, _result, run_json, step  # noqa: E402

cli = harness.cli

NAME = "jd" + "oe42"  # a made-up account
HOME = "/Us" + "ers/" + NAME
PIN_FILE = "agentops-test-traces.tar.gz"
DOI = "10.5281/zenodo.1"
ROOT = "pilot_v1_seeded/gpt/openai_gpt-x/"
PROFILE = "agentops-bench-pilot"
SPEC = f'''corpus_id = "agentops-test"
corpus_version = "0.1.0"
title = "AgentOps-shaped runs with a made-up account path (test corpus)"
mode = "import"

[[sources]]
source_id = "agentops-bench"
profile = "{PROFILE}@2"
parts = ["pilot-v1-seeded"]

[[sources.snapshots]]
snapshot_id = "pilot-v1-seeded"
origin = {{ kind = "zenodo", doi = "{DOI}", file = "{PIN_FILE}" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["agentops.tools@2"]
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

A test corpus of AgentOps-shaped runs.

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
    return HOME.encode() in data or NAME.encode() in data


def _run(condition: str, task: str, tool_text: str) -> bytes:
    run = run_json([step(1, [_call("run_python")], [_result("run_python", tool_text)], reasoning="let me run it"),
                    step(2, [], [], reasoning="done")], condition=condition)
    run["task_id"] = run["trace"]["task_id"] = task
    return json.dumps(run).encode()


def _tar(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    trace = f'Traceback:\n  File "{HOME}/work/sandbox/run.py", line 1\nNameError: x'
    members = {
        ROOT + "adversarial/safety_001_run1.json": _run("adversarial", "safety/001", trace),
        ROOT + "adversarial/safety_002_run1.json": _run("adversarial", "safety/002", "42"),
        ROOT + "clean/code_001_run1.json": _run("clean", "code/001", trace),  # out of scope: never selected
        ROOT + "adversarial/._safety_002_run1.json": b"\x00\x05\x16\x07appledouble",
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for label, data in sorted(members.items()):
            info = tarfile.TarInfo(label)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tf.addfile(info, io.BytesIO(data))
    path.write_bytes(gzip.compress(buf.getvalue(), mtime=0))
    data = path.read_bytes()
    pin = {"role": "runs", "kind": "zenodo", "doi": DOI, "record": 1, "version": "v1", "file": path.name,
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return pin, {label: hashlib.sha256(raw).hexdigest() for label, raw in members.items()}


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    base = tmp_path_factory.mktemp("agentops-withhold")
    pin, digests = _tar(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(base / "c") as writer:
        report = import_source("agentops-bench", tree, corpus=writer, profile_id=PROFILE, part="pilot-v1-seeded",
                               pin=pin, workers=1, mode="release")
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 2 and report.counters["degenerate"] == 0, report.counters
    return {"partial": base / "c.partial", "digests": digests, "container": pin["sha256"]}


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

    package = resources.files("agentprov").joinpath("adapters", "agentops")
    node = package.joinpath("semantics", "agentops.tools-2")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", f"{PROFILE}.profile.toml").read_bytes(),
        semantics_profiles={"agentops.tools@2": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
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


def _rows(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]


def test_the_working_aer_is_redacted_before_sealing(working):
    aers = [p for p in working["partial"].rglob("*") if p.is_file() and "aer" in p.name and p.suffix in (".jsonl", ".zst")]
    assert aers
    redacted = [p for p in aers if b"agentops.value_redacted" in p.read_bytes()]
    assert len(redacted) == 1
    assert not any(_holds(p.read_bytes()) for p in aers)


def test_the_profile_withholds_the_raw_objects_and_releases_every_execution(cli, working):
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    digests = working["digests"]
    path_run = digests[ROOT + "adversarial/safety_001_run1.json"]
    assert report.counters["withheld_executions"] == 0, report.counters
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    by_sha = {e.sha256: e for e in document.entries}
    assert set(by_sha) == {path_run, working["container"]}, sorted(by_sha)
    entry = by_sha[path_run]
    assert (entry.reason, entry.basis) == ("personal_data", "profile_rule")
    assert entry.finding is not None and entry.finding.rule.startswith(f"{PROFILE}@2:")
    assert by_sha[working["container"]].reason == "personal_data"
    assert [p.to_json()["rules"] for p in document.policies] == [[{"id": "account-path", "kind": "pattern",
                                                                   "scope": "object"}]]
    assert document.executions == () or len(document.executions) == 0
    released = _rows(root)
    assert len(released) == 2  # both selected runs, the redacted one included
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_byte_holds_the_path(working):
    _seal(working)
    root = working["root"]
    holding = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and _holds(p.read_bytes()))
    assert holding == []  # names only
    sidecar = root.with_name("c.withheld")
    assert any(_holds(p.read_bytes()) for p in sidecar.rglob("*") if p.is_file())
