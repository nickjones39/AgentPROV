"""SEC-15: downloaded deposits and tree-mode path safety (G.10 SEC-15; K.12.15; HL H.5.5 "Inputs are opened safely";
R-44, AD-14; T-07, T-13, T-21).

* **Archive mode** reads deposit zips without extraction: no extraction API is reached, and nothing is written anywhere
  (the deposit, the source corpus, the working directory and ``$AGENTPROV_HOME`` are guarded unchanged).
* **Tree mode**: a symlinked raw object, shard directory or execution file is refused without being followed, and a
  ``../`` or absolute relpath in ``checksums.sha256``, an index row, the manifest's ``files``, a rule catalogue or a
  semantics profile entry is refused before it is opened. Every case keeps a sentinel file outside the corpus, at the
  place the hostile path points to, and an audit hook (``corpus_harness.OpenSpy``) proves it was never opened.
* **Deposit names**: a member named ``<prefix>/../x`` or with an absolute name, an archive name with ``../`` in the
  deposit manifest, and a symlinked archive.
* **Swapped ``rules/``** and a **missing catalogue version**, through a deposit read in archive mode: ``rules.mismatch``
  fails, ``rules.unavailable`` is ``unverified`` (dev mode passes it with the finding listed; release mode fails).

The phase-11 tests in ``tests/corpus/test_deposit_verify.py`` cover the other archive-mode rows (flipped member and
stream bytes, replaced and added members, unlisted files, edited deposit manifest, lone meta archive, consistent
forgery against the published root digest); ``tests/corpus/test_tamper.py`` covers the swapped ``rules/`` copy in tree
mode.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest
import release_support as rs
import verify_support as vs
from corpus_harness import OpenSpy, sentinel, verify

from agentprov.testing import fs_guard

cli = harness.cli  # the fixtures of corpus_harness, bound in this module so pytest finds them
sealed = harness.sealed


def _deposit(sealed_root: Path, out: Path) -> Path:
    rs.build([sealed_root], out)
    return out


def _archive(out: Path, stage: str) -> Path:
    return next(p for p in sorted(out.glob("*.zip")) if f".{stage}" in p.name)


def _rewrite(path: Path, change: Any, extra: dict[str, bytes] | None = None) -> None:
    """Rewrite a zip with the builder's member settings; ``change(name, data) -> bytes | None`` (None drops it)."""
    with zipfile.ZipFile(path) as source:
        members = [(info, source.read(info)) for info in source.infolist()]
    path.unlink()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=False) as sink:
        for info, data in members:
            new = change(info.filename, data)
            if new is not None:
                sink.writestr(info, new)
        for name, data in (extra or {}).items():
            sink.writestr(zipfile.ZipInfo(name, date_time=(2026, 10, 11, 0, 0, 0)), data)


# ------------------------------------------------------------------------------------------------ the spy itself
def test_sec15_the_open_spy_records_an_open_of_a_sentinel_and_nothing_else(tmp_path):
    """Positive control: without it, every ``spy.events == []`` below could pass vacuously."""
    target = sentinel(tmp_path, b"{}")
    other = tmp_path / "plain.json"
    other.write_bytes(b"{}")
    with OpenSpy() as spy:
        other.read_bytes()
        fd = os.open(target, os.O_RDONLY)
        os.close(fd)
        target.read_bytes()
    assert len(spy.events) == 2 and all(e.startswith("open ") for e in spy.events)
    target.read_bytes()
    assert len(spy.events) == 2  # inert outside the spy


# ------------------------------------------------------------------------------------------------ archive mode
def test_sec15_archive_mode_reaches_no_extraction_api_and_writes_nothing_anywhere(cli, sealed, tmp_path, monkeypatch):
    out = _deposit(sealed, tmp_path / "deposit")
    home = Path(os.environ["AGENTPROV_HOME"])
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an extraction API was reached")

    monkeypatch.setattr(zipfile.ZipFile, "extract", refuse)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", refuse)
    monkeypatch.setattr(shutil, "unpack_archive", refuse)
    monkeypatch.setattr("tempfile.mkdtemp", refuse)
    with fs_guard.unchanged(out), fs_guard.unchanged(sealed), fs_guard.unchanged(work), fs_guard.unchanged(home):
        for level in ("checksums", "chain"):
            run = verify(cli, out, "--level", level)
            assert run.code == 0, run.err
            assert run.json()["notices"][0].startswith("archive mode (deposit directory)")
        meta = _archive(out, "meta")
        assert verify(cli, meta, "--level", "chain").code == 0


# ------------------------------------------------------------------------------------------------ tree mode: links
def _first_object(root: Path) -> str:
    return sorted(p.relative_to(root).as_posix() for p in (root / "raw" / "objects").rglob("*") if p.is_file())[0]


def test_sec15_a_symlinked_raw_object_is_refused_and_never_followed(cli, sealed, tmp_path):
    label = _first_object(sealed)
    target = sentinel(tmp_path, (sealed / label).read_bytes())  # identical bytes: only the link itself is wrong
    (sealed / label).unlink()
    os.symlink(target, sealed / label)
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "checksums")
        assert run.code == 1 and run.codes() == {"checksums.unreadable": 1, "corpus.tree.link": 1}
        run = verify(cli, sealed, "--level", "chain")
        assert run.code == 1 and {"checksums.unreadable", "corpus.tree.link", "raw.object.missing"} <= set(run.codes())
    assert spy.events == []
    with pytest.raises(Exception) as refused:  # the attacker cannot re-seal a tree that holds a link
        vs.regenerate_checksums(sealed)
    assert getattr(refused.value, "code", "") == "corpus.integrity.not_closed"


def test_sec15_a_symlinked_checksums_file_is_a_finding_and_never_followed(cli, sealed, tmp_path):
    # CB-12: the link is reported as checksums.unreadable (exit 1 with the report), never an uncaught IngestError, and
    # a published root digest cannot be compared with it.
    data = (sealed / "checksums.sha256").read_bytes()
    target = sentinel(tmp_path, data)  # identical bytes: only the link itself is wrong
    (sealed / "checksums.sha256").unlink()
    os.symlink(target, sealed / "checksums.sha256")
    published = "sha256:" + hashlib.sha256(data).hexdigest()
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "checksums", "--root-digest", published)
        assert run.code == 1 and {"checksums.unreadable", "root_digest.unverifiable"} <= set(run.codes()), run.err
        run = verify(cli, sealed, "--level", "chain")
        assert run.code == 1 and "checksums.unreadable" in run.codes(), run.err
        assert run.json()["corpus"] is not None
    assert spy.events == []


def test_sec15_a_symlinked_shard_directory_is_refused_and_never_followed(cli, sealed, tmp_path):
    shard = (sealed / _first_object(sealed)).parent
    moved = tmp_path / f"{harness.SENTINEL}-dir"
    shutil.move(shard, moved)
    os.symlink(moved, shard)
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and {"checksums.unreadable", "corpus.tree.link", "raw.object.missing"} <= set(run.codes())
    assert spy.events == []


def test_sec15_a_symlinked_execution_file_is_refused_and_never_followed(cli, sealed, tmp_path):
    aer = sorted((sealed / "aer").rglob("*.aer.jsonl"))[0]
    target = sentinel(tmp_path, aer.read_bytes())
    aer.unlink()
    os.symlink(target, aer)
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and {"checksums.unreadable", "corpus.tree.link", "corpus.read.aer"} <= set(run.codes())
    assert spy.events == []


# ------------------------------------------------------------------------------------------------ tree mode: relpaths
HOSTILE = [pytest.param("../../{name}", id="dotdot"), pytest.param("{abs}", id="absolute"),
           pytest.param("rules/../../../{name}", id="inner-dotdot")]


def _hostile(pattern: str, target: Path) -> str:
    return pattern.format(name=target.name, abs=str(target))


@pytest.mark.parametrize("pattern", HOSTILE)
def test_sec15_a_hostile_relpath_in_checksums_is_refused_before_it_is_opened(cli, sealed, tmp_path, pattern):
    target = sentinel(tmp_path, b"{}")
    line = f"{hashlib.sha256(b'{}').hexdigest()}  {_hostile(pattern, target)}\n".encode()
    path = sealed / "checksums.sha256"
    lines = sorted([line, *path.read_bytes().splitlines(keepends=True)], key=lambda b: b[66:])
    path.write_bytes(b"".join(lines))
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and "checksums.path_invalid" in run.codes()
    assert all(f["subject"]["path"].startswith("#") for f in run.json()["failures"]
               if f["code"] == "checksums.path_invalid")  # the refused path is named by line, never echoed
    assert spy.events == []


@pytest.mark.parametrize("pattern", HOSTILE)
def test_sec15_a_hostile_relpath_in_an_index_row_is_refused_before_it_is_opened(cli, sealed, tmp_path, pattern):
    target = sentinel(tmp_path, b"{}")
    items = vs.rows(sealed)
    items[0]["paths"]["aer"] = _hostile(pattern, target)
    vs.write_jsonl(sealed / "executions.jsonl", items)
    vs.regenerate_checksums(sealed)
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1 and "index.invalid" in run.codes()
    assert spy.events == []


@pytest.mark.parametrize("member", ["files", "catalogue", "semantics", "source_profile"])
@pytest.mark.parametrize("pattern", HOSTILE)
def test_sec15_a_hostile_relpath_in_the_manifest_is_refused_before_it_is_opened(cli, sealed, tmp_path, pattern, member):
    """A consistent forgery (manifest content digest and checksums regenerated) whose manifest points a file reference
    outside the corpus: refused by the grammar (``manifest.invalid`` / ``manifest.files``) or compared as an absent
    ``rules/`` copy (``rules.mismatch``); the sentinel at the target is never opened."""
    target = sentinel(tmp_path, (sealed / "rules" / "agentdojo.rules.toml").read_bytes())
    hostile = _hostile(pattern, target)

    def change(m: dict[str, Any]) -> None:
        if member == "files":
            m["files"]["card"]["path"] = hostile
        elif member == "catalogue":
            next(e for e in m["rule_catalogues"] if e["id"] == "agentdojo")["path"] = hostile
        elif member == "semantics":
            m["profiles"]["semantics"][0]["paths"] = [hostile]
        else:
            m["profiles"]["source"][0]["path"] = hostile

    vs.reforge(sealed, change=change)
    with OpenSpy() as spy:
        run = verify(cli, sealed, "--level", "chain")
    assert run.code == 1
    assert {"manifest.invalid", "manifest.files", "rules.mismatch"} & set(run.codes()), run.codes()
    assert spy.events == []


# ------------------------------------------------------------------------------------------------ deposit names
@pytest.mark.parametrize("name", ["{prefix}/../{sentinel}", "{prefix}/raw/../../{sentinel}", "/{sentinel}",
                                  "{prefix}/rules/..\\..\\{sentinel}"])
def test_sec15_a_hostile_member_name_in_a_deposit_archive_is_a_label_never_a_path(cli, sealed, tmp_path, name):
    out = _deposit(sealed, tmp_path / "deposit")
    meta = _archive(out, "meta")
    prefix = meta.name[: -len(".meta.zip")]
    label = name.format(prefix=prefix, sentinel=f"{harness.SENTINEL}.json")
    _rewrite(meta, lambda n, d: d, extra={label: b"{}"})
    sentinel(tmp_path, b"{}")
    with OpenSpy() as spy, fs_guard.unchanged(tmp_path / "deposit"):
        run = verify(cli, out, "--level", "chain")
    found = run.codes()
    assert run.code == 1 and "deposit.sha256" in found
    assert {"archive.member.path", "archive.member.prefix"} & set(found) or any(
        code.startswith("ingest.") for code in found), found
    assert spy.events == []
    assert harness.SENTINEL not in run.out + run.err  # a hostile name is never echoed


@pytest.mark.parametrize("name", ["../{sentinel}.zip", "/tmp/{sentinel}.zip", "sub/{sentinel}.zip", ".{sentinel}.zip",
                                  "+{sentinel}.zip", "-{sentinel}.zip", "{sentinel}\\..\\x.zip"])
def test_sec15_a_hostile_archive_name_in_the_deposit_manifest_is_refused(cli, sealed, tmp_path, name):
    out = _deposit(sealed, tmp_path / "deposit")
    path = out / "DEPOSIT-MANIFEST.json"
    document = json.loads(path.read_text("utf-8"))
    document["archives"][0]["name"] = name.format(sentinel=harness.SENTINEL)
    path.write_text(json.dumps(document), "utf-8")
    sentinel(tmp_path, b"PK", ".zip")
    with OpenSpy() as spy:
        run = verify(cli, out, "--level", "chain")
    assert run.code == 1 and run.codes() == {"deposit.manifest.invalid": 1}
    assert spy.events == []


def test_sec15_a_symlinked_archive_in_a_deposit_is_never_followed(cli, sealed, tmp_path):
    out = _deposit(sealed, tmp_path / "deposit")
    aer = _archive(out, "aer")
    target = tmp_path / f"{harness.SENTINEL}.zip"
    shutil.move(aer, target)
    os.symlink(target, aer)
    with OpenSpy() as spy:
        run = verify(cli, out, "--level", "chain")
    found = run.codes()
    assert run.code == 1 and "deposit.unlisted" in found and "deposit.missing" in found
    assert spy.events == []


def test_sec15_a_symlinked_deposit_manifest_is_not_a_deposit(cli, sealed, tmp_path):
    """A link is never a deposit manifest (``is_archive_input`` uses ``lstat``): the directory is then neither a deposit
    nor a corpus, a usage error (exit 2), and the link target is never opened."""
    out = _deposit(sealed, tmp_path / "deposit")
    manifest = out / "DEPOSIT-MANIFEST.json"
    target = sentinel(tmp_path, manifest.read_bytes())
    manifest.unlink()
    os.symlink(target, manifest)
    with OpenSpy() as spy:
        run = cli("verify", "--corpus", str(out), "--level", "chain")
    assert run.code == 2
    assert spy.events == []


# ------------------------------------------------------------------------------------------------ rules/ authority
def test_sec15_a_deposit_with_a_swapped_rules_copy_fails_with_rules_mismatch_in_archive_mode(cli, sealed, tmp_path):
    copy = sealed / "rules" / "agentdojo.rules.toml"
    copy.write_bytes(copy.read_bytes() + b"\n# swapped\n")
    vs.regenerate_checksums(sealed)
    out = _deposit(sealed, tmp_path / "deposit")  # the builder is given no chain verifier here (the CLI injects one)
    run = verify(cli, out, "--level", "chain")
    assert run.code == 1 and run.codes() == {"rules.mismatch": 1}
    run = verify(cli, out, "--level", "checksums")
    assert run.code == 0  # the deposit is internally consistent: only the authority check and the anchor see it


def test_sec15_a_deposit_whose_catalogue_version_the_package_does_not_ship_is_unverified_never_passed(cli, sealed,
                                                                                                     tmp_path):
    def change(m: dict[str, Any]) -> None:
        next(e for e in m["rule_catalogues"] if e["id"] == "agentdojo")["version"] = 99

    vs.reforge(sealed, change=change)
    out = _deposit(sealed, tmp_path / "deposit")
    run = verify(cli, out, "--level", "chain")
    assert run.code == 0 and run.codes() == {"rules.unavailable": 1}
    assert run.json()["failures"][0]["detail"].startswith("unverified:")
    run = verify(cli, out, "--level", "chain", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and run.codes() == {"rules.unavailable": 1}


@pytest.mark.parametrize("forgery", ["swapped", "unshipped"])
def test_sec15_the_deposit_builder_with_the_cli_verifier_refuses_a_forged_rules_authority(sealed, tmp_path, forgery):
    """``package --deposit`` injects ``verify --level chain`` in release mode into the builder (U5, D-42; H.10.1(3)): a
    swapped ``rules/`` copy (failed) and an unshipped catalogue version (unverified) never reach a deposit."""
    from agentprov.cli.deposit import verify_chain
    from agentprov.release.builder import DepositError

    if forgery == "swapped":
        copy = sealed / "rules" / "agentdojo.rules.toml"
        copy.write_bytes(copy.read_bytes() + b"\n# swapped\n")
        vs.regenerate_checksums(sealed)
        code = "rules.mismatch"
    else:
        vs.reforge(sealed, change=lambda m: next(
            e for e in m["rule_catalogues"] if e["id"] == "agentdojo").update(version=99))
        code = "rules.unavailable"
    out = tmp_path / "deposit"
    with fs_guard.unchanged(sealed), pytest.raises(DepositError) as refused:
        rs.build([sealed], out, verify=verify_chain)
    assert refused.value.code == "release.failed.verify" and code in str(refused.value)
    assert not out.exists() or not any(out.iterdir())
