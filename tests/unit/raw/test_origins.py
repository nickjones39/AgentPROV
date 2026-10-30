"""Origin records and ``raw/origins.jsonl`` (C.3.12; HL H.1.4, H.2.3; K.5.7(2); G.9.6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentprov.raw.origins import (
    Origin,
    OriginError,
    OriginLog,
    OriginRow,
    OriginUnpinnedError,
    crc32_hex,
    decode_origins,
    encode_origins,
    redact_personal,
)

C40 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
B40 = "4cbf084087345a813c6d93e99aa2d37eec2ca507"
H64 = "ab" * 32
UUID7 = "018f3a4e-7b2c-7d3a-8c1e-0123456789ab"

VALID = [
    Origin.git("https://github.com/ethz-spylab/agentdojo", C40, "runs/x.json", B40),
    Origin.git("https://github.com/ethz-spylab/agentdojo", C40, "runs/x.json", B40, introduced_in_commit=B40),
    Origin.hf("owner/data", C40, "a/b.eval"),
    Origin.zenodo("10.5281/zenodo.12528189", "agentdojo-v0.1.7.zip"),
    Origin.url("https://example.org/a.json", "2026-10-08"),
    Origin.corpus("AgentDojo-PROV", "2.3", "corpus-prov/x.json", producer_commit=C40),
    Origin.capture(UUID7),
    Origin.member(H64, "samples/a_epoch_1.json", 8, 0xDEADBEEF, 123),
    Origin.local("/tmp/some/dir"),
]


@pytest.mark.parametrize("origin", VALID, ids=lambda o: o.kind + str(len(o.data)))
def test_every_kind_round_trips_through_json(origin):
    assert Origin.from_json(json.loads(json.dumps(origin.to_json()))) == origin
    assert origin.to_json()["kind"] == origin.kind


def test_all_eight_kinds_are_covered():
    assert {o.kind for o in VALID} == {"git", "hf", "zenodo", "url", "corpus", "capture", "member", "local"}


def test_member_crc32_is_eight_lowercase_hex_digits():
    assert crc32_hex(0xAB) == "000000ab" and Origin.member(H64, "a", 0, 0, 0).data["crc32"] == "00000000"
    for bad in (-1, 2**32, True):
        with pytest.raises(ValueError):
            crc32_hex(bad)
    with pytest.raises(OriginError):
        Origin.member(H64, "a", 8, "DEADBEEF", 1)


@pytest.mark.parametrize("commit", ["main", "latest", "", "v1.0", C40[:39], C40.upper(), C40 + "0", None])
def test_git_commit_must_be_a_full_40_hex_commit(commit):
    with pytest.raises(OriginUnpinnedError) as exc:
        Origin.git("https://github.com/o/r", commit, "p", B40)
    assert exc.value.code == "raw.origin.unpinned" and exc.value.exit_code == 3


@pytest.mark.parametrize("revision", ["main", "", "refs/heads/x", C40[:7]])
def test_hf_revision_must_be_pinned(revision):
    with pytest.raises(OriginUnpinnedError):
        Origin.hf("o/d", revision, "p")


def test_other_malformed_fields_are_plain_origin_errors():
    with pytest.raises(OriginError) as exc:
        Origin.git("https://github.com/o/r", C40, "p", "nothex")
    assert not isinstance(exc.value, OriginUnpinnedError) and exc.value.code == "raw.origin.invalid"
    for call in (
        lambda: Origin.git("http://github.com/o/r", C40, "p", B40),  # https only
        lambda: Origin.url("https://x.org/a", "2026-13-01"),  # not a calendar date
        lambda: Origin.url("https://x.org/a", "2026-10-08T00:00:00Z"),  # a date, not a timestamp
        lambda: Origin.url("https://x.org/a", ""),
        lambda: Origin.capture("not-a-uuid"),
        lambda: Origin.capture("018f3a4e-7b2c-4d3a-8c1e-0123456789ab"),  # not version 7
        lambda: Origin.member("short", "a", 8, 1, 1),
        lambda: Origin.member(H64, "a", 12, 1, 1),  # bzip2 is not an allowed method
        lambda: Origin.member(H64, "a", 8, 1, -1),
        lambda: Origin.member(H64, "a\nb", 8, 1, 1),
        lambda: Origin.zenodo("", "f"),
        lambda: Origin.local(""),
        lambda: Origin("git", {"repo": "https://x/y"}),  # missing fields
        lambda: Origin("zenodo", {"doi": "d", "file": "f", "md5": "0" * 32}),  # unknown field (closed object)
        lambda: Origin("ftp", {}),
    ):
        with pytest.raises(OriginError):
            call()
    with pytest.raises(OriginError):
        Origin.from_json("not an object")
    with pytest.raises(OriginError):
        Origin.from_json({"repo": "x"})


def test_local_origin_writes_home_and_host_as_placeholders(tmp_path):
    assert Origin.local("/Users/alice/work/logs", home="/Users/alice", host="mac").data["path"] == "<home>/work/logs"
    assert Origin.local("/Users/alice/host-1/x", home="/Users/alice", host="host-1").data["path"] == "<home>/<host>/x"
    assert redact_personal("see /Users/alice and /Users/alice/y", home="/Users/alice", host="") == "see <home> and <home>/y"
    # never substitute a home of "/" or a very short host name, which would damage ordinary text
    assert redact_personal("/etc/hosts ab", home="/", host="ab") == "/etc/hosts ab"
    # the host only as a whole token
    assert redact_personal("myhost.example myhost x-myhost", home="/h", host="myhost") == "myhost.example <host> x-myhost"
    assert redact_personal("C:\\Users\\bob\\x", home="C:\\Users\\bob", host="") == "<home>\\x"


def test_default_home_is_the_running_users_home():
    home = str(Path.home())
    if len(home.rstrip("/\\")) > 1:
        assert Origin.local(home + "/data").data["path"].startswith("<home>")


def test_row_and_line_shape():
    row = OriginRow(H64, VALID[3])
    assert row.to_json() == {"origin": {"doi": "10.5281/zenodo.12528189", "file": "agentdojo-v0.1.7.zip", "kind": "zenodo"}, "sha256": "sha256:" + H64}
    assert row.line() == (
        b'{"origin":{"doi":"10.5281/zenodo.12528189","file":"agentdojo-v0.1.7.zip","kind":"zenodo"},"sha256":"sha256:' + H64.encode() + b'"}\n'
    )


def test_encode_sorts_by_digest_then_origin_and_removes_duplicates():
    a, b = "0" * 64, "f" * 64
    rows = [OriginRow(b, VALID[3]), OriginRow(a, VALID[4]), OriginRow(a, VALID[3]), OriginRow(a, VALID[3])]
    data = encode_origins(rows)
    parsed = decode_origins(data)
    # JCS(origin) of a zenodo record starts with {"doi"..., a url record with {"kind"...: "d" sorts before "k"
    assert [(r.sha256, r.origin.kind) for r in parsed] == [(a, "zenodo"), (a, "url"), (b, "zenodo")]
    assert len(parsed) == 3 and data.endswith(b"\n") and b"\r" not in data
    assert encode_origins(reversed(rows)) == data  # insertion order does not matter


def test_empty_set_is_a_zero_byte_file():
    assert encode_origins([]) == b"" and decode_origins(b"") == []


def test_decode_is_strict():
    good = encode_origins([OriginRow(H64, VALID[3])])
    with pytest.raises(OriginError):
        decode_origins(good + good)  # repeated row
    two = encode_origins([OriginRow("0" * 64, VALID[3]), OriginRow("1" * 64, VALID[3])])
    first, second = two.splitlines(keepends=True)
    with pytest.raises(OriginError) as exc:
        decode_origins(second + first)
    assert exc.value.code == "raw.origin.unsorted"
    for bad in (good.rstrip(b"\n"), good.replace(b"\n", b"\r\n"), b"\n" + good, b'{"origin":{},"sha256":"x"}\n', b"[]\n"):
        with pytest.raises(OriginError):
            decode_origins(bad)
    with pytest.raises(OriginError):
        decode_origins(good.replace(b"sha256:", b""))  # a bare digest is not the corpus-layer spelling


def test_origin_log_is_idempotent_counts_and_writes_atomically(tmp_path):
    log = OriginLog()
    assert log.add(H64, VALID[3]) is True and log.add(H64, VALID[3]) is False
    assert log.add(H64, VALID[4]) is True
    assert log.count(H64) == 2 and log.count("0" * 64) == 0 and len(log) == 2
    assert [o.kind for o in log.origins_of(H64)]
    path = tmp_path / "origins.jsonl"
    log.write(path)
    assert path.read_bytes() == log.serialise()
    assert OriginLog.load(path).rows() == log.rows()
    OriginLog().write(path)
    assert path.read_bytes() == b""


def test_row_requires_a_digest():
    with pytest.raises(OriginError):
        OriginRow("nothex", VALID[3])
