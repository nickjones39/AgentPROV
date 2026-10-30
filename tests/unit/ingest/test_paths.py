"""discover / open_evidence functional behaviour (G.3.6). Link and special-file hostility: tests/security/test_links_special_files.py."""

from __future__ import annotations

import errno
import os
import types

import pytest

from agentprov.errors import IngestError, IngestSafetyError
from agentprov.ingest import paths
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.paths import discover, open_evidence, open_root


def _verify_host():
    """A host without O_NOFOLLOW and dir_fd: forces the verify_identity mechanism on any machine."""
    host = types.SimpleNamespace(
        O_RDONLY=os.O_RDONLY, open=os.open, lstat=os.lstat, fstat=os.fstat, scandir=os.scandir,
        supports_dir_fd=frozenset(), supports_fd=frozenset(),
    )  # fmt: skip
    for name in ("O_BINARY", "O_CLOEXEC", "O_NONBLOCK"):
        if hasattr(os, name):
            setattr(host, name, getattr(os, name))
    return host


@pytest.fixture(params=["native", "verify_identity"], autouse=True)
def mechanism(request, monkeypatch):
    """Run every test of this module under both no-follow mechanisms (the host's own, or a forced fake host)."""
    if request.param == "native":
        if paths.describe_mechanism()[0] != "native":
            pytest.skip("this host has no native no-follow primitives")
    else:
        monkeypatch.setattr(paths, "_prim", lambda: paths._probe(_verify_host()))
    return request.param


def populate(root):
    (root / "a.json").write_bytes(b'{"a":1}')
    (root / "sub").mkdir()
    (root / "sub" / "b.jsonl").write_bytes(b"1\n2\n")
    (root / "sub" / "deeper").mkdir()
    (root / "sub" / "deeper" / "c.txt").write_bytes(b"c")
    (root / ".DS_Store").write_bytes(b"junk")
    (root / "sub" / "._b.jsonl").write_bytes(b"junk")


def test_discover_lists_regular_files_sorted_and_skips_apple_junk(tmp_path):
    populate(tmp_path)
    found = discover(tmp_path)
    assert [(f.label, f.size) for f in found.files] == [("a.json", 7), ("sub/b.jsonl", 4), ("sub/deeper/c.txt", 1)]
    assert found.rejected == ()
    assert found.skipped == (".DS_Store", "sub/._b.jsonl")
    assert found.root == os.path.realpath(tmp_path)
    assert discover(tmp_path) == found  # deterministic


def test_open_evidence_reads_through_the_descriptor(tmp_path):
    populate(tmp_path)
    with open_root(tmp_path) as root:
        with open_evidence(root, "sub/deeper/c.txt") as fp:
            assert fp.read() == b"c"
            assert "b" in fp.mode


def test_discover_accepts_an_open_root_without_closing_it(tmp_path):
    populate(tmp_path)
    with open_root(tmp_path) as root:
        discover(root)
        assert root.fd == -1 or os.fstat(root.fd)  # still open (a descriptor exists only with the native mechanism)


@pytest.mark.parametrize("label", ["../x", "a/../x", "/etc/passwd", "sub//b", "", "a\\b", "x" + chr(0)])
def test_open_evidence_refuses_labels_that_are_not_clean(tmp_path, label):
    populate(tmp_path)
    with open_root(tmp_path) as root, pytest.raises(IngestError) as info:
        open_evidence(root, label)
    assert info.value.code in {"ingest.name.invalid", "ingest.archive.traversal"}


def test_missing_file_is_an_ordinary_error(tmp_path):
    with open_root(tmp_path) as root, pytest.raises(FileNotFoundError):
        open_evidence(root, "nope.json")


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_file_size_cap(tmp_path, delta):
    limits = IngestLimits().replace(max_artefact_bytes=64)
    (tmp_path / "f").write_bytes(b"x" * (64 + delta))
    with open_root(tmp_path) as root:
        if delta > 0:
            with pytest.raises(IngestError) as info:
                open_evidence(root, "f", limits)
            assert info.value.code == "ingest.size.file"
        else:
            open_evidence(root, "f", limits).close()


def test_staging_never_allows_hardlinks(tmp_path):
    (tmp_path / "f").write_bytes(b"1")
    with open_root(tmp_path) as root, pytest.raises(ValueError):
        open_evidence(root, "f", allow_hardlinks=True, staging=True)


def test_open_descriptors_grow_with_depth_not_width(tmp_path, monkeypatch):
    """A wide tree (a raw store has 256 shard directories) must not hold one descriptor per pending sibling: under a
    256 descriptor limit that crashed with EMFILE or dropped directories as special files (bug pass BF-14)."""
    for i in range(200):
        (tmp_path / "runs" / f"d{i:03d}").mkdir(parents=True)
        (tmp_path / "runs" / f"d{i:03d}" / "x.json").write_bytes(b"{}")
    peak = []
    scandir = os.scandir

    def counting_scandir(ref):
        peak.append(len(os.listdir("/dev/fd")))
        return scandir(ref)

    paths._prim()  # probe the host first: the probe must see the real os.scandir
    baseline = len(os.listdir("/dev/fd"))
    monkeypatch.setattr(os, "scandir", counting_scandir)
    found = discover(tmp_path)
    assert len(found.files) == 200 and not found.rejected
    assert max(peak) - baseline < 16


def test_running_out_of_descriptors_is_an_error_not_a_rejection(tmp_path, monkeypatch, mechanism):
    if mechanism != "native":
        pytest.skip("only the native mechanism opens directories")
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "x.json").write_bytes(b"{}")

    def exhausted(dir_fd, name, *, directory):
        raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))

    monkeypatch.setattr(paths, "_open_at", exhausted)
    with pytest.raises(OSError) as info:
        discover(tmp_path)
    assert info.value.errno == errno.EMFILE


def test_missing_host_primitives_fail_closed_with_a_typed_code():
    class Host:  # no O_NOFOLLOW, no O_DIRECTORY, no dir_fd support
        O_RDONLY = 0

    with pytest.raises(IngestSafetyError) as info:
        paths._probe(Host())
    assert info.value.code == "ingest.path.unsupported_platform" and info.value.exit_code == 3
    assert "O_NOFOLLOW" in str(info.value) and "scandir(fd)" in str(info.value)


def test_optional_primitives_degrade_without_failing():
    host = type("Host", (), {})()
    # A synthetic native host: flag values from the real os where it has them, else POSIX-style stand-ins
    # (Windows has no O_NOFOLLOW / O_DIRECTORY; the probe only needs distinct bits).
    for name, fallback in (("O_RDONLY", 0), ("O_NOFOLLOW", 0x20000), ("O_DIRECTORY", 0x10000)):
        setattr(host, name, getattr(os, name, fallback))
    host.open, host.stat, host.scandir = os.open, os.stat, os.scandir
    # Declared support, not the real host's (Windows' os.supports_dir_fd is empty): the probe reads membership only.
    host.supports_dir_fd = {host.open, host.stat}
    host.supports_fd = {host.scandir}
    prim = paths._probe(host)  # no O_CLOEXEC, O_NONBLOCK or O_NOFOLLOW_ANY on this fake host
    assert prim.nonblocking is False
    assert prim.file_flags == host.O_RDONLY | host.O_NOFOLLOW
