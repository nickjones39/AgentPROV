"""D-602: the shipped ``redcode-exec-openhands`` ``[withhold]`` rule, end to end with no injection (D-450 decoded scan;
D-234..D-236; HL H.4.5; G.9.4-G.9.6).

The real token sits in an unselected member (a shell history under ``environment/``) of the deposit's supplementary zip,
the ``supp`` context pin. The runner imports one archive input per snapshot and has no archive context tree yet, so that
zip is never stored today and cannot be imported here; the rule takes effect on it once the context tree lands. What
the current runner can import is a trajectory deposit zip as the archive input, so this test builds one at run time
(never committed) in the layout of Zenodo 23168099: the committed RedCode fixture trajectories under their member
labels, plus an unselected member ``environment/<seg>/.bash_history`` that holds a test-made value of the token shape
(assembled at run time, never printed). Checked:

* import (release mode, archive input with a Zenodo test pin): every trajectory maps; the history member is not
  selected, so it is no object of its own and no execution cites it;
* seal (release): the decoded scan finds the value inside the stored zip and withholds the zip at object level (basis
  ``profile_rule``, scope ``object``, reason ``secret``); **0 executions** are withheld (the trajectories are stored as
  their own objects and were scanned as stored);
* ``verify --level chain --release`` passes on the sealed corpus;
* no sealed byte holds the value; the private sidecar does; ``WITHHELD.json`` names the rule id, never the value.
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

import openhands_support as support
import pytest

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "security", _TESTS / "corpus", _TESTS / "unit" / "release", _TESTS / "adapters",
              _TESTS.parent / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402

cli = harness.cli

PROFILE = "redcode-exec-openhands"
PIN_FILE = "trajectories_OH-test.zip"
DOI = "10.5281/zenodo.1"
SPEC = f'''corpus_id = "redcode-withhold-test"
corpus_version = "0.1.0"
title = "RedCode-shaped OpenHands runs with a test-made token in an unselected member (test corpus)"
mode = "import"

[[sources]]
source_id = "{PROFILE}"
profile = "{PROFILE}@1"
parts = ["head"]

[[sources.snapshots]]
snapshot_id = "head"
origin = {{ kind = "zenodo", doi = "{DOI}", file = "{PIN_FILE}" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["openhands.tools@2"]
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

A test corpus of RedCode-shaped OpenHands runs.

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
#: A test-made value of the token shape (hf_ and 34 letters and digits), never a deposited value.
TOKEN = "hf" + "_" + "TESTSENTINEL" + "0123456789" + "abcdefghijkl"
assert len(TOKEN) == 37


def _zip(path: Path) -> tuple[dict[str, Any], int]:
    members = {label: data for label, data in support.tree("redcode").items() if "/trajectory/" in label}
    assert members
    members["environment/OpenHands-test/.bash_history"] = f"ls\nexport HF_TOKEN={TOKEN}\n".encode()
    members["README.md"] = b"not selected\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in sorted(members.items()):
            zf.writestr(label, data)
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": DOI, "record": 1, "version": "v1", "file": path.name,
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return pin, sum(1 for label in members if "/trajectory/" in label)


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed OpenHands fixtures are absent")
    base = tmp_path_factory.mktemp("redcode-withhold")
    pin, runs = _zip(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, tree, corpus=writer, profile_id=PROFILE, part="head", pin=pin, workers=1,
                               mode="release")
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == runs and report.counters["degenerate"] == 0
    return {"partial": base / "c.partial", "container": pin["sha256"], "runs": runs}


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

    package = resources.files("agentprov").joinpath("adapters", "openhands")
    node = package.joinpath("semantics", "openhands.tools-2")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", f"{PROFILE}.profile.toml").read_bytes(),
        semantics_profiles={"openhands.tools@2": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
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


def test_the_decoded_hit_withholds_the_zip_at_object_level_and_no_execution(cli, working):
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_objects"] == 1 and report.counters["withheld_executions"] == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    (entry,) = document.entries
    assert entry.sha256 == working["container"]
    assert (entry.reason, entry.basis) == ("secret", "profile_rule")
    assert entry.finding is not None and entry.finding.rule.startswith(f"{PROFILE}@1:")
    assert [p.to_json()["rules"] for p in document.policies] == [[{"id": "hf-token-shape", "kind": "pattern",
                                                                    "scope": "object"}]]
    assert document.executions == () or list(document.executions) == []
    rows = [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]
    assert len(rows) == working["runs"]  # every run stays released
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_byte_holds_the_value_and_withheld_json_names_the_rule_only(working):
    _seal(working)
    root = working["root"]
    needle = TOKEN.encode()
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and needle in p.read_bytes()) == []
    sidecar = root.with_name("c.withheld")
    assert any(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == working["container"]
               for p in sidecar.rglob("*"))
    data = (root / "WITHHELD.json").read_bytes()
    assert needle not in data and b"[A-Za-z0-9]{34}" not in data and b"hf-token-shape" in data
