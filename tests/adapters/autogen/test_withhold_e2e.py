"""D-603: the shipped ``autogen-guard-placement`` ``[withhold]`` policy, end to end (import -> seal -> chain --release).

Pre-check PC-01 found a real-format secret key of the study's own observability service in one deposit member the
profile never selects (it is neither a run file nor a context artefact), so the corpus stores it only inside the deflated
deposit zip. Its bytes never appear literally in any stored object; only the decoded scan of D-450 can see them. The
profile's object-scope rule must therefore withhold the zip object, and nothing else: no execution, no stored member.

The archive input is a deposit zip assembled at test time (never committed): the committed fixture members (the
InjecAgent tool arm and its context files, unedited) plus one unselected member at the label PC-01 named, whose text
carries a test-made sentinel of the key's shape (assembled at run time from pieces, never a deposited value, never
printed). Nothing is monkeypatched: the policy is read from the shipped profile by the import worker, sealing,
``verify --level chain`` and the deposit builder. Checked:

* import (release mode, archive input with a Zenodo test pin) maps the 20 runs; sealing withholds exactly one object,
  the zip (reason ``secret``, basis ``profile_rule``, the decoded detector, rule ``langfuse-secret-key``, no affected
  execution), and no execution; the 20 executions and every selected member stay released;
* ``verify --level chain --release`` passes on the sealed corpus (the D-236 backstop re-reads every released archive
  decoded, D-450);
* no sealed or deposited byte holds the sentinel, read as stored and with every zip decoded; the private sidecar does.
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

import autogen_support as support
import pytest

_TESTS = Path(__file__).resolve().parents[2]
for _path in (_TESTS / "security", _TESTS / "corpus", _TESTS / "unit" / "release", _TESTS / "adapters"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402

cli = harness.cli

PIN_FILE = "deposit.zip"
DOI = "10.5281/zenodo.1"
#: The member PC-01 named; the profile selects neither it nor any sibling capture outside phase 0.
UNSELECTED = support.ROOT + "results/phase7/capture.json"
#: A test-made sentinel of the rule's shape (prefix, then a UUID of lower-case hex); assembled here, never committed whole.
SENTINEL = ("sk" + "-l" + "f-" + "-".join(("d603" * 2, "0" * 4, "4" + "0" * 3, "8" + "0" * 3, "d603" * 3))).encode()
SPEC = f'''corpus_id = "autogen-withhold-test"
corpus_version = "0.1.0"
title = "AutoGen guard-placement runs with a test-made key in an unselected member (test corpus)"
mode = "import"

[[sources]]
source_id = "autogen-guard-placement"
profile = "autogen-guard-placement@2"
parts = ["v1.0"]

[[sources.snapshots]]
snapshot_id = "v1.0"
origin = {{ kind = "zenodo", doi = "{DOI}", file = "{PIN_FILE}" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["autogen.tools@1"]
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

A test corpus of AutoGen guard-placement runs.

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


def _decoded_holds(data: bytes) -> bool:
    """The sentinel in ``data`` as stored, or in any member of ``data`` read as a zip (in memory, depth 1)."""
    if SENTINEL in data:
        return True
    if not data.startswith(b"PK\x03\x04"):
        return False
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return any(SENTINEL in zf.read(info) or SENTINEL in info.filename.encode() for info in zf.infolist())


def _zip(path: Path) -> dict[str, Any]:
    """The test deposit zip (fixed member times, deflated); returns its pin."""
    members = {label: data for label, (data, _method) in support.fixture_members().items()}
    assert UNSELECTED not in members and not any(SENTINEL in d for d in members.values())
    members[UNSELECTED] = b'{"input_rail_yaml": "observability:\\n  secret_key: ' + SENTINEL + b'\\n"}\n'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for label, data in sorted(members.items()):
            info = zipfile.ZipInfo(label, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    assert SENTINEL not in data  # deflated: only a decoded read can see it
    return {"role": "deposit", "kind": "zenodo", "doi": DOI, "record": 1, "version": "v1", "file": path.name,
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed AutoGen fixtures are absent")
    base = tmp_path_factory.mktemp("autogen-withhold")
    pin = _zip(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(base / "c") as writer:
        report = import_source(support.PROFILE, tree, corpus=writer, profile_id=support.PROFILE, part="v1.0", pin=pin,
                               snapshot_id="v1.0", mode="release", workers=1)
    assert report.exit_code == 0, (report.counters, report.failures[:3])
    assert report.counters["mapped"] == 20 and report.counters["degenerate"] == 0, report.counters
    return {"partial": base / "c.partial", "container": pin["sha256"]}


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

    package = resources.files("agentprov").joinpath("adapters", "autogen")
    node = package.joinpath("semantics", "autogen.tools-1")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", "autogen-guard-placement.profile.toml").read_bytes(),
        semantics_profiles={"autogen.tools@1": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
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


def test_the_shipped_profile_declares_one_object_scope_rule():
    from agentprov.adapters.profiles import load_profile
    from agentprov.corpus.withhold import policy_of_profile

    profile = load_profile(support.PROFILE)
    data = (support.REPO / "src/agentprov/adapters/autogen/profiles/autogen-guard-placement.profile.toml").read_bytes()
    policy = policy_of_profile(data, profile_id=support.PROFILE, profile_version=profile.version)
    assert policy is not None and policy.ref == "autogen-guard-placement@2"
    assert [(r.id, r.kind, r.scope, r.reason) for r in policy.rules] == [("langfuse-secret-key", "pattern", "object", "secret")]
    (rule,) = policy.rules
    assert rule.hits(b"x" + SENTINEL + b"x") and rule.width == len(SENTINEL)
    assert not rule.hits(SENTINEL.replace(b"d603", b"D603"))  # lower-case hex only, as the shape is
    assert not rule.hits(SENTINEL[:-1])


def test_the_zip_is_withheld_and_every_execution_and_selected_member_released(cli, working):
    from agentprov.corpus.withheld import decode_withheld
    from agentprov.corpus.withhold_scan import DECODED_DETECTOR

    before = _rows(working["partial"])
    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_objects"] == 1 and report.counters["withheld_executions"] == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    (entry,) = document.entries
    assert entry.sha256 == working["container"]
    assert (entry.reason, entry.basis, entry.affected_executions) == ("secret", "profile_rule", ())
    assert entry.finding is not None and entry.finding.detector == DECODED_DETECTOR
    assert entry.finding.rule == "autogen-guard-placement@2:langfuse-secret-key"
    assert document.executions == ()
    assert [p.to_json()["rules"] for p in document.policies] == [
        [{"id": "langfuse-secret-key", "kind": "pattern", "scope": "object"}]]
    released = _rows(root)
    assert len(released) == 20 and sorted(r["source_key"] for r in released) == sorted(r["source_key"] for r in before)
    selected = [json.loads(line) for line in (root / "raw" / "members.jsonl").read_text().splitlines()]
    stored = {m["sha256"].removeprefix("sha256:") for m in selected if m["disposition"] == "selected"}
    assert stored and all(any((root / "raw" / "objects").glob(f"{sha[:2]}/{sha}.*")) for sha in stored)
    assert not any((root / "raw" / "objects").glob(f"{working['container'][:2]}/{working['container']}.*"))
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_or_deposited_byte_holds_the_key(working, tmp_path):
    import release_support as rs

    _seal(working)
    root = working["root"]
    holding = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and _decoded_holds(p.read_bytes()))
    assert holding == []  # names only
    sidecar = root.with_name("c.withheld")
    assert any(_decoded_holds(p.read_bytes()) for p in sidecar.rglob("*") if p.is_file())
    rs.build([root], tmp_path / "deposit")
    assert not any(_decoded_holds(p.read_bytes()) for p in (tmp_path / "deposit").rglob("*") if p.is_file())


def test_withheld_json_names_the_rule_id_never_the_pattern_or_a_match(working):
    _seal(working)
    data = (working["root"] / "WITHHELD.json").read_bytes()
    assert SENTINEL not in data and b"[0-9a-f]{8}" not in data
    assert json.loads(data)["policies"][0]["profile"]["id"] == "autogen-guard-placement"
