"""D-221 with D.16.14 R3 (pre-round review PR-2): a DTap corpus holding an LFS pinned object seals end to end.

An R3 pinned object (the LFS object a Git LFS pointer stands for) is mapped as a primary candidate with its own pin's
``hf`` origin. ``package`` built the snapshot origin from every primary's root origin, so ``git`` (the runs pin) plus
``hf`` (the object) was refused as mixed kinds (``package.refused.pin``) for every dtap-bench@2 and mcphunt@2 corpus.
The snapshot origin is now built without the recorded pinned objects' exact (object, origin) pairs, as the re-map does
(``rawtree``'s ``pinned_keys``), and the pinned object is sealed in ``pinned_objects`` (D-221). The DTap fixture is
imported in release mode with its ``tasks`` tree (pinned) and one LFS object; it must seal and pass
``verify --level chain --release``.
"""

from __future__ import annotations

import json
import sys
from importlib import resources
from pathlib import Path
from typing import Any

import dtap_support as support
from test_import import _object

from agentprov.adapters.profiles import load_profile

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "corpus",):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import verify_support as vs  # noqa: E402

TASKS_PIN = {"kind": "git", "role": "tasks", "repo": support.TASKS_REPO, "commit": support.TASKS_COMMIT}
SPEC = f'''corpus_id = "dtap-lfs-test"
corpus_version = "0.1.0"
title = "DTap fixture with one LFS object (test corpus)"
mode = "import"

[[sources]]
source_id = "dtap"
profile = "{support.PROFILE}@3"
parts = ["head"]

[[sources.snapshots]]
snapshot_id = "head"
origin = {{ kind = "git", repo = "{support.RUNS_REPO}", commit = "{support.RUNS_COMMIT}", subtree = "" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["dtap.tools@3"]
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

A test corpus of DTap-shaped runs with one LFS object.

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


def _inputs() -> Any:
    from agentprov.adapters.registry.claims import CHECKER
    from agentprov.corpus.datasheet import load_statements
    from agentprov.corpus.package import LicenceFile, ProducerFacts, SealInputs

    package = resources.files("agentprov").joinpath("adapters", "dtap")
    node = package.joinpath("semantics", "dtap.tools-3")
    return SealInputs(
        spec=SPEC.encode(), card=CARD.encode(), changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", f"{support.PROFILE}.profile.toml").read_bytes(),
        semantics_profiles={"dtap.tools@3": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
                                             if c.is_file()}},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)")},
        producer=ProducerFacts(git_commit="0123456789abcdef0123456789abcdef01234567", git_tree_clean=True,
                               distributions_sha256="sha256:" + "0" * 64, zlib_version="1.2.12"),
        checker=CHECKER, registry_date="2026-10-11",
    )


def test_a_corpus_with_an_lfs_pinned_object_seals_and_verifies(tmp_path, monkeypatch):
    from agentprov.cli.main import main
    from agentprov.corpus.package import ReleaseArgs, seal

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    runs_pin = dict(next(p for p in load_profile(support.PROFILE).data["source"]["pins"] if p["role"] == "runs"))
    imp = support.run_import(tmp_path, support.runs_files(), support.tasks_files(), objects=[_object(tmp_path)],
                             pin=runs_pin, tasks_pin=TASKS_PIN, mode="release", in_process=False, workers=1)
    working = json.loads((imp.partial / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    assert working["pinned_objects"] and working["pinned_objects"][0]["origin"]["kind"] == "hf"
    root = tmp_path / "corpus"
    seal(root, corpus_version="0.1.0", inputs=_inputs(), release=ReleaseArgs(release_date="2026-10-21"))
    snapshot = json.loads((root / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    assert snapshot["origin"] == {"kind": "git", "repo": support.RUNS_REPO, "commit": support.RUNS_COMMIT, "subtree": ""}
    assert [o["label"] for o in snapshot["pinned_objects"]] == [o["label"] for o in working["pinned_objects"]]
    assert snapshot["context"][0]["role"] == "tasks"
    assert main(["verify", "--corpus", str(root), "--json", "--level", "chain", "--release",
                 "--root-digest", vs.root_digest(root)]) == 0
