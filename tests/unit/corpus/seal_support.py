"""Helpers for the sealing tests (``seal_support``; not collected).

:func:`working_corpus` imports three golden June-2024 AgentDojo logs (loaded programmatically from the committed,
licence-cleared fixtures; their text is never printed) into a working corpus once per session, in release mode through a
T1 worker, with a test pin that vouches for every file; each test gets its own copy. :func:`inputs` builds the
:class:`~agentprov.corpus.package.SealInputs` of a small test spec (``mini-agentdojo``) whose card and changes are
written here; the decided statements are the committed ``corpora/datasheet-statements.toml``.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
for _path in (REPO / "tests" / "adapters", REPO / "tests" / "unit" / "raw"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import import_support as support  # noqa: E402

from agentprov.corpus.datasheet import load_statements  # noqa: E402
from agentprov.corpus.package import LicenceFile, ProducerFacts, SealInputs  # noqa: E402

C274885 = support.C274885
COMMIT = "0123456789abcdef0123456789abcdef01234567"
TREE_SHA1 = "1227480d637f06ac435c809ab39803afa72f78fc"
PIN = {"commit": C274885, "kind": "git", "role": "2024-06", "tree": "runs/", "tree_sha1": TREE_SHA1}

SPEC = f'''corpus_id = "mini-agentdojo"
corpus_version = "0.1.0"
title = "Three golden AgentDojo logs (test corpus)"
mode = "import"

[[sources]]
source_id = "agentdojo"
profile = "agentdojo-upstream@2"
parts = ["2024-06"]

[[sources.snapshots]]
snapshot_id = "2024-06"
origin = {{ kind = "git", repo = "{support.AGENTDOJO}", commit = "{C274885}", subtree = "runs", subtree_sha1 = "{TREE_SHA1}" }}
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

A test corpus of golden logs.

## Composition

The corpus holds {{v:/counts/executions}} execution records. {{claim:raw_included}} {{claim:validation_strict}}

## Maintenance

Test only.
"""

CHANGES = '''[[change]]
version = "0.1.0"
bump = "initial"
summary = "Test corpus."
'''

_TEMPLATE: dict[str, Path] = {}


def _build(root: Path) -> Path:
    from agentprov.adapters.runner.importer import LocalTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    support.agentdojo_tree(root / "in", count=3)
    with CorpusWriter(root / "c") as corpus:
        report = import_source("agentdojo", LocalTree(root / "in"), corpus=corpus, part="2024-06", workers=1, mode="release",
                               pin_check=support.vouch(root / "in"), pin=PIN)
    assert report.exit_code == 0, report.counters
    return root / "c.partial"


def working_corpus(tmp_path_factory: Any, dest: Path) -> Path:
    """A fresh copy of the session's working corpus at ``dest.partial``; returns ``dest`` (the final directory)."""
    if "tree" not in _TEMPLATE:
        _TEMPLATE["tree"] = _build(tmp_path_factory.mktemp("seal-template"))
    partial = dest.with_name(dest.name + ".partial")
    shutil.copytree(_TEMPLATE["tree"], partial, symlinks=True)
    return dest


def source_profile() -> bytes:
    from importlib import resources

    return resources.files("agentprov").joinpath("adapters", "agentdojo", "profiles", "agentdojo-upstream.profile.toml").read_bytes()


def semantics_files() -> dict[str, bytes]:
    from importlib import resources

    node = resources.files("agentprov").joinpath("adapters", "agentdojo", "semantics", "agentdojo.suites-2")
    return {child.name: child.read_bytes() for child in sorted(node.iterdir(), key=lambda c: c.name) if child.is_file()}


def inputs(**changes: Any) -> SealInputs:
    """The seal inputs of the test spec; keyword arguments replace fields (``spec``, ``card``, ``producer``, …)."""
    from agentprov.adapters.registry.claims import CHECKER

    base = SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((REPO / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=source_profile(),
        semantics_profiles={"agentdojo.suites@2": semantics_files()},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)")},
        producer=ProducerFacts(git_commit=COMMIT, git_tree_clean=True, distributions_sha256="sha256:" + "0" * 64,
                               zlib_version="1.2.12"),
        checker=CHECKER,
        registry_date="2026-10-11",
    )
    return replace(base, **changes)


def tree_bytes(root: Path) -> dict[str, bytes]:
    return support.tree_bytes(root)


def committed_spec(corpus_id: str) -> dict[str, Any]:
    """``spec`` and ``persona_files`` seal inputs for a committed corpus spec (``corpora/<id>/corpus-spec.toml``): the
    persona files its ``[scan]`` table names (D-810), read from beside it as ``agentprov package`` reads them."""
    from agentprov.corpus.spec import parse_spec

    path = REPO / "corpora" / corpus_id / "corpus-spec.toml"
    data = path.read_bytes()
    personas = {rel.rsplit("/", 1)[-1]: (path.parent / rel).read_bytes() for rel, _digest in parse_spec(data).persona_files}
    return {"spec": data, "persona_files": personas}
