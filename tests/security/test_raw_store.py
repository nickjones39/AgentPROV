"""SEC: the raw store never builds paths from untrusted strings, never overwrites, never follows links (G.3.1, G.4.5)."""

from __future__ import annotations

import hashlib
import io
import os
import stat

import pytest

from agentprov.ingest.limits import IngestLimits
from agentprov.errors import IngestError
from agentprov.raw.origins import Origin, OriginError, OriginLog, decode_origins
from agentprov.raw.store import DigestCollisionError, RawObjectStore, RawStoreError

TRAVERSAL = ["../../etc/passwd", "..", "../" * 40 + "a" * 64, "a" * 62 + "/.", "a" * 64 + "/../" + "b" * 64, "a" * 64 + "\x00", "A" * 64, "%2e%2e/" + "a" * 58,
             " " + "a" * 63, "a" * 63 + "\n", "ａ" * 64]


@pytest.fixture
def store(tmp_path):
    return RawObjectStore(tmp_path / "raw")


@pytest.mark.parametrize("digest", TRAVERSAL)
def test_untrusted_digest_strings_are_absent_and_never_reach_the_filesystem(store, digest, monkeypatch):
    touched = []
    real_scandir, real_lstat, real_open = os.scandir, os.lstat, os.open
    monkeypatch.setattr(os, "scandir", lambda p, *a, **k: (touched.append(str(p)), real_scandir(p, *a, **k))[1])
    monkeypatch.setattr(os, "lstat", lambda p, *a, **k: (touched.append(str(p)), real_lstat(p, *a, **k))[1])
    monkeypatch.setattr(os, "open", lambda p, *a, **k: (touched.append(str(p)), real_open(p, *a, **k))[1])
    assert store.has(digest) is False
    for call in (store.size, store.read_bytes, store.open):
        with pytest.raises(KeyError):
            call(digest)
    assert touched == []
    with pytest.raises(ValueError):
        store.path_for(digest)


def test_a_symlinked_object_is_never_followed(store, tmp_path):
    put = store.put(b"genuine")
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"outside the store")
    os.chmod(put.path, 0o644)
    put.path.unlink()
    try:
        put.path.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    for call in (store.has, store.size, store.read_bytes, store.verify):
        with pytest.raises(RawStoreError) as exc:
            call(put.sha256)
        assert exc.value.code == "raw.object.invalid"
    assert secret.read_bytes() == b"outside the store"


def test_a_symlinked_shard_directory_is_never_followed(store, tmp_path):
    put = store.put(b"genuine")
    shard = put.path.parent
    elsewhere = tmp_path / "elsewhere"
    shard.rename(elsewhere)
    try:
        shard.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(RawStoreError) as exc:
        store.read_bytes(put.sha256)
    assert exc.value.code == "raw.store.not_directory"
    with pytest.raises(RawStoreError):
        store.put(b"genuine")  # a put through the replaced shard is refused too, never written elsewhere
    assert sorted(p.name for p in elsewhere.iterdir()) == [put.path.name]


def test_store_roots_that_are_links_or_files_are_refused(tmp_path):
    (tmp_path / "real").mkdir()
    try:
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "objects").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(RawStoreError):
        RawObjectStore(tmp_path / "root")
    with pytest.raises(RawStoreError):
        RawObjectStore(tmp_path / "root", create=False)
    (tmp_path / "file").write_text("x")
    with pytest.raises((RawStoreError, FileExistsError, NotADirectoryError)):
        RawObjectStore(tmp_path / "file")


def test_published_objects_are_read_only_without_exec_bits(store):
    path = store.put(b"data").path
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o444 and not mode & 0o333
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses permission bits")
    with pytest.raises(PermissionError):
        open(path, "wb")  # noqa: SIM115


def test_an_existing_digest_is_never_rewritten_even_when_its_content_is_wrong(store):
    put = store.put(b"original")
    os.chmod(put.path, 0o644)
    put.path.write_bytes(b"EVIL")
    os.chmod(put.path, 0o444)
    before = os.stat(put.path)
    with pytest.raises(DigestCollisionError):
        store.put(b"original")
    after = os.stat(put.path)
    assert (before.st_ino, before.st_mtime_ns, put.path.read_bytes()) == (after.st_ino, after.st_mtime_ns, b"EVIL")
    assert list(store.tmp_dir.iterdir()) == []


def test_hostile_bytes_are_stored_verbatim(store):
    separator = "\u2028"  # a real U+2028 inside a record must survive: it is not a line break (G.3.3)
    for data in (b"\x00" * 10, b"\xef\xbb\xbf{}", b"line\r\nline\r\n", b"\xff\xfe\x00bad utf-8", ('{"a":"x' + separator + 'y"}\n').encode(), bytes(range(256))):
        put = store.put(data)
        assert store.read_bytes(put.sha256) == data and put.sha256 == hashlib.sha256(data).hexdigest()


def test_oversize_streams_are_cut_off_and_leave_nothing(tmp_path):
    limits = IngestLimits().replace(max_artefact_bytes=4096)
    store = RawObjectStore(tmp_path / "raw", limits=limits)

    class Endless(io.RawIOBase):
        def readable(self):
            return True

        def readinto(self, b):
            b[:] = b"x" * len(b)
            return len(b)

    with pytest.raises(IngestError) as exc:
        store.put_stream(io.BufferedReader(Endless()), chunk_size=1024)
    assert exc.value.code == "ingest.size.file"
    assert list(store.digests()) == [] and list(store.tmp_dir.iterdir()) == []


@pytest.mark.parametrize(
    "field", ["path", "label"]
)
def test_origin_strings_cannot_forge_jsonl_lines(field):
    for evil in ("a\n{\"origin\":{}}", "a\r\nb", "a\x00b", "a\u0085b"):
        with pytest.raises(OriginError):
            if field == "path":
                Origin.local(evil)
            else:
                Origin.member("a" * 64, evil, 8, 0, 0)


def test_origin_rows_stay_one_line_each_even_with_quotes_and_unicode(store):
    log = OriginLog()
    log.add("a" * 64, Origin.member("b" * 64, 'we"ird \\ name ☃ \u202e rtl.json', 8, 1, 1))
    data = log.serialise()
    assert data.count(b"\n") == 1
    assert decode_origins(data)[0].origin.data["label"] == 'we"ird \\ name ☃ \u202e rtl.json'


def test_no_raw_store_module_imports_a_network_or_process_module():
    import ast
    import pathlib

    import agentprov.raw as raw

    forbidden = {"socket", "subprocess", "urllib", "http", "shutil", "pickle", "marshal", "tarfile", "platform", "dotenv"}
    # `fetch.py` is the one home of the network and of the `git` subprocess in the raw layer (MN M.5.3, G.7.5); its own
    # tests (tests/unit/raw/test_fetch*.py, tests/security/test_fetch_hardening.py) hold it to its rules. The dangerous
    # attribute check below still covers it.
    network_home = {"fetch.py"}
    for path in pathlib.Path(raw.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if path.name in network_home:
                pass
            elif isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & forbidden, path.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, path.name
            elif isinstance(node, ast.Attribute):
                assert node.attr not in {"extract", "extractall", "unpack_archive", "system", "popen"}, path.name
