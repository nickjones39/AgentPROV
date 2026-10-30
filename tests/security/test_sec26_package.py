"""SEC-26: ``package`` and the deposit builder under the interpreter guard, at command level (G.10 SEC-26; K.12.12(2),
(3); G.3.8; AD-16 as ruled; Q.15a; T-26).

* **Advisory corpus, seal mode** (K.12.12(3)): a working corpus imported in dev mode below 3.14.8 from an archive (a
  synthetic Inspect ``.eval``) records ``producer.interpreter_advisory``; ``agentprov package`` on a patched interpreter
  refuses it with exit 4 and the code ``ingest.interpreter.unpatched``, and writes nothing.
* **Advisory corpus, deposit mode**: ``agentprov package --deposit`` refuses a sealed corpus whose manifest records an
  advisory with exit 4 and writes no deposit.
* **Below the floor, deposit mode** (K.12.12(2)): ``package --deposit`` exits 3 before any archive is opened and writes
  nothing.
* **Below the floor, seal mode**: sealing a corpus that holds an archive container opens no archive (no zip is read
  from untrusted bytes); it is not refused (see the observation in ``sec-coverage-12c.md``).
* **Below the floor, ``verify --release``** in tree mode at the ``rederive`` level (which re-expands archives) exits 3.

Function-level tests stay where they are (``test_interpreter_guard.py::test_manifest_with_advisory_is_refused_with_exit_4``;
``tests/unit/release/test_builder.py::test_release_mode_refuses_below_the_interpreter_floor_exit_3``).
"""

from __future__ import annotations

import json
import shutil
import warnings
import zipfile
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest

from agentprov.testing import fs_guard

cli = harness.cli  # the corpus_harness fixtures, bound in this module so pytest finds them
sealed = harness.sealed

BELOW = (3, 14, 7)
RELEASE_TOML = '''title = "AgentPROV test deposit"
description_preamble = "A deposit draft built by the security tests."
keywords = ["test"]

[[creators]]
name = "Test Creator"
'''


@pytest.fixture(autouse=True)
def _package_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """``package`` reads git facts and the H.1.5(5) git guard; the tests run outside any corpus repository."""
    import seal_support as ss

    from agentprov.cli import package

    monkeypatch.setattr(package, "git_facts", lambda repo=package.REPO_ROOT: (ss.COMMIT, True))
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: True)


@pytest.fixture
def archive_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every ``zipfile.ZipFile`` opened for reading (the archive gate's only reader, ``ingest.archives.open_zip``)."""
    opened: list[str] = []
    real = zipfile.ZipFile

    class Spy(real):  # type: ignore[misc, valid-type]
        def __init__(self, file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> None:
            if mode == "r":
                opened.append(type(file).__name__)
            super().__init__(file, mode, *args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", Spy)
    return opened


def _below_the_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: BELOW)


def _inspect_working(base: Path, *, mode: str) -> Path:
    return harness.inspect_working(base, mode=mode)


def _agentharm_spec(base: Path, *, personas: bool = True) -> tuple[Path, Path]:
    """The committed ast-survey-agentharm spec, card and changes in ``base/corpora``; ``personas=False`` drops the spec's
    ``[scan]`` table (D-810) for a test of another withholding rule, whose ledger version the address rule would raise."""
    import seal_support as ss

    spec_dir = base / "corpora" / "ast-survey-agentharm"
    spec_dir.mkdir(parents=True)
    for name in ("corpus-spec.toml", "CARD.md", "CHANGES.toml"):
        shutil.copy(ss.REPO / "corpora" / "ast-survey-agentharm" / name, spec_dir / name)
    if not personas:
        text = (spec_dir / "corpus-spec.toml").read_text("utf-8")
        (spec_dir / "corpus-spec.toml").write_text(text[:text.index("\n# D-810: persona files")] + "\n", "utf-8")
    shutil.copy(ss.REPO / "corpora" / "datasheet-statements.toml", base / "corpora" / "datasheet-statements.toml")
    shutil.copytree(ss.REPO / "corpora" / "personas", base / "corpora" / "personas")  # the spec's [scan] files (D-810)
    licence = base / "LICENSE.txt"
    licence.write_bytes(b"test licence text\n")
    return spec_dir / "corpus-spec.toml", licence


def _package(cli: Any, corpus: Path, spec: Path, licence: Path) -> Any:
    return cli("package", "--corpus", str(corpus), "--corpus-version", "0.1.0", "--spec", str(spec), "--licence-file",
               f"LICENSE={licence}", "--licence-file", f"AgentHarm-LICENSE={licence}")


# ------------------------------------------------------------------------------------------------ seal mode
def test_sec26_package_refuses_an_advisory_working_corpus_with_exit_4_on_a_patched_interpreter(cli, tmp_path,
                                                                                                monkeypatch):
    from agentprov.envinfo import InterpreterUnpatchedWarning

    _below_the_floor(monkeypatch)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        corpus = _inspect_working(tmp_path, mode="dev")
    assert any(issubclass(w.category, InterpreterUnpatchedWarning) for w in caught)
    partial = corpus.with_name("c.partial")
    advisory = json.loads((partial / "corpus.json").read_text("utf-8"))["producer"]["interpreter_advisory"]
    assert advisory == {"floor": "3.14.8", "missing": ["CVE-2026-15310", "CVE-2026-19672"], "python_version": "3.14.7"}
    monkeypatch.undo()  # back on the patched interpreter that runs package
    from agentprov.cli import package

    monkeypatch.setattr(package, "git_facts", lambda repo=package.REPO_ROOT: ("0" * 40, True))
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: True)
    spec, licence = _agentharm_spec(tmp_path)
    with fs_guard.unchanged(partial):
        run = _package(cli, corpus, spec, licence)
    assert run.code == 4
    assert "ingest.interpreter.unpatched" in run.err
    assert not corpus.exists()


def test_sec26_package_below_the_floor_opens_no_archive_while_sealing(cli, tmp_path, monkeypatch, archive_spy):
    """The seal step reads stored objects and records, never an archive's members: below the floor it opens no zip
    (the guard's purpose, G.3.8), and seals. Release-mode archive reading below the floor is refused by the deposit
    builder and ``verify --release`` (tests below)."""
    corpus = _inspect_working(tmp_path, mode="release")
    spec, licence = _agentharm_spec(tmp_path)
    archive_spy.clear()
    processes: list[str] = []
    import subprocess

    real = subprocess.Popen

    class Spy(real):  # type: ignore[misc, valid-type]
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            processes.append(" ".join(map(str, args)) if isinstance(args, (list, tuple)) else str(args))
            super().__init__(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", Spy)
    _below_the_floor(monkeypatch)
    run = _package(cli, corpus, spec, licence)
    assert archive_spy == []
    assert not any("agentprov.worker" in p for p in processes), processes  # no T1 job could open one unseen
    assert run.code == 0, run.err  # pinned: seal mode is not refused below the floor (sec-coverage-12c.md, O-2)
    assert json.loads((corpus / "corpus.json").read_text("utf-8"))["producer"]["interpreter_advisory"] is None


def test_sec26_the_archive_spy_sees_an_in_process_archive_open(tmp_path, monkeypatch, archive_spy):
    """Positive control for ``archive_spy``: an in-process (dev) import of the ``.eval`` opens it through the gate."""
    _inspect_working(tmp_path, mode="dev")
    assert archive_spy


# ------------------------------------------------------------------------------------------------ deposit mode
def _deposit_args(out: Path, metadata: Path, corpus: Path) -> list[str]:
    return ["package", "--deposit", str(out), "--metadata", str(metadata), "--release-date", "2026-10-11", "--corpus",
            str(corpus)]


def _with_scan(root: Path) -> None:
    import release_support as rs

    from agentprov.corpus.integrity import root_digest
    from agentprov.release.builder import scan_path_for

    scan_path_for(root).write_text(json.dumps(rs.scan_document(root, root_digest(root))))


@pytest.fixture
def metadata(tmp_path: Path) -> Path:
    path = tmp_path / "release.toml"
    path.write_text(RELEASE_TOML)
    return path


def test_sec26_the_deposit_control_builds_on_a_patched_interpreter(cli, sealed, tmp_path, metadata):
    """Control: the same deposit invocation succeeds without the advisory and above the floor."""
    _with_scan(sealed)
    out = tmp_path / "deposit"
    run = cli(*_deposit_args(out, metadata, sealed))
    assert run.code == 0, run.err
    assert any(out.glob("*.zip"))


def test_sec26_package_deposit_refuses_a_sealed_corpus_that_records_an_advisory_with_exit_4(cli, sealed, tmp_path,
                                                                                            metadata):
    import release_support as rs

    rs.restamp(sealed, lambda m: m["producer"].update(interpreter_advisory={
        "floor": "3.14.8", "missing": ["CVE-2026-15310", "CVE-2026-19672"], "python_version": "3.14.7"}))
    _with_scan(sealed)
    out = tmp_path / "deposit"
    with fs_guard.unchanged(sealed):
        run = cli(*_deposit_args(out, metadata, sealed))
    assert run.code == 4 and "ingest.interpreter.unpatched" in run.err
    assert not out.exists() or not any(out.iterdir())


def test_sec26_package_deposit_below_the_floor_exits_3_before_any_archive_is_opened(cli, sealed, tmp_path, metadata,
                                                                                     monkeypatch, archive_spy):
    _with_scan(sealed)
    out = tmp_path / "deposit"
    _below_the_floor(monkeypatch)
    with fs_guard.unchanged(sealed):
        run = cli(*_deposit_args(out, metadata, sealed))
    assert run.code == 3 and "ingest.interpreter.unpatched" in run.err
    assert archive_spy == [] and not out.exists()


# ------------------------------------------------------------------------------------------------ verify --release
def test_sec26_verify_release_rederive_below_the_floor_exits_3_before_reading(cli, sealed, monkeypatch, archive_spy):
    from corpus_harness import verify

    import verify_support as vs

    digest = vs.root_digest(sealed)
    _below_the_floor(monkeypatch)
    with fs_guard.unchanged(sealed):
        run = verify(cli, sealed, "--level", "rederive", "--release", "--root-digest", digest)
    assert run.code == 3 and archive_spy == []
