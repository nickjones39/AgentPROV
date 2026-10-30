"""An ATIA corpus seals in release mode with the ``inspect.atia@1`` SEM stage (DECISIONS D-307 addendum: orchestrator
request 2026-10-21; docs/architecture D.9.15; H.3.1).

A sealed index row records a SEM stage (H.3.1), so before ``inspect.atia@1`` an ATIA corpus could not be sealed. The
input is a ``logs/`` tree assembled at test time (never committed; D-309) whose files a test pin check vouches for at the
profile's pin: one synthetic ``inspect_ai 0.3.112`` log with a tool-call sample and a sample without a call. Nothing is
monkeypatched: the import reads the registry part's semantics profile. Checked:

* import (release mode) maps both samples, each with the SEM stage ``inspect.atia@1`` ``ok``;
* the seal (release) writes every row with ``sem``, ``prov`` and ``validation`` stages and a SEM digest and path;
* ``verify --level chain --release`` passes on the sealed corpus.
"""

from __future__ import annotations

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
import test_atia_semantics as atia_sem  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402

cli = harness.cli

PROFILE = "atia-benchmark"
SEM = "inspect.atia@1"
LOG = "logs/2025-07-17T00-00-00-04-00_account-takeover-suite_SyntheticAtiaLog00000a.eval"
SPEC = '''corpus_id = "atia-benchmark"
corpus_version = "0.1.0"
title = "ATIA-shaped synthetic logs (test corpus)"
mode = "import"

[[sources]]
source_id = "atia-benchmark"
profile = "atia-benchmark@1"
parts = ["logs"]

[[sources.snapshots]]
snapshot_id = "logs"
origin = { kind = "git", repo = "https://github.com/mattngyn/atia_benchmark", commit = "cc71caf55c6f35d7aad440a4a746f44ae39d17c4", subtree = "logs" }
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["inspect.atia@1"]
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

A test corpus of ATIA-shaped logs.

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


def _tree(root: Path) -> None:
    header = isp.synthetic_header("0.3.112")
    header["eval"]["task"] = "account_takeover_suite"
    samples = {"s1_epoch_1.json": isp.basic_sample("s1", tune=atia_sem._atia_shape),
               "s2_epoch_1.json": atia_sem._no_call_sample("s2")}
    (root / LOG).parent.mkdir(parents=True, exist_ok=True)
    (root / LOG).write_bytes(isp.build_eval(header, samples))


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    import import_support as support

    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    profile = load_profile(PROFILE)
    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("primary") is True)
    base = tmp_path_factory.mktemp("atia-seal")
    source = base / "in"
    _tree(source)
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, LocalTree(source), corpus=writer, profile_id=PROFILE, part="logs",
                               mode="release", workers=1, pin=pin,
                               pin_check=support.vouch(source, repo=pin["repo"], commit=pin["commit"]))
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 2 and report.counters["degenerate"] == 0, report.counters
    return {"partial": base / "c.partial"}


@pytest.fixture
def working(working_template: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    partial = tmp_path / "c.partial"
    shutil.copytree(working_template["partial"], partial, symlinks=True)
    return {"root": tmp_path / "c", "partial": partial}


def _inputs() -> Any:
    from importlib import resources

    from agentprov.adapters.registry.claims import CHECKER
    from agentprov.corpus.datasheet import load_statements
    from agentprov.corpus.package import LicenceFile, ProducerFacts, SealInputs

    package = resources.files("agentprov").joinpath("adapters", "inspect")
    node = package.joinpath("semantics", "inspect.atia-1")
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


def _rows(root: Path) -> list[dict[str, Any]]:
    import json

    return [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]


def test_the_import_annotates_every_execution_with_the_registry_part_profile(working_template):
    rows = _rows(working_template["partial"])
    assert [r["stages"]["sem"] for r in rows] == [{SEM: "ok"}] * 2


def test_the_corpus_seals_with_the_sem_stage_and_verifies_chain_release(cli, working):
    from agentprov.corpus.package import ReleaseArgs, seal

    report = seal(working["root"], corpus_version="0.1.0", inputs=_inputs(),
                  release=ReleaseArgs(release_date="2026-10-21"))
    assert report.counters.get("withheld_objects", 0) == 0 and report.counters.get("withheld_executions", 0) == 0
    root = working["root"]
    assert not (root / "WITHHELD.json").exists()  # the profile declares no [withhold] rule
    rows = _rows(root)
    assert len(rows) == 2
    for row in rows:
        assert row["stages"]["sem"] == {SEM: "ok"} and row["stages"]["prov"] and row["stages"]["validation"]
        assert set(row["digests"]["sem"]) == {SEM} and set(row["paths"]["sem"]) == {SEM}
        assert row["paths"]["sem"][SEM].startswith("sem/inspect.atia-1/")
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
