"""The portable no-follow capability (G.3.6, G.3.10; DECISIONS D-7): selection by feature test, and the verify_identity
mechanism's own defences (reparse points, identity swaps, host path syntax). Everything runs on any host, through
synthetic hosts and patched ``lstat``/``fstat`` results."""

from __future__ import annotations

import os
import stat
import types

import pytest

from agentprov.errors import IngestError, IngestSafetyError
from agentprov.ingest import paths
from agentprov.ingest.paths import discover, open_evidence, open_root


def host(**present):
    """A synthetic ``os``: only the named attributes exist."""
    return types.SimpleNamespace(**present)


NATIVE_HOST = dict(
    O_RDONLY=0, O_NOFOLLOW=0x100, O_DIRECTORY=0x200, open=os.open, stat=os.stat, scandir=os.scandir,
    supports_dir_fd={os.open, os.stat}, supports_fd={os.scandir},
)  # fmt: skip
VERIFY_ONLY = dict(O_RDONLY=0, open=os.open, lstat=os.lstat, fstat=os.fstat, scandir=os.scandir)


@pytest.fixture
def verify(monkeypatch):
    monkeypatch.setattr(paths, "_prim", lambda: paths._probe(host(**VERIFY_ONLY)))


def test_native_is_chosen_when_every_native_primitive_exists():
    prim = paths._probe(host(**NATIVE_HOST))
    assert prim.mechanism == "native" and "dir_fd" in prim.how
    assert paths.describe_mechanism(host(**NATIVE_HOST))[0] == "native"


@pytest.mark.parametrize("missing", ["O_NOFOLLOW", "O_DIRECTORY", "supports_dir_fd", "supports_fd"])
def test_losing_any_native_primitive_selects_verify_identity(missing):
    h = dict(NATIVE_HOST, **{"lstat": os.lstat, "fstat": os.fstat})
    h.pop(missing)
    prim = paths._probe(host(**h))
    assert prim.mechanism == "verify_identity" and prim.root_flags == 0
    mechanism, how = paths.describe_mechanism(host(**h))
    assert mechanism == "verify_identity" and "lstat" in how


def test_unsupported_platform_only_when_neither_mechanism_exists():
    with pytest.raises(IngestSafetyError) as info:
        paths._probe(host(O_RDONLY=0))
    assert info.value.code == "ingest.path.unsupported_platform"
    assert "fallback" in str(info.value) and "lstat" in str(info.value)
    mechanism, how = paths.describe_mechanism(host(O_RDONLY=0))
    assert mechanism == "none" and "lstat" in how


def test_verify_identity_flags_include_binary_and_never_a_nofollow_flag():
    prim = paths._probe(host(O_RDONLY=0, O_BINARY=0x8000, **{k: v for k, v in VERIFY_ONLY.items() if k != "O_RDONLY"}))
    assert prim.file_flags & 0x8000 and prim.dir_flags == 0


class WithAttributes:
    """A stat result that also carries ``st_file_attributes`` (present only where the host reports them)."""

    def __init__(self, st, attributes):
        self._st, self._attributes = st, attributes

    def __getattr__(self, name):
        return self._attributes if name == "st_file_attributes" else getattr(self._st, name)


def test_a_reparse_point_is_a_link_where_the_host_reports_attributes(verify, tmp_path, monkeypatch):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.json").write_bytes(b"{}")
    (tmp_path / "plain.json").write_bytes(b"{}")
    real = paths._lstat

    def lstat(path):
        st = real(path)
        flagged = os.path.basename(path) in {"d", "plain.json"}
        return WithAttributes(st, stat.FILE_ATTRIBUTE_REPARSE_POINT if flagged else 0)

    monkeypatch.setattr(paths, "_lstat", lstat)
    found = discover(tmp_path)
    assert found.files == () and [(r.label, r.code) for r in found.rejected] == [
        ("d", "ingest.path.symlink"),
        ("plain.json", "ingest.path.symlink"),
    ]
    for label in ("d/f.json", "plain.json"):
        with open_root(tmp_path) as root, pytest.raises(IngestError) as info:
            open_evidence(root, label)
        assert info.value.code == "ingest.path.symlink"


def test_a_plain_regular_file_opens_under_verify_identity(verify, tmp_path):
    (tmp_path / "f.json").write_bytes(b"{}")
    with open_root(tmp_path) as root, open_evidence(root, "f.json") as fp:
        assert fp.read() == b"{}"


def test_a_leaf_swapped_between_lstat_and_open_is_refused(verify, tmp_path, monkeypatch):
    (tmp_path / "a.json").write_bytes(b"one")
    (tmp_path / "b.json").write_bytes(b"two")
    real_lstat = paths._lstat
    monkeypatch.setattr(paths, "_lstat", lambda path: real_lstat(str(tmp_path / "b.json")) if path.endswith("a.json") else real_lstat(path))
    with open_root(tmp_path) as root, pytest.raises(IngestError) as info:
        open_evidence(root, "a.json")  # lstat said "b.json", the open reached "a.json": a different file
    assert info.value.code == "ingest.path.symlink"


def test_identity_falls_back_to_size_and_mtime_when_the_host_has_no_file_ids():
    a = types.SimpleNamespace(st_ino=0, st_dev=0, st_size=3, st_mtime_ns=5)
    assert paths._same_identity(a, types.SimpleNamespace(st_ino=0, st_dev=0, st_size=3, st_mtime_ns=5))
    assert not paths._same_identity(a, types.SimpleNamespace(st_ino=0, st_dev=0, st_size=4, st_mtime_ns=5))
    assert paths._same_identity(types.SimpleNamespace(st_ino=7, st_dev=1), types.SimpleNamespace(st_ino=7, st_dev=1))
    assert not paths._same_identity(types.SimpleNamespace(st_ino=7, st_dev=1), types.SimpleNamespace(st_ino=8, st_dev=1))


def test_a_host_with_an_alternate_separator_refuses_stream_and_drive_forms(verify, tmp_path, monkeypatch):
    (tmp_path / "f.json").write_bytes(b"{}")
    monkeypatch.setattr(os, "altsep", "\\")  # a DOS-like path syntax: ':' means a drive or a stream
    with open_root(tmp_path) as root:
        for label in ("f.json:stream", "a:b"):
            with pytest.raises(IngestError) as info:
                open_evidence(root, label)
            assert info.value.code == "ingest.archive.traversal"
        with open_evidence(root, "f.json") as fp:
            assert fp.read() == b"{}"


def test_a_bare_descriptor_needs_the_native_mechanism(verify, tmp_path):
    (tmp_path / "f").write_bytes(b"x")  # a file descriptor: Windows cannot os.open() a directory
    fd = os.open(tmp_path / "f", os.O_RDONLY)
    try:
        with pytest.raises(ValueError):
            open_evidence(fd, "x")
    finally:
        os.close(fd)


def test_a_directory_path_can_be_given_instead_of_a_handle(verify, tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "f.json").write_bytes(b"[]")
    with open_evidence(tmp_path, "s/f.json") as fp:
        assert fp.read() == b"[]"


def test_both_mechanisms_discover_the_same_tree(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.json").write_bytes(b"1")
    (tmp_path / "y.jsonl").write_bytes(b"2")
    (tmp_path / ".DS_Store").write_bytes(b"j")
    if paths.describe_mechanism()[0] != "native":
        pytest.skip("this host has no native mechanism to compare with")
    native = discover(tmp_path)
    monkeypatch.setattr(paths, "_prim", lambda: paths._probe(host(**VERIFY_ONLY)))
    assert discover(tmp_path) == native
