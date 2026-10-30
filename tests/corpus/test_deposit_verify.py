"""Archive-mode ``verify`` of deposit drafts, without extraction (H.5.5, H.10.3(1); G.3.5; K.12.15; HL-T9; D-38, D-39).

Deposits are built by U5's builder from the sealed test corpus (``release_support``). Every case runs the CLI on the
deposit directory (or a lone meta archive) with ``--json`` and checks exit code and finding codes; the deposit directory
is guarded unchanged (nothing is extracted or written).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
import release_support as rs
import verify_support as vs

from agentprov.testing import fs_guard


@pytest.fixture
def deposit(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> tuple[Path, Path]:
    """``(sealed corpus, deposit directory)``."""
    sealed = rs.sealed(tmp_path_factory, tmp_path / "corpora")
    out = tmp_path / "deposit"
    rs.build([sealed], out)
    return sealed, out


def codes(run: Any) -> dict[str, int]:
    return dict(run.json()["issues_by_code"])


def archive(out: Path, stage: str) -> Path:
    return next(p for p in sorted(out.glob("*.zip")) if f".{stage}" in p.name)


def rewrite(path: Path, change: Any) -> None:
    """Rewrite a zip with the builder's member settings; ``change(name, data) -> bytes | None`` (None drops it)."""
    with zipfile.ZipFile(path) as source:
        members = [(info, source.read(info)) for info in source.infolist()]
    path.unlink()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=False) as sink:
        for info, data in members:
            new = change(info.filename, data)
            if new is not None:
                sink.writestr(info, new)


def test_a_clean_deposit_passes_chain_in_archive_mode_without_extraction(cli, deposit, check_summary):
    sealed, out = deposit
    with fs_guard.unchanged(out):
        run = cli("verify", "--corpus", str(out), "--json")
    assert run.code == 0, run.err
    document = run.json()
    check_summary(document)
    assert document["failures"] == [] and document["counters"]["archives"] == 5
    assert document["counters"]["executions_checked"] == 3 and document["counters"]["files_matched"] > 0
    assert document["notices"][0].startswith("archive mode (deposit directory)")
    assert vs.root_digest(sealed) in run.err
    assert cli("verify", "--corpus", str(out), "--level", "checksums").code == 0
    assert cli("verify", "--corpus", str(out), "--release").code == 2  # D-620: the deposit manifest anchors nothing
    assert cli("verify", "--corpus", str(out), "--release", "--root-digest", vs.root_digest(sealed)).code == 0
    assert cli("verify", "--corpus", str(out), "--root-digest", vs.root_digest(sealed)).code == 0


def test_release_mode_on_a_deposit_needs_a_published_root_digest(cli, deposit, monkeypatch):
    """D-620 (ultra seal-release #8): ``DEPOSIT-MANIFEST.json`` lies in the same untrusted directory as the archives, so
    it anchors nothing. ``verify --release`` on a deposit directory needs ``--root-digest``, as in tree mode and on a
    lone meta archive: exit 2 before anything is read. Without ``--release`` the option stays optional."""
    from agentprov.corpus.verify import VerifyUsageError
    from agentprov.release.verify import verify_deposit

    sealed, out = deposit
    with fs_guard.unchanged(out):
        assert cli("verify", "--corpus", str(out), "--release").code == 2
        assert cli("verify", "--corpus", str(out), "--release", "--level", "checksums").code == 2
        with pytest.raises(VerifyUsageError, match="--root-digest"):
            verify_deposit(out, release=True)
        assert cli("verify", "--corpus", str(out), "--release", "--root-digest", vs.root_digest(sealed)).code == 0
        assert cli("verify", "--corpus", str(out)).code == 0  # dev mode: unchanged
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 7))
    assert cli("verify", "--corpus", str(out), "--release").code == 2  # the usage error precedes the interpreter guard


def test_a_deposit_of_a_version_with_build_metadata_verifies(cli, tmp_path_factory, tmp_path):
    """SemVer build metadata (``+r1``) is in the corpus version, so in every archive and its member prefix: the deposit
    the builder names ``<corpus_id>-v0.1.0+r1.<stage>...zip`` verifies (ultra seal-release #1)."""
    sealed = rs.sealed(tmp_path_factory, tmp_path / "corpora", "mini-build", version="0.1.0+r1")
    out = tmp_path / "deposit"
    rs.build([sealed], out)
    assert any(p.name == "mini-build-v0.1.0+r1.meta.zip" for p in out.glob("*.zip"))
    run = cli("verify", "--corpus", str(out), "--json", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 0, codes(run)
    assert cli("verify", "--corpus", str(out / "mini-build-v0.1.0+r1.meta.zip"), "--level", "checksums").code == 0


def test_rederive_is_refused_in_archive_mode(cli, deposit):
    assert cli("verify", "--corpus", str(deposit[1]), "--level", "rederive").code == 5


def test_a_member_byte_flipped_inside_an_archive(cli, deposit):
    _, out = deposit
    aer = archive(out, "aer")

    def change(name: str, data: bytes) -> bytes:
        if name.endswith(".aer.jsonl") and not getattr(change, "done", False):
            change.done = True  # type: ignore[attr-defined]
            flipped = bytearray(data)
            flipped[5] ^= 0x01
            return bytes(flipped)
        return data

    rewrite(aer, change)
    run = cli("verify", "--corpus", str(out), "--json")
    found = codes(run)
    assert run.code == 1
    assert found.get("checksums.mismatch") == 1  # the member against the corpus's checksums.sha256
    assert {"deposit.sha256", "deposit.md5", "deposit.archive.members_sha256"} <= set(found)


def test_a_flipped_byte_in_the_compressed_stream(cli, deposit):
    _, out = deposit
    path = archive(out, "prov")
    data = bytearray(path.read_bytes())
    data[200] ^= 0xFF  # inside the first member's compressed data
    path.write_bytes(bytes(data))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1
    found = codes(run)
    assert "deposit.sha256" in found
    assert any(code.startswith(("checksums.", "ingest.archive.")) for code in found)


def test_an_archive_replaced(cli, deposit, tmp_path_factory, tmp_path):
    """The aer archive replaced by the aer archive of another deposit (another corpus prefix)."""
    _, out = deposit
    other_sealed = rs.sealed(tmp_path_factory, tmp_path / "other", corpus_id="mini-gpl", derived="GPL-3.0-only")
    other = tmp_path / "other-deposit"
    rs.build([other_sealed], other)
    target = archive(out, "aer")
    target.write_bytes(archive(other, "aer").read_bytes())
    run = cli("verify", "--corpus", str(out), "--json")
    found = codes(run)
    assert run.code == 1
    assert {"deposit.sha256", "archive.member.prefix", "archive.not_present"} & set(found) >= {"deposit.sha256",
                                                                                                "archive.member.prefix"}
    assert "checksums.missing" in found  # the corpus's own AER files are no longer in the union of archives


def test_a_member_added(cli, deposit):
    _, out = deposit
    meta = archive(out, "meta")
    prefix = meta.name[: -len(".meta.zip")]
    with zipfile.ZipFile(meta, "a", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as zf:
        zf.writestr(f"{prefix}/validation/extra.json", b"{}")  # not a file of the H.1.2 tree
        zf.writestr(f"{prefix}/raw/objects/ab/ab{'0' * 62}.json", b"x")  # a grammar-admitted label it does not list
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    found = codes(run)
    assert run.code == 1
    assert found.get("archive.member.path") == 1 and found.get("checksums.unlisted") == 1
    assert "deposit.sha256" in found


def test_an_unlisted_file_beside_the_archives(cli, deposit):
    _, out = deposit
    (out / "notes.txt").write_bytes(b"x")
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.unlisted": 1}


def test_a_consistent_forgery_is_detected_only_by_the_published_root_digest(cli, tmp_path_factory, tmp_path):
    """Corpus tampered, ``checksums.sha256`` regenerated and a deposit built from it: the deposit is internally consistent;
    the root digest published outside it detects the forgery (D-39)."""
    sealed = rs.sealed(tmp_path_factory, tmp_path / "corpora")
    published = vs.root_digest(sealed)
    datasheet = sealed / "DATASHEET.md"
    datasheet.write_bytes(datasheet.read_bytes() + b"\nAn added sentence.\n")
    vs.regenerate_checksums(sealed)
    out = tmp_path / "forged"
    rs.build([sealed], out)
    assert cli("verify", "--corpus", str(out)).code == 0
    run = cli("verify", "--corpus", str(out), "--json", "--root-digest", published)
    assert run.code == 1 and codes(run) == {"root_digest.mismatch": 1}


def test_the_deposit_manifest_edited(cli, deposit):
    _, out = deposit
    path = out / "DEPOSIT-MANIFEST.json"
    document = json.loads(path.read_text("utf-8"))
    document["archives"][0]["members_sha256"] = "sha256:" + hashlib.sha256(b"x").hexdigest()
    document["corpora"][0]["root_digest"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(document), "utf-8")
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    found = codes(run)
    assert run.code == 1 and found.get("deposit.archive.members_sha256") == 1 and found.get("deposit.root_digest") == 1


def test_a_lone_meta_archive(cli, deposit):
    sealed, out = deposit
    meta = archive(out, "meta")
    run = cli("verify", "--corpus", str(meta), "--json")
    assert run.code == 0, run.err  # dev mode: what it holds verifies; the rest is unverified, never passed
    document = run.json()
    assert set(document["issues_by_code"]) == {"archive.not_present"}
    assert all(f["detail"].startswith("unverified:") for f in document["failures"])
    assert cli("verify", "--corpus", str(meta), "--release").code == 2  # no deposit manifest: --root-digest needed
    assert cli("verify", "--corpus", str(meta), "--release", "--root-digest", vs.root_digest(sealed)).code == 1
    rewrite(meta, lambda name, data: data + b"\n" if name.endswith("DATASHEET.md") else data)
    run = cli("verify", "--corpus", str(meta), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run).get("checksums.mismatch") == 1


def test_release_mode_below_the_interpreter_floor_is_refused_before_reading(cli, deposit, monkeypatch):
    monkeypatch.setattr("agentprov.envinfo._running_version", lambda: (3, 14, 7))
    sealed, out = deposit
    assert cli("verify", "--corpus", str(out), "--release", "--root-digest", vs.root_digest(sealed)).code == 3


def test_archive_options_that_need_a_tree_are_usage_errors(cli, deposit):
    _, out = deposit
    assert cli("verify", "--corpus", str(out), "--against-pins").code == 2
    assert cli("verify", "--corpus", str(out), "--sample", "1", "--seed", "s").code == 2


def edit_manifest(out: Path, change: Any) -> None:
    path = out / "DEPOSIT-MANIFEST.json"
    document = json.loads(path.read_text("utf-8"))
    change(document)
    path.write_text(json.dumps(document), "utf-8")


def test_an_archive_no_corpus_names_fails_even_with_the_published_root_digest(cli, deposit):
    """An extra archive listed in ``archives[]`` (correct size and digests) but named by no ``corpora[]`` entry: it holds
    a second ``corpus.json`` label, so it is never trusted (H.10.3(1), D-38), and the published root digest does not
    cover it (CB-13)."""
    sealed, out = deposit
    document = json.loads((out / "DEPOSIT-MANIFEST.json").read_text("utf-8"))
    corpus = document["corpora"][0]
    prefix = corpus["member_prefix"]
    name = prefix.rstrip("/") + ".raw.002.zip"
    with zipfile.ZipFile(out / name, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as zf:
        zf.writestr(prefix + "corpus.json", b'{"forged": true}\n')
        zf.writestr(prefix + "PLANTED.txt", b"planted\n")
    data = (out / name).read_bytes()
    entry = {"bytes": len(data), "corpus_id": corpus["corpus_id"], "corpus_version": corpus["corpus_version"],
             "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(), "members_sha256": "sha256:" + "0" * 64,
             "n_members": 99, "name": name, "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
             "shards": {"first": "zz", "last": "zz"}, "stage": "raw", "uncompressed_bytes": 0}
    edit_manifest(out, lambda d: d["archives"].append(entry))
    with fs_guard.unchanged(out):
        run = cli("verify", "--corpus", str(out), "--json", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and codes(run) == {"deposit.archive.orphan": 1}


def test_a_deposit_without_corpora_is_refused(cli, deposit):
    sealed, out = deposit
    edit_manifest(out, lambda d: d.update(corpora=[]))
    run = cli("verify", "--corpus", str(out), "--json", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}


def test_an_archive_claimed_twice_or_listed_twice(cli, deposit):
    _, out = deposit
    edit_manifest(out, lambda d: d["corpora"][0]["archives"].append(d["corpora"][0]["archives"][-1]))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.archive.orphan": 1}
    edit_manifest(out, lambda d: d["corpora"][0]["archives"].pop())
    assert cli("verify", "--corpus", str(out), "--level", "checksums").code == 0
    edit_manifest(out, lambda d: d["archives"].append(dict(d["archives"][-1])))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.archive.orphan": 1}


def test_an_archive_named_for_another_corpus_is_refused(cli, deposit):
    """Every archive a corpus names carries the corpus's ``<corpus_id>-v<version>.`` name prefix."""
    _, out = deposit
    old = archive(out, "raw")
    new = "mini-other-v0.1.0" + old.name[old.name.index(".raw."):]
    old.rename(out / new)

    def change(document: dict[str, Any]) -> None:
        for entry in document["archives"]:
            entry["name"] = new if entry["name"] == old.name else entry["name"]
        document["corpora"][0]["archives"] = [new if n == old.name else n for n in document["corpora"][0]["archives"]]

    edit_manifest(out, change)
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}


# ------------------------------------------------------------------------------------------------ documents (D-490, CB-14)
def put_document(out: Path, name: str, data: bytes) -> None:
    """Write deposit document ``name`` and make the deposit manifest agree with it (listing it when it is new)."""
    (out / name).write_bytes(data)

    def change(document: dict[str, Any]) -> None:
        entry = next((e for e in document["documents"] if e["name"] == name), None)
        if entry is None:
            entry = {"name": name}
            document["documents"].append(entry)
        entry.update(bytes=len(data), md5=hashlib.md5(data, usedforsecurity=False).hexdigest(),
                     sha256="sha256:" + hashlib.sha256(data).hexdigest())

    edit_manifest(out, change)


def test_a_forged_datasheet_copy_fails_even_when_the_deposit_manifest_agrees(cli, deposit):
    """The deposit copy ``DATASHEET-<id>.md`` is compared with the archived ``DATASHEET.md`` that the root digest covers,
    not only with the forgeable deposit manifest (D-490)."""
    sealed, out = deposit
    put_document(out, "DATASHEET-mini-mit.md", b"# Datasheet\n\nForged: no restrictions and no injection payloads.\n")
    with fs_guard.unchanged(out):
        run = cli("verify", "--corpus", str(out), "--json", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and codes(run) == {"deposit.document.datasheet": 1}


def test_a_datasheet_copy_with_a_line_added_fails(cli, deposit):
    _, out = deposit
    put_document(out, "DATASHEET-mini-mit.md", (out / "DATASHEET-mini-mit.md").read_bytes() + b"\nAn added line.\n")
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.document.datasheet": 1}


@pytest.mark.parametrize("name", ["EXTRA-NOTE.md", "DATASHEET-mini-other.md", "LICENSE"])
def test_a_document_outside_the_closed_set_is_refused(cli, deposit, name):
    """``documents[]`` is exactly README.md, CHANGELOG.md, deposit-metadata.json and one datasheet copy per corpus."""
    sealed, out = deposit
    put_document(out, name, b"free-form\n")
    run = cli("verify", "--corpus", str(out), "--json", "--release", "--root-digest", vs.root_digest(sealed))
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}


@pytest.mark.parametrize("name", ["README.md", "DATASHEET-mini-mit.md", "deposit-metadata.json"])
def test_a_document_missing_from_the_closed_set_is_refused(cli, deposit, name):
    _, out = deposit
    (out / name).unlink()
    edit_manifest(out, lambda d: d.update(documents=[e for e in d["documents"] if e["name"] != name]))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}


def test_a_document_listed_twice_is_refused(cli, deposit):
    _, out = deposit
    edit_manifest(out, lambda d: d["documents"].append(dict(d["documents"][0])))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}


@pytest.mark.parametrize("value", [None, "false", 0])
def test_mixed_licence_classes_must_be_a_boolean(cli, deposit, value):
    _, out = deposit
    edit_manifest(out, lambda d: d.update(mixed_licence_classes=value))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}


def test_a_mixed_class_deposit_passes_and_its_datasheet_copies_are_checked(cli, tmp_path_factory, tmp_path):
    """With mixed licence classes each copy is the sealed datasheet plus the builder's deposit note (D-490)."""
    mit = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")
    gpl = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-gpl", "GPL-3.0-only")
    out = tmp_path / "mixed"
    rs.build([mit, gpl], out, allow_mixed_licence_classes=True)
    digests = [arg for c in (mit, gpl) for arg in ("--root-digest", vs.root_digest(c))]
    run = cli("verify", "--corpus", str(out), "--json", "--release", *digests)
    assert run.code == 0, run.err
    copy = (out / "DATASHEET-mini-gpl.md").read_bytes()
    assert copy != (gpl / "DATASHEET.md").read_bytes()
    put_document(out, "DATASHEET-mini-gpl.md", copy.replace(b"## Deposit note", b"## A note", 1))
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.document.datasheet": 1}
    put_document(out, "DATASHEET-mini-gpl.md", (gpl / "DATASHEET.md").read_bytes())  # the note dropped
    run = cli("verify", "--corpus", str(out), "--json", "--level", "checksums")
    assert run.code == 1 and codes(run) == {"deposit.document.datasheet": 1}
    edit_manifest(out, lambda d: d.update(mixed_licence_classes=False))  # now a byte copy is expected
    assert cli("verify", "--corpus", str(out), "--level", "checksums").code == 1


@pytest.fixture
def mixed(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> tuple[Path, Path, list[str]]:
    """``(the GPL corpus, a builder-made MIT + GPL-3.0-only deposit, the --root-digest arguments)``."""
    mit = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-mit")
    gpl = rs.sealed(tmp_path_factory, tmp_path / "c", "mini-gpl", "GPL-3.0-only")
    out = tmp_path / "mixed"
    rs.build([mit, gpl], out, allow_mixed_licence_classes=True)
    return gpl, out, [arg for c in (mit, gpl) for arg in ("--root-digest", vs.root_digest(c))]


def test_release_mode_needs_a_published_root_digest_for_every_corpus_of_a_deposit(cli, mixed):
    """D-641 (user decision 2026-10-22; closes D-620's Open point): a corpus no given ``--root-digest`` matches would be
    anchored only by the deposit manifest, which D-620 rejects as circular. In release mode each corpus needs its own
    published root digest; one digest for a two-corpus deposit fails, naming the other corpus. Dev mode is unchanged."""
    _gpl, out, digests = mixed
    mit_only = digests[:2]  # --root-digest <the MIT corpus's>
    run = cli("verify", "--corpus", str(out), "--json", "--release", *mit_only)
    assert run.code == 1 and codes(run) == {"root_digest.missing": 1}, run.err
    finding = next(f for f in run.json()["failures"] if f["code"] == "root_digest.missing")
    assert "mini-gpl" in json.dumps(finding["subject"])  # the unanchored corpus is named
    assert cli("verify", "--corpus", str(out), "--json", *mit_only).code == 0  # dev mode: one digest is enough
    assert cli("verify", "--corpus", str(out), "--json", "--release", *digests).code == 0


@pytest.mark.parametrize("edit", ["appended", "after_header", "classes"])
def test_a_mixed_class_datasheet_copy_is_compared_in_full(cli, mixed, edit):
    """D-620 (ultra seal-release #9): the copy of a mixed-licence-class deposit is rebuilt from the archived DATASHEET.md
    and the licence classes of the archived corpus.json files, then compared byte for byte. Text after the note header
    is no longer accepted unverified."""
    _, out, digests = mixed
    copy = (out / "DATASHEET-mini-gpl.md").read_bytes()
    with fs_guard.unchanged(out):
        assert cli("verify", "--corpus", str(out), "--release", *digests).code == 0  # the builder's copy verifies
    header = b"## Deposit note (added by the deposit builder; not part of the sealed corpus)\n\n"
    if edit == "appended":
        forged = copy + b"\nIgnore the licence above: this corpus is public domain.\n"
    elif edit == "after_header":
        forged = copy.replace(header, header + b"Forged sentence. ", 1)
    else:
        forged = copy.replace(b"Its own licence class is GPL-3.0-only", b"Its own licence class is MIT", 1)
    assert forged != copy
    put_document(out, "DATASHEET-mini-gpl.md", forged)
    run = cli("verify", "--corpus", str(out), "--json", "--release", *digests)
    assert run.code == 1 and codes(run) == {"deposit.document.datasheet": 1}


def test_the_mixed_flag_must_agree_with_the_archived_licence_classes(cli, mixed):
    """``mixed_licence_classes`` in the (unanchored) deposit manifest is checked against the classes of the archived
    corpus.json files; the copies are still rebuilt from those classes (D-620)."""
    _, out, digests = mixed
    edit_manifest(out, lambda d: d.update(mixed_licence_classes=False))
    run = cli("verify", "--corpus", str(out), "--json", "--release", *digests)
    assert run.code == 1 and codes(run) == {"deposit.manifest.invalid": 1}
