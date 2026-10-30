"""Checksums, set digests, content and root digests, closed world (HL H.2.11, H.5.3, H.5.4, H.5.5; HL-T2)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from agentprov.corpus.integrity import (
    ChecksumFinding,
    IntegrityError,
    content_digest,
    parse_checksums,
    root_digest,
    set_digest,
    verify_checksums,
    write_checksums,
)
from agentprov.corpus.layout import CorpusLayout, SealedCorpusError
from agentprov.testing import fs_guard

EX = "ex_7uz2oys57hugtsueixylme4fl5"
OBJ = b'{"x":1}'
OBJ_SHA = hashlib.sha256(OBJ).hexdigest()


def mini_corpus(root: Path, *, sealed: bool = True) -> Path:
    """A small tree with one file of every kind HL-T2 names (corpus.json, DATASHEET.md, raw/members.jsonl, WITHHELD.json)."""
    layout = CorpusLayout(root)
    files = {
        "corpus.json": json.dumps({"format": "agentprov-corpus/0.1", "sealed": sealed}).encode(),
        "executions.jsonl": b"",
        "register.jsonl": b"",
        "derivation.json": b"{}\n",
        "DATASHEET.md": b"# datasheet\n",
        "CHANGELOG.md": b"# changes\n",
        "WITHHELD.json": b"{}\n",
        "raw/origins.jsonl": b"",
        "raw/members.jsonl": b"",
        f"raw/objects/{OBJ_SHA[:2]}/{OBJ_SHA}.json": OBJ,
        layout.aer_relpath(EX): b"aer\n",
        "LICENSES/DERIVED.txt": b"licence\n",
        "LICENSES/foo/LICENSE": b"MIT\n",
        "LICENSES/foo/NOTICE.md": b"notice\n",
        "schemas/aer-0.1.schema.json": b"{}\n",
        "rules/corpus-spec.toml": b"",
        "rules/foo.rules.toml": b"",
        "rules/prov/agentprov-prov-0.1.toml": b"",
        "validation/results.jsonl": b"",
        "validation/summary.json": b"{}\n",
    }
    for label, data in files.items():
        path = root.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


# ------------------------------------------------------------------------------------------------ digests
def test_set_digest_definition():
    pairs = [("ex_b", "sha256:" + "2" * 64), ("ex_a", "sha256:" + "1" * 64)]
    body = "".join(sorted(f"{a} {b}\n" for a, b in pairs)).encode()
    assert set_digest(pairs) == "sha256:" + hashlib.sha256(body).hexdigest()
    assert set_digest(reversed(pairs)) == set_digest(pairs)
    assert set_digest([]) == "sha256:" + hashlib.sha256(b"").hexdigest()
    for bad in ([("a b", "c")], [("a", "c\nd")], [("", "c")]):
        with pytest.raises(ValueError):
            set_digest(bad)


def test_content_digest_excludes_release_sealed_and_itself():
    manifest = {"corpus_id": "c", "counts": {"executions": 2}, "release": {"created": None}, "sealed": False}
    base = content_digest(manifest)
    assert base == "sha256:" + hashlib.sha256(b'{"corpus_id":"c","counts":{"executions":2}}').hexdigest()
    changed = {**manifest, "release": {"created": "2026-10-11T00:00:00Z"}, "sealed": True, "content_digest": base}
    assert content_digest(changed) == base  # HL-T4: independent of the release date
    assert content_digest(dict(reversed(list(manifest.items())))) == base  # JCS: formatting and order are irrelevant
    assert content_digest({**manifest, "corpus_id": "d"}) != base
    with pytest.raises(ValueError):
        content_digest({"ratio": 0.5})


# ------------------------------------------------------------------------------------------------ write + verify
def test_hl_t2_every_file_is_listed_sorted_and_verified(tmp_path):
    root = mini_corpus(tmp_path / "c")
    target = write_checksums(root)  # corpus.json already says sealed: true (H.5.3(4))
    data = target.read_bytes()
    lines = data.decode().splitlines()
    paths = [line[66:] for line in lines]
    assert paths == sorted(paths, key=str.encode) and "checksums.sha256" not in paths
    for required in ("corpus.json", "DATASHEET.md", "raw/members.jsonl", "WITHHELD.json", "CHANGELOG.md", "LICENSES/foo/LICENSE"):
        assert required in paths
    assert all(len(line) > 66 and line[64:66] == "  " for line in lines) and data.endswith(b"\n")
    assert lines[paths.index("corpus.json")][:64] == hashlib.sha256((root / "corpus.json").read_bytes()).hexdigest()
    assert root_digest(root) == "sha256:" + hashlib.sha256(data).hexdigest()
    with fs_guard.unchanged(root):
        report = verify_checksums(root)
    assert report.ok and report.listed == report.matched == len(paths) == 20


def test_hl_t2_a_stray_ds_store_fails_verification(tmp_path):
    root = mini_corpus(tmp_path / "c")
    write_checksums(root)
    (root / ".DS_Store").write_bytes(b"\0")
    (root / "raw" / "._members.jsonl").write_bytes(b"\0")
    report = verify_checksums(root)
    assert not report.ok and report.codes() == {"corpus.tree.stray": 2}
    assert verify_checksums(root, closed_world=False).ok


@pytest.mark.parametrize(
    ("damage", "code"),
    [
        (lambda r: (r / "DATASHEET.md").write_bytes(b"edited\n"), "checksums.mismatch"),
        (lambda r: (r / "WITHHELD.json").unlink(), "checksums.missing"),
        (lambda r: (r / "aer" / "00").mkdir() or (r / "rules" / "bar.rules.toml").write_bytes(b""), "checksums.unlisted"),
        (lambda r: (r / "raw" / "tmp").mkdir(), "corpus.tree.raw_tmp"),
        (lambda r: (r / "views").mkdir(), "corpus.tree.empty_dir"),
        (lambda r: (r / "notes.txt").write_bytes(b""), "corpus.tree.stray"),
    ],
)
def test_tampering_is_found(tmp_path, damage, code):
    root = mini_corpus(tmp_path / "c")
    write_checksums(root)
    damage(root)
    report = verify_checksums(root)
    assert not report.ok and code in report.codes()


def test_a_symlink_is_never_followed(tmp_path):
    root = mini_corpus(tmp_path / "c")
    write_checksums(root)
    outside = tmp_path / "outside.md"
    outside.write_bytes((root / "DATASHEET.md").read_bytes())  # the same bytes: following it would pass
    (root / "DATASHEET.md").unlink()
    os.symlink(outside, root / "DATASHEET.md")
    report = verify_checksums(root)
    assert {"checksums.unreadable", "corpus.tree.link"} <= set(report.codes())


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_a_refused_checksums_file_is_a_finding_not_an_exception(tmp_path, kind):
    # CB-12: a checksums.sha256 that open_evidence refuses (a link, a special file) is checksums.unreadable, like any
    # listed file; the closed-world findings are still reported and nothing outside the tree is opened.
    root = mini_corpus(tmp_path / "c")
    data = write_checksums(root).read_bytes()
    (root / "checksums.sha256").unlink()
    if kind == "symlink":
        outside = tmp_path / "outside.sha256"
        outside.write_bytes(data)  # the same bytes: following it would pass
        os.symlink(outside, root / "checksums.sha256")
    else:
        os.mkfifo(root / "checksums.sha256")
    report = verify_checksums(root)
    assert not report.ok and report.listed == report.matched == 0
    assert "checksums.unreadable" in report.codes() and "checksums.absent" not in report.codes()
    unreadable = [f for f in report.findings if f.code == "checksums.unreadable"]
    assert [f.path for f in unreadable] == ["checksums.sha256"] and unreadable[0].detail
    with pytest.raises(IntegrityError) as refused:
        root_digest(root)
    assert refused.value.code == "corpus.integrity.unreadable"


def test_malformed_checksums_are_reported_by_line_never_by_path(tmp_path):
    good = "0" * 64
    data = (f"{good}  register.jsonl\n{good}  corpus.json\n{good}  ../etc/passwd\n{good}  corpus.json\n"
            f"{'G' * 64}  derivation.json\n{good} DATASHEET.md\n{good}  checksums.sha256\n").encode()
    entries, findings = parse_checksums(data)
    assert [e.path for e in entries] == ["register.jsonl"]
    assert findings == [
        ChecksumFinding("checksums.malformed", "#2", "lines are not sorted by path"),
        ChecksumFinding("checksums.path_invalid", "#3", "the path is not a file of the H.1.2 tree"),
        ChecksumFinding("checksums.malformed", "#4", "lines are not sorted by path"),
        ChecksumFinding("checksums.malformed", "#5", "the digest is not 64 lower-case hex digits"),
        ChecksumFinding("checksums.malformed", "#6", "not '<64 hex>  <path>'"),
        ChecksumFinding("checksums.path_invalid", "#7", "the path is not a file of the H.1.2 tree"),
    ]
    assert all("passwd" not in f.path + f.detail for f in findings)
    assert parse_checksums(f"{good}  corpus.json".encode())[1][0].code == "checksums.malformed"  # no final LF


def test_verify_without_checksums(tmp_path):
    report = verify_checksums(mini_corpus(tmp_path / "c"))
    assert not report.ok and report.codes() == {"checksums.absent": 1}
    with pytest.raises(IntegrityError):
        root_digest(tmp_path / "c")


def test_write_checksums_refusals(tmp_path):
    root = mini_corpus(tmp_path / "c")
    (root / "raw" / "tmp").mkdir()
    with pytest.raises(IntegrityError) as exc:
        write_checksums(root)  # the stray empty raw/tmp/ of a working tree (removed by sealing)
    assert exc.value.code == "corpus.integrity.not_closed"
    (root / "raw" / "tmp").rmdir()
    write_checksums(root)
    with pytest.raises(SealedCorpusError):
        write_checksums(root)  # a corpus is checksummed once
    outer = mini_corpus(tmp_path / "outer")
    inner = mini_corpus(outer / "inner")
    with pytest.raises(SealedCorpusError):
        write_checksums(inner)  # inside a sealed corpus
    assert not (inner / "checksums.sha256").exists()


def test_two_writes_of_one_tree_give_one_root_digest(tmp_path):
    first, second = mini_corpus(tmp_path / "a"), mini_corpus(tmp_path / "b")
    write_checksums(first)
    write_checksums(second)
    assert root_digest(first) == root_digest(second)
