"""``tools/release_scan.py`` reads unselected archive members for the home path and host name (D-491; core review B,
CB-16).

``path_scan`` used to search stored bytes only, and gitleaks runs at ``--max-archive-depth 0``, so a home path inside a
deflated (or tar.gz / tar.zst) member that the profile never selected passed the release scan with no finding. The scan
now reads every stored archive decoded through D-450's bounded ``expand`` path (:mod:`agentprov.corpus.withhold_scan`),
reports a hit as ``<label>#<member index>`` and fails closed with ``home-path-unscanned`` for an archive it cannot read.
The needles are synthetic; archives are built here (writing them is trusted code).
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import lzma
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "security"))

import format_support as fs  # noqa: E402
import release_support as rs  # noqa: E402

from agentprov.raw.members import MemberRow, encode_members  # noqa: E402
from agentprov.raw.origins import Origin, OriginRow, encode_origins  # noqa: E402

_TOOL = Path(__file__).resolve().parents[3] / "tools" / "release_scan.py"
_spec = importlib.util.spec_from_file_location("release_scan_tool_d491", _TOOL)
assert _spec is not None and _spec.loader is not None
release_scan = importlib.util.module_from_spec(_spec)
sys.modules["release_scan_tool_d491"] = release_scan
_spec.loader.exec_module(release_scan)

HOME, HOST = "/Users/synthetic-reviewer", "synthetic-host.example"
NEEDLES = release_scan.personal_needles(home=HOME, host=HOST)
#: In-process dispatch is for tests only and refused in release mode (G.4); one test below runs the T1 workers.
FAST = {"in_process": True, "release": False}
CLEAN = b'{"ok": true, "text": "' + b"x" * 300 + b'"}\n'
PERSONAL = (b'{"header": 1}\n{"eval": {"task_file": "' + HOME.encode() + b'/inspect/task.py"}}\n'
            b'{"host": "' + HOST.encode() + b'"}\n')  # home path on line 2, host name on line 3


@pytest.fixture(autouse=True)
def _scratch_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))  # the decoded scan's scratch store lives here


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _crc(data: bytes) -> str:
    return f"{zlib.crc32(data):08x}"


def _put(root: Path, data: bytes, ext: str) -> str:
    """Store ``data`` as a raw object of the tree; returns its label."""
    sha = _sha(data)
    label = f"raw/objects/{sha[:2]}/{sha}.{ext}"
    (root / label).parent.mkdir(parents=True, exist_ok=True)
    (root / label).write_bytes(data)
    return label


def _found(root: Path, **kwargs):
    return [(f.path, f.rule, f.line) for f in release_scan.path_scan(root, NEEDLES, **{**FAST, **kwargs})]


def _assert_hidden(archive: bytes) -> None:
    assert HOME.encode() not in archive and HOST.encode() not in archive  # compressed: the stored bytes never hold it


# ------------------------------------------------------------------------------------------------ hits in members
def test_a_deflated_zip_member_holding_the_home_path_is_a_finding(tmp_path):
    archive = fs.zip_bytes([("header.json", CLEAN), ("_journal/start.json", PERSONAL * 3)])
    _assert_hidden(archive)
    label = _put(tmp_path, archive, "eval")
    assert _found(tmp_path) == [(f"{label}#1", "home-path", 2), (f"{label}#1", "home-path", 5),
                                (f"{label}#1", "home-path", 8), (f"{label}#1", "host-name", 3),
                                (f"{label}#1", "host-name", 6), (f"{label}#1", "host-name", 9)]  # fmt: skip


def test_a_gzip_tar_member_is_a_finding(tmp_path):
    archive = gzip.compress(fs.tar_bytes([("chats/a.json", CLEAN), ("chats/session.json", PERSONAL)]), mtime=0)
    _assert_hidden(archive)
    label = _put(tmp_path, archive, "gz")
    assert _found(tmp_path) == [(f"{label}#1", "home-path", 2), (f"{label}#1", "host-name", 3)]


def test_a_zstd_tar_member_is_a_finding(tmp_path):
    archive = fs.tzst([("claude_code/a.json", CLEAN), ("claude_code/b.json", PERSONAL)])
    _assert_hidden(archive)
    label = _put(tmp_path, archive, "zst")
    assert _found(tmp_path) == [(f"{label}#1", "home-path", 2), (f"{label}#1", "host-name", 3)]


def test_a_member_name_holding_the_home_path_is_a_finding_on_line_0(tmp_path):
    archive = gzip.compress(fs.tar_bytes([("x" + HOME + "/notes.json", CLEAN)]), mtime=0)  # the tar header is compressed
    _assert_hidden(archive)
    label = _put(tmp_path, archive, "gz")
    assert _found(tmp_path) == [(f"{label}#0", "home-path", 0)]


def test_a_member_of_a_nested_archive_is_located_through_its_parent(tmp_path):
    inner = fs.zip_bytes([("a.json", CLEAN), ("b.json", PERSONAL)])
    outer = fs.zip_bytes([("logs/readme.json", CLEAN), ("logs/inner.zip", inner)])
    label = _put(tmp_path, outer, "zip")
    assert _found(tmp_path) == [(f"{label}#1!1", "home-path", 2), (f"{label}#1!1", "host-name", 3)]


def test_a_third_party_account_path_in_a_zip_member_is_a_finding(tmp_path):
    """D-457: the account-path rule reads decoded members as the home-path rule does; the operator's own home path
    (HOME, a ``/Users/<name>`` path) stays ``home-path`` only."""
    other = b'{"a": 1}\n{"cwd": "C:\\\\Users\\\\zq-synthetic\\\\run"}\n'  # JSON-escaped Windows form, line 2
    archive = fs.zip_bytes([("header.json", CLEAN), ("run_manifest.json", other * 3), ("_journal/start.json", PERSONAL)])
    assert b"zq-synthetic" not in archive  # deflated: the stored bytes never hold it
    label = _put(tmp_path, archive, "eval")
    assert _found(tmp_path) == [(f"{label}#1", "account-path", 2), (f"{label}#1", "account-path", 4),
                                (f"{label}#1", "account-path", 6), (f"{label}#2", "home-path", 2),
                                (f"{label}#2", "host-name", 3)]  # fmt: skip
    assert _found(tmp_path, accounts=False) == [(f"{label}#2", "home-path", 2), (f"{label}#2", "host-name", 3)]


def test_the_archives_are_read_by_t1_workers(tmp_path):
    archive = fs.zip_bytes([("header.json", CLEAN), ("_journal/start.json", PERSONAL)])
    label = _put(tmp_path, archive, "eval")
    found = [(f.path, f.rule, f.line) for f in release_scan.path_scan(tmp_path, NEEDLES)]  # defaults: T1, release mode
    assert found == [(f"{label}#1", "home-path", 2), (f"{label}#1", "host-name", 3)]


# ------------------------------------------------------------------------------------------------ fail closed
@pytest.mark.parametrize("shape", ["xz", "corrupt-zip", "too-deep"])
def test_an_archive_that_cannot_be_decoded_is_an_unscanned_finding(tmp_path, shape):
    if shape == "xz":
        data, ext = lzma.compress(PERSONAL), "xz"  # a deferred codec
    elif shape == "corrupt-zip":
        data, ext = b"PK\x03\x04" + b"\x00" * 200, "zip"
    else:  # three levels of zip: one beyond the default max_archive_depth (2)
        level3 = fs.zip_bytes([("c.json", CLEAN)])
        data, ext = fs.zip_bytes([("b.zip", fs.zip_bytes([("c.zip", level3)]))]), "zip"
    label = _put(tmp_path, data, ext)
    found = _found(tmp_path)
    assert (label, "home-path-unscanned", 0) in found
    assert all(rule == "home-path-unscanned" for _path, rule, _line in found)


def test_a_declared_nesting_allowance_reads_the_deeper_level(tmp_path):
    level3 = fs.zip_bytes([("c.json", PERSONAL)])
    data = fs.zip_bytes([("b.zip", fs.zip_bytes([("c.zip", level3)]))])
    label = _put(tmp_path, data, "zip")
    assert _found(tmp_path, max_depth=3) == [(f"{label}#0!0!0", "home-path", 2), (f"{label}#0!0!0", "host-name", 3)]


# ------------------------------------------------------------------------------------------------ unchanged
def test_a_plain_file_still_gives_its_finding(tmp_path):
    label = _put(tmp_path, PERSONAL, "json")
    (tmp_path / "corpus.json").write_bytes(b'{"x": 1}\n')
    assert _found(tmp_path) == [(label, "home-path", 2), (label, "host-name", 3)]


def test_an_archive_without_a_hit_gives_no_finding(tmp_path):
    _put(tmp_path, fs.zip_bytes([("a.json", CLEAN), ("b.json", CLEAN * 2)]), "zip")
    _put(tmp_path, gzip.compress(fs.tar_bytes([("a.json", CLEAN)]), mtime=0), "gz")
    _put(tmp_path, CLEAN, "json")
    assert _found(tmp_path) == []


def test_a_selected_member_is_scanned_as_its_own_object_not_through_its_container(tmp_path):
    """A member the corpus stores (raw/members.jsonl, confirmed by its member origin) is found once, as its own object;
    the unselected member beside it is read through the container."""
    archive = fs.zip_bytes([("samples/s1.json", PERSONAL), ("_journal/start.json", PERSONAL + CLEAN)])
    label = _put(tmp_path, archive, "eval")
    member = _put(tmp_path, PERSONAL, "json")
    rows = [MemberRow(_sha(archive), "f" * 64, "samples/s1.json", 8, _crc(PERSONAL), len(PERSONAL), _sha(PERSONAL),
                      "selected"),
            MemberRow(_sha(archive), "f" * 64, "_journal/start.json", 8, "00000000", 1, None, "not_selected")]
    (tmp_path / "raw/members.jsonl").write_bytes(encode_members(rows))
    (tmp_path / "raw/origins.jsonl").write_bytes(encode_origins([OriginRow(_sha(PERSONAL), Origin.member(
        _sha(archive), "samples/s1.json", 8, _crc(PERSONAL), len(PERSONAL)))]))
    assert sorted(_found(tmp_path)) == sorted([(f"{label}#1", "home-path", 2), (f"{label}#1", "host-name", 3),
                                               (member, "home-path", 2), (member, "host-name", 3)])  # fmt: skip


# ------------------------------------------------------------------------------------------------ secret shapes (D-600)
def _secrets(root: Path, **kwargs):
    return [(f.path, f.rule, f.line) for f in release_scan.path_scan(root, {}, accounts=False, **{**FAST, **kwargs})]


@pytest.mark.parametrize("index", range(len(rs.secret_shapes())))
def test_each_secret_shape_in_a_deflated_zip_member_is_a_finding(tmp_path, index):
    """gitleaks runs at ``--max-archive-depth 0`` and never sees a member; the native rules read it decoded."""
    rule, value = rs.secret_shapes(6)[index]
    member = (b'{"a": 1}\n{"env": {"TOKEN": "' + value.encode() + b'"}}\n') * 3  # lines 2, 4 and 6
    archive = fs.zip_bytes([("header.json", CLEAN), ("_journal/start.json", member)])
    assert value.encode() not in archive and value[-12:].encode() not in archive  # deflated
    label = _put(tmp_path, archive, "eval")
    assert _secrets(tmp_path) == [(f"{label}#1", rule, n) for n in (2, 4, 6)]
    assert _secrets(tmp_path, secrets=False) == []


def test_a_secret_shape_in_a_tar_gz_member_name_and_a_nested_zip_is_a_finding(tmp_path):
    shapes = dict(rs.secret_shapes(7)[::-1])
    named = gzip.compress(fs.tar_bytes([("logs/" + shapes["huggingface-access-token"] + ".json", CLEAN)]), mtime=0)
    inner = fs.zip_bytes([("a.json", CLEAN), ("b.json", b"x\n" + shapes["langfuse-secret-key"].encode() + b"\n")])
    outer = fs.zip_bytes([("logs/readme.json", CLEAN), ("logs/inner.zip", inner)])
    a, b = _put(tmp_path, named, "gz"), _put(tmp_path, outer, "zip")
    assert sorted(_secrets(tmp_path)) == sorted([(f"{a}#0", "huggingface-access-token", 0),
                                                 (f"{b}#1!1", "langfuse-secret-key", 2)])  # fmt: skip


def test_near_misses_in_a_member_are_not_findings(tmp_path):
    shapes = dict(rs.secret_shapes(8)[::-1])
    misses = ["x" + shapes["github-pat"], shapes["github-pat"] + "Z", shapes["huggingface-access-token"][:-1],
              "sk" + "-lf-" + "0" * 36]
    _put(tmp_path, fs.zip_bytes([("a.json", "\n".join(misses).encode() + b"\n")]), "zip")
    assert _secrets(tmp_path) == []


def test_the_backstop_refuses_a_synthetic_benchmark_triage_of_a_member_github_pat(tmp_path):
    """D-236: a ``[withhold]`` policy whose ``scan_rules`` names ``github-pat`` refuses the deposit unless the finding is
    triaged ``false-positive``; a native finding in an archive member is covered like a gitleaks one
    (:func:`agentprov.release.metadata.check_withhold_scan`, which the deposit builder calls)."""
    from agentprov.release.metadata import check_withhold_scan

    value = rs.secret_shapes(9)[0][1]
    label = _put(tmp_path, fs.zip_bytes([("header.json", CLEAN), ("run.json", b'{"t": "' + value.encode() + b'"}\n')]),
                 "zip")
    findings = release_scan.path_scan(tmp_path, {}, **FAST)
    assert [f.fingerprint for f in findings] == [f"{label}#1:github-pat:1"]
    digest = "sha256:" + "a" * 64
    for triage, missed in (("synthetic-benchmark", 1), ("real", 1), ("false-positive", 0)):
        text = (f'root_digest = "{digest}"\n[[triage]]\nfingerprint = "{label}#1:github-pat:1"\n'
                f'triage = "{triage}"\nreason = "synthetic test"\n').encode()
        doc = release_scan.scan_document({"root_digest": digest}, [], findings, release_scan.load_triage(text))
        assert check_withhold_scan(doc, ["github-pat"]) == missed
        assert check_withhold_scan(doc, ["aws-access-token"]) == 0
        assert value not in json.dumps(doc) and value[-12:] not in json.dumps(doc)


def test_the_scan_document_records_the_new_path_scan_version():
    assert release_scan.PATH_SCAN_VERSION == "6"  # 3: account paths (D-457); 4: secret shapes (D-600); 5, 6: e-mail (D-810)
