"""The ``code-agent-misalignment-geminicli`` ``[withhold]`` rule, end to end with no injection (D-336; D-234..D-236).

The policy is read from the shipped profile everywhere it is read (the import worker, sealing, ``verify --level chain``
and the deposit builder): nothing is monkeypatched. The archive input is a zstd tar assembled at test time (never
committed) in the layout of Zenodo 20404563: two committed fixture rollouts (unedited) and one rollout whose stream
carries, in one tool output, a test-made sentinel of the Google API key shape (assembled at run time, never printed; the
deposit's own value is never used or written). Checked:

* import (release mode, archive input with a Zenodo test pin) -> seal (release) withholds the sentinel stream (basis
  ``profile_rule``, scope ``executions``), its one execution, and the tar (basis ``container``); the two clean
  executions stay released;
* ``verify --level chain --release`` passes on the sealed corpus (the D-236 backstop re-applies the profile's rule);
* no sealed or deposited byte holds the sentinel; the private sidecar does; ``WITHHELD.json`` names the rule id only;
* the release secret scan (gitleaks) finds nothing in the sealed corpus, while the same scan over the sidecar finds the
  sentinel (the control); skipped when gitleaks is not installed;
* D-450 (bug pass BF-18), the D.23.7 shape: the sentinel only in a ``claude_code`` file the profile does not select (so
  never decompressed at import, and never literally in the zstd bytes). Sealing reads the tar decoded and withholds it
  (basis ``profile_rule``, detector ``agentprov-withhold-decoded/1``, object level); the three executions stay
  released, ``chain`` passes, and no sealed or deposited file holds the tar.
* D-609, the harness account path (pre-check PC-code-agent-misalignment-01): one rollout's ``final_diff.patch`` carries
  the harness's ``diff -r`` header lines with a made-up workstation account (assembled at run time), and the README
  names that account's home. Sealing withholds the patch and the README at object level (reason ``personal_data``, basis
  ``profile_rule``, no affected execution) and the tar as their container; all three executions stay released, ``chain
  --release`` passes, no sealed or deposited byte holds the path and the private sidecar does. A second rollout's patch
  with an agent-written placeholder home path (another made-up name) is not the harness form and stays sealed.
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
              _TESTS / "adapters" / "geminicli", _TESTS.parent / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import corpus_harness as harness  # noqa: E402
import format_support  # noqa: E402
import geminicli_support as support  # noqa: E402
import verify_support as vs  # noqa: E402
from corpus_harness import verify  # noqa: E402

cli = harness.cli

PROFILE = support.PROFILE
PIN_FILE = "RESULTS_raw.tar.zst"
DOI = "10.5281/zenodo.1"
SPEC = f'''corpus_id = "geminicli-test"
corpus_version = "0.1.0"
title = "gemini-cli rollouts with a test-made key-shaped sentinel (test corpus)"
mode = "import"

[[sources]]
source_id = "{PROFILE}"
profile = "{PROFILE}@2"
parts = ["results-raw"]

[[sources.snapshots]]
snapshot_id = "results-raw"
origin = {{ kind = "zenodo", doi = "{DOI}", file = "{PIN_FILE}" }}
alt_origins = []
raw_policy = "include"

[derive]
sem_profiles = ["geminicli.tools@1"]
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

A test corpus of gemini-cli rollouts.

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
#: A test-made value of the Google API key shape (never a deposited value): the prefix and 35 key characters.
SENTINEL = ("AI" + "za" + "SyTEST0SENTINEL0phase10o0geminicli0").encode()
assert len(SENTINEL) == 39


def _holds(data: bytes) -> bool:
    return SENTINEL in data


def _with_result() -> list[str]:
    """Fixture rollouts whose stream ends with a result event, ``ok`` first. Aborted runs are left out until D-372 lands:
    on main the importer and ``verify --level chain`` read an I-class ``incomplete_run`` differently, so a seal holding one
    fails its own chain check (a core defect, docs/reports/phase10o/README.md §10)."""
    found = [d for d in support.streams().values() if any(e["type"] == "result" for e in support.events(d))]
    found.sort(key=lambda d: (d != support.by_criterion("ok_with_text_and_calls"), d))
    assert len(found) >= 3
    return found


def _archive(path: Path) -> tuple[dict[str, Any], str]:
    """The test tar.zst; returns its pin and the sha256 of the sentinel stream."""
    planted_dir, *clean = _with_result()[:3]
    members: dict[str, bytes] = {}
    for d in (*clean, planted_dir):
        members.update(support.files_of(d))
    events = support.events(planted_dir)
    result = next(e for e in events if e["type"] == "tool_result" and isinstance(e.get("output"), str))
    result["output"] = "GOOGLE_API_KEY=" + SENTINEL.decode() + "\n" + result["output"]
    stream = support.jsonl(events)
    members[f"{planted_dir}/gemini_stream.jsonl"] = stream
    rows = [support.manifest_for(d).decode().split("\r\n")[1] for d in (*clean, planted_dir)]
    members["RESULTS_build/manifest.csv"] = (support.MANIFEST_HEADER + "\r\n" + "\r\n".join(rows) + "\r\n").encode()
    members["RESULTS_build/README.md"] = b"test\n"
    assert not any(_holds(v) for k, v in members.items() if k != f"{planted_dir}/gemini_stream.jsonl")
    data = format_support.tzst(sorted(members.items()))
    path.write_bytes(data)
    pin = {"role": "runs", "part": "results-raw", "primary": True, "kind": "zenodo", "doi": DOI, "record": 1,
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "bytes": len(data)}
    return pin, hashlib.sha256(stream).hexdigest()


@pytest.fixture(scope="module")
def working_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed gemini-cli fixtures are absent")
    base = tmp_path_factory.mktemp("geminicli-withhold")
    pin, planted = _archive(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["size"])
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, tree, corpus=writer, profile_id=PROFILE, part="results-raw", pin=pin,
                               workers=1, mode="release")
    assert report.exit_code == 0, report.counters
    assert report.counters["mapped"] == 3 and report.counters["degenerate"] == 0
    return {"partial": base / "c.partial", "planted": planted, "container": pin["sha256"]}


def _unselected_archive(path: Path) -> dict[str, Any]:
    """The test tar.zst with clean streams only, and the sentinel in an unselected ``claude_code`` transcript (D.23.7)."""
    dirs = _with_result()[:3]
    members: dict[str, bytes] = {}
    for d in dirs:
        members.update(support.files_of(d))
    rows = [support.manifest_for(d).decode().split("\r\n")[1] for d in dirs]
    members["RESULTS_build/manifest.csv"] = (support.MANIFEST_HEADER + "\r\n" + "\r\n".join(rows) + "\r\n").encode()
    members["RESULTS_build/README.md"] = b"test\n"
    assert not any(_holds(v) for v in members.values())
    cell, run = dirs[0].rsplit("/", 2)[-2:]
    hidden = f"RESULTS_build/cells/claude_code__{cell.split('__', 1)[1]}/{run}/transcript.jsonl"
    members[hidden] = b'{"env": "GOOGLE_API_KEY=' + SENTINEL + b'"}\n'
    data = format_support.tzst(sorted(members.items()))
    assert not _holds(data)  # compressed: the stored tar never holds it literally
    path.write_bytes(data)
    return {"role": "runs", "part": "results-raw", "primary": True, "kind": "zenodo", "doi": DOI, "record": 1,
            "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "bytes": len(data)}


@pytest.fixture(scope="module")
def unselected_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed gemini-cli fixtures are absent")
    base = tmp_path_factory.mktemp("geminicli-withhold-unselected")
    pin = _unselected_archive(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["size"])
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, tree, corpus=writer, profile_id=PROFILE, part="results-raw", pin=pin,
                               workers=1, mode="release")
    assert report.exit_code == 0 and report.counters["mapped"] == 3, report.counters
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

    package = resources.files("agentprov").joinpath("adapters", "geminicli")
    node = package.joinpath("semantics", "geminicli.tools-1")
    return SealInputs(
        spec=SPEC.encode(),
        card=CARD.encode(),
        changes=CHANGES.encode(),
        statements=load_statements((_TESTS.parent / "corpora" / "datasheet-statements.toml").read_bytes()),
        source_profile=package.joinpath("profiles", f"{PROFILE}.profile.toml").read_bytes(),
        semantics_profiles={"geminicli.tools@1": {c.name: c.read_bytes() for c in sorted(node.iterdir(), key=lambda c: c.name)
                                                  if c.is_file()}},
        licence_files={"LICENSE": LicenceFile(b"test licence text\n", "supplied at sealing (test)")},
        producer=ProducerFacts(git_commit="0123456789abcdef0123456789abcdef01234567", git_tree_clean=True,
                               distributions_sha256="sha256:" + "0" * 64, zlib_version="1.2.12"),
        checker=CHECKER,
        registry_date="2026-10-11",
    )


def _seal(working: dict[str, Any], **kwargs: Any) -> Any:
    from agentprov.corpus.package import ReleaseArgs, seal

    return seal(working["root"], corpus_version="0.1.0", inputs=_inputs(), release=ReleaseArgs(release_date="2026-10-14"),
                **kwargs)


def _rows(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines()]


def test_the_shipped_profile_withholds_the_sentinel_rollout(cli, working):
    from agentprov.corpus.withheld import decode_withheld

    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_executions"] == 1
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    by_sha = {e.sha256: e for e in document.entries}
    entry = by_sha[working["planted"]]
    assert (entry.reason, entry.basis) == ("secret", "profile_rule")
    assert entry.finding is not None and entry.finding.rule.startswith(f"{PROFILE}@2:")
    assert by_sha[working["container"]].basis == "container"
    assert {e.basis for e in document.entries} == {"profile_rule", "container"}
    assert [p.to_json()["rules"] for p in document.policies] == [[
        {"id": "deposit-readme-account-path", "kind": "pattern", "scope": "object"},
        {"id": "google-api-key-shape", "kind": "pattern", "scope": "executions"},
        {"id": "harness-account-path", "kind": "pattern", "scope": "object"}]]
    assert len(document.executions) == 1
    released = _rows(root)
    assert len(released) == 2  # the two clean fixture rollouts
    assert not {r["source_key"].split("#", 1)[0].removeprefix("sha256:") for r in released} & {working["planted"]}
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()


def test_no_sealed_or_deposited_byte_holds_the_sentinel(working, tmp_path):
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
def test_the_release_secret_scan_finds_no_key_in_the_sealed_corpus(working):
    import release_scan

    from agentprov.adapters.profiles import load_profile

    scan_rules = set(load_profile(PROFILE).data["withhold"]["scan_rules"])
    _seal(working)
    root = working["root"]
    executable = str(shutil.which("gitleaks"))
    document = release_scan.scan(root, gitleaks=executable, needles={})
    assert [f for f in document["findings"] if f["rule"] in scan_rules] == []
    control, _resolved = release_scan.run_gitleaks(executable, root.with_name("c.withheld"))
    assert any(f.rule in scan_rules for f in control)


def test_withheld_json_names_rule_ids_never_a_pattern_or_match(working):
    _seal(working)
    data = (working["root"] / "WITHHELD.json").read_bytes()
    assert not _holds(data)
    assert b"AIza[" not in data  # the profile's rule stays in the profile
    assert json.loads(data)["policies"][0]["profile"]["id"] == PROFILE


def test_a_key_in_an_unselected_member_withholds_the_tar_d450(cli, unselected_template, tmp_path):
    import release_support as rs

    from agentprov.corpus.withheld import decode_withheld

    partial = tmp_path / "c.partial"
    shutil.copytree(unselected_template["partial"], partial, symlinks=True)
    working = {"root": tmp_path / "c", "partial": partial}
    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_executions"] == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    (entry,) = document.entries
    assert entry.sha256 == unselected_template["container"]
    assert (entry.reason, entry.basis, entry.affected_executions) == ("secret", "profile_rule", ())
    assert entry.finding is not None and entry.finding.detector == "agentprov-withhold-decoded/1"
    assert entry.finding.rule == f"{PROFILE}@2:google-api-key-shape"
    assert len(_rows(root)) == 3
    sealed = {p.name.split(".", 1)[0] for p in (root / "raw").rglob("*") if p.is_file()}
    assert unselected_template["container"] not in sealed
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
    rs.build([root], tmp_path / "deposit")
    assert not any(p.name.startswith(unselected_template["container"]) for p in (tmp_path / "deposit").rglob("*"))


# ------------------------------------------------------------------------------------------------ D-609 account path
#: A made-up workstation account and a made-up placeholder name (neither generic, neither a deposited name), assembled at
#: run time so no committed byte spells the path.
ACCOUNT = "q" + "z" + "x"
PLACEHOLDER = "w" + "v" + "k"
ACCOUNT_HOME = f"/home/{ACCOUNT}/".encode()


def _harness_patch(run: str) -> bytes:
    """A ``final_diff.patch`` in the harness's ``diff -r`` form: header lines naming the work root, then a hunk."""
    root = f"/home/{ACCOUNT}/jss_agent_work/{run}"
    return (f"diff -r {root}/before/app/settings.py {root}/after/app/settings.py\n"
            "--- a/app/settings.py\n+++ b/app/settings.py\n@@ -1,2 +1,2 @@\n-DEBUG = False\n+DEBUG = True\n").encode()


def _placeholder_patch() -> bytes:
    """An agent-written line with a placeholder home path: not the harness header form (synthetic-benchmark)."""
    return (f"--- a/tools/paths.py\n+++ b/tools/paths.py\n@@ -1 +1 @@\n-BASE = '.'\n"
            f"+BASE = '/home/{PLACEHOLDER}/projects/app'\n").encode()


def _account_archive(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """The test tar.zst for D-609; returns its pin and the sha256 of the harness patch, the README and the placeholder
    patch."""
    planted_dir, placeholder_dir, clean_dir = _with_result()[:3]
    members: dict[str, bytes] = {}
    for d in (planted_dir, placeholder_dir, clean_dir):
        members.update(support.files_of(d))
    assert not any(ACCOUNT_HOME in v for v in members.values())
    patch = _harness_patch(planted_dir.rsplit("/", 1)[-1])
    members[f"{planted_dir}/final_diff.patch"] = patch
    placeholder = _placeholder_patch()
    members[f"{placeholder_dir}/final_diff.patch"] = placeholder
    readme = f"# Raw rollouts\n\nBuilt on a workstation. Source: /home/{ACCOUNT}/TempXy/results/RESULTS_build\n".encode()
    members["RESULTS_build/README.md"] = readme
    rows = [support.manifest_for(d).decode().split("\r\n")[1] for d in (planted_dir, placeholder_dir, clean_dir)]
    members["RESULTS_build/manifest.csv"] = (support.MANIFEST_HEADER + "\r\n" + "\r\n".join(rows) + "\r\n").encode()
    data = format_support.tzst(sorted(members.items()))
    assert ACCOUNT_HOME not in data  # compressed
    path.write_bytes(data)
    pin = {"role": "runs", "part": "results-raw", "primary": True, "kind": "zenodo", "doi": DOI, "record": 1,
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "bytes": len(data)}
    digests = {"patch": hashlib.sha256(patch).hexdigest(), "readme": hashlib.sha256(readme).hexdigest(),
               "placeholder": hashlib.sha256(placeholder).hexdigest()}
    return pin, digests


@pytest.fixture(scope="module")
def account_template(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter

    if not (support.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed gemini-cli fixtures are absent")
    base = tmp_path_factory.mktemp("geminicli-withhold-account")
    pin, digests = _account_archive(base / PIN_FILE)
    tree = ArchiveTree(base / PIN_FILE, pin=pin, sha256=pin["sha256"], size=pin["size"])
    with CorpusWriter(base / "c") as writer:
        report = import_source(PROFILE, tree, corpus=writer, profile_id=PROFILE, part="results-raw", pin=pin,
                               workers=1, mode="release")
    assert report.exit_code == 0 and report.counters["mapped"] == 3, report.counters
    return {"partial": base / "c.partial", "container": pin["sha256"], **digests}


def test_the_harness_account_path_withholds_the_patch_and_readme_only_d609(cli, account_template, tmp_path):
    import release_support as rs

    from agentprov.corpus.withheld import decode_withheld

    partial = tmp_path / "c.partial"
    shutil.copytree(account_template["partial"], partial, symlinks=True)
    working = {"root": tmp_path / "c", "partial": partial}
    stored = {p.name.split(".", 1)[0] for p in (partial / "raw" / "objects").rglob("*") if p.is_file()}
    assert {account_template["patch"], account_template["readme"], account_template["placeholder"]} <= stored
    report = _seal(working)
    root = working["root"]
    assert report.counters["withheld_executions"] == 0
    document = decode_withheld((root / "WITHHELD.json").read_bytes())
    by_sha = {e.sha256: e for e in document.entries}
    assert set(by_sha) == {account_template["patch"], account_template["readme"], account_template["container"]}
    for key, rule in (("patch", "harness-account-path"), ("readme", "deposit-readme-account-path")):
        entry = by_sha[account_template[key]]
        assert (entry.reason, entry.basis, entry.affected_executions) == ("personal_data", "profile_rule", ())
        assert entry.finding is not None and entry.finding.rule == f"{PROFILE}@2:{rule}"
        assert "D-609" in entry.public_note
    assert by_sha[account_template["container"]].basis == "container"
    assert document.executions == ()
    assert len(_rows(root)) == 3  # every execution released
    sealed = {p.name.split(".", 1)[0] for p in (root / "raw").rglob("*") if p.is_file()}
    assert account_template["placeholder"] in sealed  # the agent-written placeholder is not the harness form
    assert not {account_template["patch"], account_template["readme"], account_template["container"]} & sealed
    holding = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ACCOUNT_HOME in p.read_bytes())
    assert holding == []  # names only
    data = (root / "WITHHELD.json").read_bytes()
    assert ACCOUNT_HOME not in data and b"jss_agent_work" not in data and ACCOUNT.encode() not in data
    sidecar = root.with_name("c.withheld")
    assert any(ACCOUNT_HOME in p.read_bytes() for p in sidecar.rglob("*") if p.is_file())
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
    rs.build([root], tmp_path / "deposit")
    assert not any(ACCOUNT_HOME in p.read_bytes() for p in (tmp_path / "deposit").rglob("*") if p.is_file())
