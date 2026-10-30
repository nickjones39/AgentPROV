"""``agentprov package --deposit`` (MN N.2.11 deposit mode; HL H.10, HL-T9; D-42; exit codes N.1.3).

Sealed test corpora (``tests/unit/release/release_support``) with a release scan beside them (as
``tools/release_scan.py`` writes it) are deposited through the CLI. Checked: exit 0, the closing "nothing has been
uploaded or published" line and a valid summary; the usage errors (no ``--metadata``, no ``--release-date``, a seal-mode
flag, a malformed ``release.toml``); exit 4 for a missing scan and for mixed licence classes, exit 0 with the flag; a dry
run writes nothing; the git guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_UNIT = Path(__file__).resolve().parents[1] / "unit"
for _path in (_UNIT / "raw", _UNIT / "corpus", _UNIT / "release"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import release_support as rs  # noqa: E402

from agentprov.corpus.integrity import root_digest  # noqa: E402
from agentprov.release.builder import scan_path_for  # noqa: E402

RELEASE_TOML = '''title = "AgentPROV test deposit"
description_preamble = "A deposit draft built by the CLI tests."
keywords = ["test"]

[[creators]]
name = "Test Creator"
'''


@pytest.fixture
def setup(tmp_path_factory, tmp_path, monkeypatch):
    from agentprov.cli import package

    monkeypatch.setattr(package, "git_facts", lambda repo=package.REPO_ROOT: (rs.PRODUCER.git_commit, True))
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: True)
    metadata = tmp_path / "release.toml"
    metadata.write_text(RELEASE_TOML)

    def corpus(corpus_id: str = "mini-mit", derived: str = "inherit") -> Path:
        root = rs.sealed(tmp_path_factory, tmp_path / "corpora", corpus_id, derived)
        scan_path_for(root).write_text(json.dumps(rs.scan_document(root, root_digest(root))))
        return root

    return corpus, metadata


def _args(out: Path, metadata: Path, *corpora: Path) -> list[str]:
    args = ["package", "--deposit", str(out), "--metadata", str(metadata), "--release-date", "2026-10-11"]
    for corpus in corpora:
        args += ["--corpus", str(corpus)]
    return args


def test_deposit_mode_writes_a_draft_and_says_nothing_was_published(cli, setup, tmp_path, check_summary):
    corpus, metadata = setup
    root = corpus()
    run = cli(*_args(tmp_path / "out", metadata, root), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"]["archives"] == 5 and summary["counters"]["corpora"] == 1
    assert "Nothing has been uploaded or published." in run.err
    assert f"root digest {root_digest(root)}" in run.err
    assert (tmp_path / "out" / "DEPOSIT-MANIFEST.json").is_file()
    meta = json.loads((tmp_path / "out" / "deposit-metadata.json").read_text())
    assert meta["software"]["git_commit"] == rs.PRODUCER.git_commit and meta["status"] == "draft-unpublished"


def test_the_deposit_summary_writes_paths_under_home_as_home(cli, setup, tmp_path, monkeypatch):
    # CC-21: no literal home path in the deposit summary either (N.1.12(7))
    corpus, metadata = setup
    root = corpus()
    monkeypatch.setenv("HOME", str(tmp_path))
    run = cli(*_args(tmp_path / "out", metadata, root), "--json")
    assert run.code == 0, run.err
    assert str(tmp_path) not in run.out and str(tmp_path) not in run.err


def test_two_cli_builds_are_byte_identical(cli, setup, tmp_path):
    corpus, metadata = setup
    root = corpus()
    assert cli(*_args(tmp_path / "a", metadata, root)).code == 0
    assert cli(*_args(tmp_path / "b", metadata, root)).code == 0
    assert rs.tree_bytes(tmp_path / "a") == rs.tree_bytes(tmp_path / "b")


def test_usage_errors_exit_2(cli, setup, tmp_path):
    corpus, metadata = setup
    root = corpus()
    out = tmp_path / "out"
    assert cli("package", "--deposit", str(out), "--corpus", str(root), "--release-date", "2026-10-11").code == 2
    assert cli("package", "--deposit", str(out), "--corpus", str(root), "--metadata", str(metadata)).code == 2
    assert cli(*_args(out, metadata, root)[:-2], "--corpus", str(root), "--corpus-version", "0.1.0").code == 2
    assert cli("package", "--deposit", str(out), "--corpus", str(root), "--metadata", str(metadata),
               "--release-date", "11/10/2026").code == 2
    assert cli("package", "--corpus", str(root), "--metadata", str(metadata)).code == 2  # deposit flags without --deposit
    bad = tmp_path / "bad.toml"
    bad.write_text("title = 1\n")
    assert cli(*_args(out, bad, root)).code == 2
    assert not out.exists()


def test_a_release_date_past_the_zip_range_is_usage_exit_2(cli, setup, tmp_path):
    # CB-19: ZIP member timestamps end at 2107; a later date used to pass --dry-run and crash the real build (exit 70)
    corpus, metadata = setup
    root = corpus()
    out = tmp_path / "out"
    args = [a if a != "2026-10-11" else "2108-01-01" for a in _args(out, metadata, root)]
    for extra in ((), ("--dry-run",)):
        run = cli(*args, *extra, "--json")
        assert run.code == 2, run.err
        assert run.json()["outcome"] == "usage" and "2107" in run.err
    assert not out.exists() and not list(tmp_path.glob("out*"))


def test_a_missing_scan_is_refused_exit_4(cli, setup, tmp_path):
    corpus, metadata = setup
    root = corpus()
    scan_path_for(root).unlink()
    run = cli(*_args(tmp_path / "out", metadata, root), "--json")
    assert run.code == 4 and run.json()["outcome"] == "refused"
    assert not (tmp_path / "out").exists()


def test_mixed_licence_classes_exit_4_and_the_flag_admits_them(cli, setup, tmp_path):
    corpus, metadata = setup
    mit, gpl = corpus("mini-mit"), corpus("mini-gpl", "GPL-3.0-only")
    assert cli(*_args(tmp_path / "out", metadata, mit, gpl)).code == 4
    assert not (tmp_path / "out").exists()
    run = cli(*_args(tmp_path / "out", metadata, mit, gpl), "--allow-mixed-licence-classes")
    assert run.code == 0, run.err
    assert "licence classes are mixed" in run.err


def test_dry_run_writes_nothing(cli, setup, tmp_path):
    corpus, metadata = setup
    run = cli(*_args(tmp_path / "out", metadata, corpus()), "--dry-run", "--json")
    assert run.code == 0 and run.json()["dry_run"] is True
    assert "would write" in run.err and not (tmp_path / "out").exists()


def test_the_draft_is_kept_out_of_git(cli, setup, tmp_path, monkeypatch):
    from agentprov.cli import package

    corpus, metadata = setup
    root = corpus()
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: False)
    assert cli(*_args(tmp_path / "repo" / "out", metadata, root)).code == 4
    # CC-20: a dry run is refused like the real run (the guard is read-only; it used to be skipped under --dry-run)
    assert cli(*_args(tmp_path / "repo" / "out", metadata, root), "--dry-run").code == 4
