"""SEC-10 (K.12.9): symlinks, hardlinks, special files in input trees. Capabilities are feature-tested, never platform-named.

The zip-symlink attribute case lives in test_archives.py (``ingest.archive.link``); a git mode-120000 entry is stored as
data by ``raw.fetch`` (its own tests).
"""

from __future__ import annotations

import os
import stat
import threading
import types

import pytest

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest import paths
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


def make_symlink(target, link, *, directory=False):
    if not hasattr(os, "symlink"):
        pytest.skip("host has no os.symlink")
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("host refuses to create symlinks for this user")


def make_hardlink(src, dst):
    if not hasattr(os, "link"):
        pytest.skip("host has no os.link")
    try:
        os.link(src, dst)
    except (OSError, NotImplementedError):
        pytest.skip("host refuses to create hardlinks here")


def code_of(root_fd, label, **kw):
    with pytest.raises(IngestError) as info:
        open_evidence(root_fd, label, **kw)
    return info.value.code


def test_sec10_symlinked_file_is_rejected_by_discover_and_open(tmp_path):
    (tmp_path / "real.json").write_bytes(b"{}")
    secret = tmp_path.parent / (tmp_path.name + "-outside.txt")
    secret.write_bytes(b"private")
    make_symlink(secret, tmp_path / "link.json")
    found = discover(tmp_path)
    assert [f.label for f in found.files] == ["real.json"]
    assert [(r.label, r.code) for r in found.rejected] == [("link.json", "ingest.path.symlink")]
    with open_root(tmp_path) as root:
        assert code_of(root, "link.json") == "ingest.path.symlink"


def test_sec10_dangling_symlink_is_a_symlink_not_a_missing_file(tmp_path):
    make_symlink(tmp_path / "nowhere", tmp_path / "dangling")
    assert [r.code for r in discover(tmp_path).rejected] == ["ingest.path.symlink"]
    with open_root(tmp_path) as root:
        assert code_of(root, "dangling") == "ingest.path.symlink"


def test_sec10_symlink_in_any_directory_component_is_refused(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "stolen.json").write_bytes(b"private")
    root_dir = tmp_path / "tree"
    (root_dir / "a").mkdir(parents=True)
    make_symlink(outside, root_dir / "a" / "b", directory=True)
    found = discover(root_dir)
    assert found.files == () and [(r.label, r.code) for r in found.rejected] == [("a/b", "ingest.path.symlink")]
    with open_root(root_dir) as root:
        assert code_of(root, "a/b/stolen.json") == "ingest.path.symlink"
        assert code_of(root, "a/b") == "ingest.path.symlink"


def test_sec10_a_directory_swapped_for_a_symlink_after_discovery_is_still_refused(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside2")
    outside.mkdir()
    (outside / "x.json").write_bytes(b"private")
    root_dir = tmp_path / "tree"
    (root_dir / "d").mkdir(parents=True)
    (root_dir / "d" / "x.json").write_bytes(b"public")
    assert [f.label for f in discover(root_dir).files] == ["d/x.json"]
    (root_dir / "d" / "x.json").unlink()
    (root_dir / "d").rmdir()
    make_symlink(outside, root_dir / "d", directory=True)  # the race: the checked path now points outside
    with open_root(root_dir) as root:
        assert code_of(root, "d/x.json") == "ingest.path.symlink"


def test_sec10_a_symlinked_root_is_resolved_once_and_recorded(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "f.json").write_bytes(b"1")
    make_symlink(real, tmp_path / "rootlink", directory=True)
    found = discover(tmp_path / "rootlink")
    assert found.root == os.path.realpath(real) and [f.label for f in found.files] == ["f.json"]


def test_sec10_hardlink_is_refused_unless_allowed(tmp_path):
    (tmp_path / "private.txt").write_bytes(b"private")
    make_hardlink(tmp_path / "private.txt", tmp_path / "alias.json")
    found = discover(tmp_path)
    assert {r.label: r.code for r in found.rejected} == {
        "alias.json": "ingest.path.hardlink",
        "private.txt": "ingest.path.hardlink",
    }
    with open_root(tmp_path) as root:
        assert code_of(root, "alias.json") == "ingest.path.hardlink"
        with open_evidence(root, "alias.json", allow_hardlinks=True) as fp:
            assert fp.read() == b"private"
        with pytest.raises(ValueError):  # never for a staging directory
            open_evidence(root, "alias.json", allow_hardlinks=True, staging=True)
    assert [f.label for f in discover(tmp_path, allow_hardlinks=True).files] == ["alias.json", "private.txt"]


def test_sec10_fifo_is_rejected_without_hanging(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("host has no os.mkfifo")
    try:
        os.mkfifo(tmp_path / "pipe")
    except OSError:
        pytest.skip("host cannot create a FIFO here")
    (tmp_path / "ok.json").write_bytes(b"{}")
    outcome: dict[str, object] = {}

    def work():
        found = discover(tmp_path)
        outcome["rejected"] = [(r.label, r.code) for r in found.rejected]
        outcome["files"] = [f.label for f in found.files]
        with open_root(tmp_path) as root:
            outcome["open"] = code_of(root, "pipe")

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(10)
    assert not thread.is_alive(), "a FIFO hung the importer"
    assert outcome == {"rejected": [("pipe", "ingest.path.special")], "files": ["ok.json"], "open": "ingest.path.special"}


def test_sec10_a_directory_is_not_a_file(tmp_path):
    (tmp_path / "d").mkdir()
    with open_root(tmp_path) as root:
        assert code_of(root, "d") in {"ingest.path.special"}


def test_sec10_special_file_that_stat_reports_as_regular_is_still_checked_through_the_descriptor(tmp_path, monkeypatch):
    (tmp_path / "f").write_bytes(b"1")
    real_fstat = os.fstat

    class Fake:
        def __init__(self, st):
            self._st = st

        def __getattr__(self, name):
            if name == "st_mode":
                return stat.S_IFCHR | 0o600
            return getattr(self._st, name)

    monkeypatch.setattr(os, "fstat", lambda fd: Fake(real_fstat(fd)))
    with open_root(tmp_path) as root:
        assert code_of(root, "f") == "ingest.path.special"


def test_sec10_apple_junk_is_skipped_not_rejected(tmp_path):
    (tmp_path / ".DS_Store").write_bytes(b"x")
    (tmp_path / "._real.json").write_bytes(b"x")
    (tmp_path / "real.json").write_bytes(b"{}")
    found = discover(tmp_path)
    assert [f.label for f in found.files] == ["real.json"] and found.rejected == ()
    assert found.skipped == (".DS_Store", "._real.json")


def test_sec10_hostile_file_names_in_a_tree_are_rejected_as_labels(tmp_path):
    for name in ("bad" + chr(0x1B) + "name", "back\\slash"):
        try:
            (tmp_path / name).write_bytes(b"x")
        except (OSError, ValueError):
            pytest.skip("host cannot create this file name")
    (tmp_path / "fine.json").write_bytes(b"{}")
    found = discover(tmp_path)
    assert [f.label for f in found.files] == ["fine.json"]
    assert {r.code for r in found.rejected} == {"ingest.name.invalid", "ingest.archive.traversal"}


def test_sec10_discovery_reads_nothing_and_respects_the_size_cap_on_open(tmp_path):
    limits = IngestLimits().replace(max_artefact_bytes=10)
    (tmp_path / "big").write_bytes(b"x" * 11)
    assert [f.label for f in discover(tmp_path, limits).files] == ["big"]  # listing is not reading
    with open_root(tmp_path) as root:
        assert code_of(root, "big", limits=limits) == "ingest.size.file"
