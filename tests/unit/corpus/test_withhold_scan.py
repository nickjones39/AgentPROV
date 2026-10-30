"""The decoded scan of stored archives for the ``[withhold]`` byte rules (D-450; bug pass BF-18).

A canary in a deflated member the profile never selected used to ship inside the released container: the planner, the
``chain`` and deposit-builder rescans and gitleaks all saw only the compressed bytes. Synthetic archives built here (zip,
nested zip, tar.zst, split zip, deferred codecs); the reachable shapes of D.23.7 (geminicli: a key-shaped value in a
``claude_code`` file the profile does not select, in a zstd tar) and D-265 (credleak: collector logs the profile does not
select, in a zip) use the shipped profiles' own policies. Secret-shaped values are assembled at run time and never
printed; assertions compare rule ids and codes, never values.
"""

from __future__ import annotations

import bz2
import gzip
import hashlib
import sys
import tomllib
import zlib
from collections.abc import Iterable, Mapping
from importlib import resources
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "security"))

import format_support as fs  # noqa: E402

from agentprov.corpus import withhold as wh  # noqa: E402
from agentprov.corpus.withhold_scan import DECODED_DETECTOR, scan_archives  # noqa: E402
from agentprov.raw.members import MemberRow, split_descriptor  # noqa: E402
from agentprov.raw.origins import Origin, OriginRow  # noqa: E402

SECRET = ("CAN" + "ARY-") + "ABCDEFGH"  # assembled at run time
POLICY = wh.parse_policy(tomllib.loads('''
[withhold]
reason = "secret"
public_note = "a planted test canary"
[[withhold.rules]]
id = "canary"
pattern = "CANARY-[A-Z]{8}"
scope = "executions"
'''), profile_id="tst", profile_version=1, profile_sha256="sha256:" + "0" * 64)
CLEAN = b'{"ok": true, "text": "' + b"x" * 400 + b'"}'
HIDDEN = b'{"API_KEY": "' + SECRET.encode() + b'", "pad": "' + b"y" * 400 + b'"}'


def _store(*blobs: tuple[bytes, str]) -> tuple[dict[str, str], dict[str, bytes]]:
    """``(objects, files)``: bare hex -> corpus label, and label -> bytes."""
    objects, files = {}, {}
    for data, ext in blobs:
        sha = hashlib.sha256(data).hexdigest()
        label = f"raw/objects/{sha[:2]}/{sha}.{ext}"
        objects[sha], files[label] = label, data
    return objects, files


def _stream(files: Mapping[str, bytes]):
    def stream(label: str) -> Iterable[bytes]:
        data = files[label]
        return [data[i : i + 7] for i in range(0, len(data), 7)] or [b""]  # small chunks: matches straddle them

    return stream


def _scan(*blobs: tuple[bytes, str], in_process: bool = True):
    objects, files = _store(*blobs)
    # in-process dispatch is for tests only and refused in release mode (G.4); the T1 path has its own test below
    return objects, scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=in_process,
                                  release=not in_process)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _crc(data: bytes) -> str:
    return f"{zlib.crc32(data):08x}"


def _unstored(container: bytes, *labels: str) -> list[MemberRow]:
    """``not_selected`` rows: members the corpus lists but does not store (the scan reads them through the container)."""
    return [MemberRow(_sha(container), "f" * 64, label, 8, "00000000", 1, None, "not_selected") for label in labels]


def _row(container: bytes, label: str, data: bytes) -> MemberRow:
    """A ``selected`` row of ``raw/members.jsonl``: ``data`` stored as the member ``label`` of ``container``."""
    return MemberRow(_sha(container), "f" * 64, label, 8, _crc(data), len(data), _sha(data), "selected")


# ------------------------------------------------------------------------------------------------ the scanner
def test_a_member_the_profile_never_selected_is_read_decoded():
    archive = fs.zip_bytes([("results/run1.json", CLEAN), ("config/env.json", HIDDEN)])
    assert SECRET.encode() not in archive  # deflated: the stored bytes never hold it
    _objects, scan = _scan((archive, "zip"))
    assert scan.hits == {_sha(archive): frozenset({"canary"})} and scan.unscanned == {}


def test_a_clean_archive_and_a_plain_document_give_nothing():
    _objects, scan = _scan((fs.zip_bytes([("a.json", CLEAN)]), "zip"), (CLEAN, "json"))
    assert scan.hits == {} and scan.unscanned == {}


def test_a_nested_archive_is_read_in_turn():
    archive = fs.zip_bytes([("a.json", CLEAN), ("inner.zip", fs.zip_bytes([("deep/env.json", HIDDEN)]))])
    _objects, scan = _scan((archive, "zip"))
    assert scan.hits == {_sha(archive): frozenset({"canary"})} and scan.unscanned == {}


def test_nesting_deeper_than_the_limit_is_unscanned():
    archive = fs.zip_bytes([("1.zip", fs.zip_bytes([("2.zip", fs.zip_bytes([("env.json", HIDDEN)]))]))])
    _objects, scan = _scan((archive, "zip"))
    assert scan.hits == {} and scan.unscanned == {_sha(archive): "ingest.archive.depth"}


def test_a_tar_zst_is_read_decoded():
    archive = fs.tzst([("cells/claude_code__m/s__v/transcript.jsonl", HIDDEN), ("cells/gemini/stream.jsonl", CLEAN)])
    assert SECRET.encode() not in archive
    _objects, scan = _scan((archive, "zst"))
    assert scan.hits == {_sha(archive): frozenset({"canary"})} and scan.unscanned == {}


@pytest.mark.parametrize("pack", [gzip.compress, bz2.compress], ids=["gzip-document", "bz2"])
def test_a_compressed_stream_that_is_not_an_archive_is_unscanned(pack):
    data = pack(HIDDEN)
    _objects, scan = _scan((data, "bin"))
    assert scan.hits == {} and scan.unscanned == {_sha(data): "ingest.stream.codec"}


def test_a_split_archive_is_read_through_its_parts_and_reported_on_its_descriptor():
    archive = fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)])
    parts = fs.split(archive, 100)
    assert len(parts) >= 3
    descriptor = split_descriptor([(_sha(p), len(p)) for p in parts])
    _objects, scan = _scan((descriptor, "json"), *((p, "bin") for p in parts))
    assert scan.hits == {_sha(descriptor): frozenset({"canary"})} and scan.unscanned == {}


def test_bytes_that_do_not_match_their_digest_are_unscanned():
    archive = fs.zip_bytes([("config/env.json", HIDDEN)])
    objects, files = _store((archive, "zip"))
    label = next(iter(files))
    files[label] = fs.zip_bytes([("config/env.json", CLEAN)])  # the tree changed under its label
    scan = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False)
    assert scan.hits == {} and scan.unscanned == {_sha(archive): "raw.object.mismatch"}


def test_the_archives_are_opened_by_t1_workers():
    archive = fs.zip_bytes([("results/run1.json", CLEAN), ("config/env.json", HIDDEN)])
    _objects, scan = _scan((archive, "zip"), in_process=False)
    assert scan.hits == {_sha(archive): frozenset({"canary"})}


def test_zero_byte_objects_and_members_count_as_scanned():
    empty_member = fs.zip_bytes([("logs/empty.eval", b""), ("a.json", CLEAN)])
    _objects, scan = _scan((b"", "bin"), (empty_member, "zip"))
    assert scan.hits == {} and scan.unscanned == {}


# ------------------------------------------------------------------------------------------------ fail closed
def _hidden_zip() -> bytes:
    return fs.zip_bytes([("config/env.json", HIDDEN)])


@pytest.mark.parametrize(("shape", "code"), [
    ("plain-tar", "ingest.archive.format"),  # an uncompressed tar holding a deflated zip
    ("stub-zip", "ingest.archive.prefix"),  # a zip behind a shell stub (self-extractor shape)
    ("spanned-zip", "ingest.archive.format"),
    ("7z", "ingest.archive.format"),
    ("rar", "ingest.archive.format"),
    ("xz", "ingest.stream.codec"),
])
def test_an_archive_the_scan_cannot_open_is_unscanned_never_a_document(shape, code):
    """Review of D-450: only a zip at offset 0 or a gzip/zstd stream is opened; anything else that looks like an archive
    or a compressed stream fails closed, as a stored object and as a member."""
    data = {
        "plain-tar": fs.tar_bytes([("inner.zip", _hidden_zip())]),
        "stub-zip": b"#!/bin/sh\nexit 0\n" + _hidden_zip(),
        "spanned-zip": b"PK\x07\x08" + _hidden_zip(),
        "7z": b"7z\xbc\xaf\x27\x1c" + b"\x00" * 40,
        "rar": b"Rar!\x1a\x07\x01\x00" + b"\x00" * 40,
        "xz": b"\xfd7zXZ\x00" + b"\x00" * 40,
    }[shape]
    _objects, scan = _scan((data, "bin"))
    assert scan.unscanned == {_sha(data): code}
    outer = fs.zip_bytes([("a.json", CLEAN), ("odd.bin", data)])
    _objects, scan = _scan((outer, "zip"))
    assert scan.unscanned == {_sha(outer): code}


def test_documents_that_only_resemble_an_archive_are_documents():
    text = b"BZh is how this note begins, and it is plain text.\n" + CLEAN
    empty_zip = fs.zip_bytes([])
    _objects, scan = _scan((text, "txt"), (empty_zip, "zip"))
    assert scan.unscanned == {} and scan.hits == {}


def test_a_canary_in_a_member_label_is_found():
    archive = fs.zip_bytes([(f"logs/{SECRET}.json", CLEAN)])
    _objects, scan = _scan((archive, "zip"))
    assert scan.hits == {_sha(archive): frozenset({"canary"})}


def test_bytes_after_a_zips_end_record_are_unscanned():
    archive = fs.zip_bytes([("a.json", CLEAN)]) + gzip.compress(HIDDEN)
    _objects, scan = _scan((archive, "zip"))
    assert scan.unscanned == {_sha(archive): "ingest.archive.trailing"}


def test_the_decoded_bytes_of_one_root_are_bounded_and_the_scratch_store_is_removed(monkeypatch, tmp_path):
    from agentprov.ingest.limits import IngestLimits

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    archive = fs.zip_bytes([(f"m{i}.json", CLEAN) for i in range(4)] + [("z.json", HIDDEN)])
    objects, files = _store((archive, "zip"))
    limits = IngestLimits().replace(max_total_bytes=2 * len(CLEAN))
    scan = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False, limits=limits)
    assert scan.unscanned == {_sha(archive): "ingest.archive.size"}  # the job's own bound: selected members exceed it
    assert list((tmp_path / "home" / "tmp").iterdir()) == []


def test_a_worker_pool_that_cannot_start_leaves_every_archive_unscanned(monkeypatch):
    from agentprov.corpus import withhold_scan
    from agentprov.io.workers import IsolationInsufficientError

    def refuse(**_kwargs):
        raise IsolationInsufficientError("this host gives only degraded isolation")

    monkeypatch.setattr(withhold_scan, "WorkerPool", refuse)
    archive = _hidden_zip()
    _objects, scan = _scan((archive, "zip"), (CLEAN, "json"))
    assert scan.unscanned == {_sha(archive): "worker.isolation.insufficient"} and scan.hits == {}


def test_a_part_of_a_split_archive_that_cannot_be_read_whole_is_read_on_its_own():
    """A descriptor with a missing part is unscanned; its present parts are then read as archives of their own."""
    whole = _hidden_zip()
    descriptor = split_descriptor([(_sha(whole), len(whole)), ("e" * 64, 10)])
    _objects, scan = _scan((descriptor, "json"), (whole, "zip"))
    assert scan.unscanned == {_sha(descriptor): "raw.object.missing"}
    assert scan.hits == {_sha(whole): frozenset({"canary"})}


def test_an_end_record_that_carries_an_archive_in_its_comment_is_not_an_empty_zip():
    inner = _hidden_zip()
    record = b"PK\x05\x06" + b"\x00" * 16 + len(inner).to_bytes(2, "little") + inner
    _objects, scan = _scan((record, "zip"))
    assert scan.unscanned == {_sha(record): "ingest.archive.prefix"}


def test_a_listed_label_the_pattern_rules_refuse_does_not_crash_the_scan():
    """A label with a control character round-trips through raw/members.jsonl; the selection falls back to every
    member instead of raising, and the member-name gate then refuses the label: unscanned, never a crash."""
    archive = fs.zip_bytes([("a\x01.json", HIDDEN), ("b.json", CLEAN)])
    objects, files = _store((archive, "zip"), (CLEAN, "json"))
    members = [*_unstored(archive, "a\x01.json"), _row(archive, "b.json", CLEAN)]
    scan = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False, members=members)
    assert scan.unscanned == {_sha(archive): "ingest.name.invalid"}


def test_whole_directories_of_unstored_members_fold_into_one_pattern():
    from agentprov.corpus.withhold_scan import _fold

    wanted = [f"logs/run{i:05d}/trace.json" for i in range(3000)] + ["top.json", "mixed/x.json"]
    assert _fold(wanted, {"results/r1.json", "mixed/stored.json"}) == ["logs/**", "mixed/x.json", "top.json"]
    assert _fold(["a[1]/b*.json"], set()) == ["a[[]1]/**"]


def test_rescan_trusts_a_stored_member_row_only_with_its_member_origin():
    """chain reads the released raw/members.jsonl; a row that claims a member is stored as some released object counts
    only if raw/origins.jsonl records that member origin, so an edited members.jsonl alone cannot hide a member."""
    from agentprov.raw.members import encode_members
    from agentprov.raw.origins import encode_origins

    archive = fs.zip_bytes([("results/run1.json", CLEAN), ("config/env.json", HIDDEN)])
    decoy = b'{"decoy": true}'
    rows = [MemberRow(_sha(archive), "f" * 64, "config/env.json", 8, _crc(HIDDEN), len(HIDDEN), _sha(decoy), "selected"),
            _row(archive, "results/run1.json", CLEAN)]
    origin = OriginRow(_sha(CLEAN), Origin("member", {"container": _sha(archive), "label": "results/run1.json",
                                                       "method": 8, "crc32": _crc(CLEAN), "size": len(CLEAN)}))
    objects, files = _store((archive, "zip"), (CLEAN, "json"), (decoy, "json"))
    files["raw/members.jsonl"] = encode_members(rows)
    files["raw/origins.jsonl"] = encode_origins([origin])
    hits = wh.rescan(sorted(files), _stream(files), POLICY)
    assert (objects[_sha(archive)], "canary") in hits  # the doctored row did not hide config/env.json


# ------------------------------------------------------------------------------------------------ D-452: depth
def _three_levels(secret_in: str) -> tuple[bytes, bytes, bytes]:
    """split-zip-like outer zip > logs/a.zip > r.eval (a zip) > JSON members: the controlarena-persistent shape."""
    inner = HIDDEN if secret_in == "eval" else CLEAN
    eval_log = fs.zip_bytes([("header.json", CLEAN), ("samples/s1.json", inner)])
    blob = b"".join(hashlib.sha256(bytes([i])).digest() for i in range(64))  # 2 KiB that do not compress
    nested = fs.zip_bytes([("r.eval", eval_log), ("blob.bin", blob)])
    outer = fs.zip_bytes([("logs/a.zip", nested), ("README.md", CLEAN)])
    return outer, nested, eval_log


def test_a_declared_nesting_depth_is_honoured():
    outer, _nested, _eval_log = _three_levels("eval")
    objects, files = _store((outer, "zip"))
    default = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False)
    assert default.unscanned == {_sha(outer): "ingest.archive.depth"}  # level 3 is beyond the global 2
    declared = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False, max_depth=3)
    assert declared.hits == {_sha(outer): frozenset({"canary"})} and declared.unscanned == {}


def test_members_stored_as_their_own_objects_are_scanned_as_their_own_roots():
    """D-452: the import stored the nested zip and the .eval log; each is read decoded as its own root at level 1, so
    the global depth is enough and the hit is on the log that holds the canary."""
    outer, nested, eval_log = _three_levels("eval")
    objects, files = _store((outer, "zip"), (nested, "zip"), (eval_log, "eval"))
    members = [_row(outer, "logs/a.zip", nested), *_unstored(outer, "README.md"), _row(nested, "r.eval", eval_log),
               *_unstored(nested, "blob.bin")]
    scan = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False, members=members)
    assert scan.hits == {_sha(eval_log): frozenset({"canary"})} and scan.unscanned == {}
    # a row whose bytes differ from what the archive holds does not cover the member: it is read through its container
    forged = [MemberRow(_sha(outer), "f" * 64, "logs/a.zip", 8, "00000000", len(nested), _sha(nested), "selected"),
              *_unstored(outer, "README.md"), _row(nested, "r.eval", eval_log), *_unstored(nested, "blob.bin")]
    scan = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False, members=forged)
    assert scan.unscanned == {_sha(outer): "expand.not_selected"}


def test_a_member_stored_under_a_nested_raise_is_not_refused_by_the_scans_own_gate():
    """D-382/D-383: the import stored a nested zip above the global member bound; the scan's gate rejects it, but it is a
    corpus object of its own and is scanned as its own root."""
    from agentprov.ingest.limits import IngestLimits

    outer, nested, eval_log = _three_levels("none")
    objects, files = _store((outer, "zip"), (nested, "zip"), (eval_log, "eval"))
    limits = IngestLimits().replace(max_member_bytes=len(nested) - 1)
    assert len(nested) - 1 > max(len(CLEAN), len(eval_log), 2048)  # only the nested zip is over the bound
    unstored = scan_archives({_sha(outer): objects[_sha(outer)]}, _stream(files), POLICY.byte_rules, in_process=True,
                             release=False, limits=limits)  # fmt: skip
    assert unstored.unscanned == {_sha(outer): "ingest.archive.size"}
    members = [_row(outer, "logs/a.zip", nested), *_unstored(outer, "README.md"), _row(nested, "r.eval", eval_log),
               *_unstored(nested, "blob.bin")]
    scan = scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=True, release=False, limits=limits,
                         members=members)  # fmt: skip
    assert scan.hits == {} and scan.unscanned == {}


def test_the_policy_carries_the_profiles_declared_nesting_depth():
    doc = tomllib.loads('''
[import]
nested = [{ pattern = "logs/*.zip", max_depth = 3 }, { pattern = "deep/*.zip", max_depth = 4 }]
[withhold]
reason = "secret"
public_note = "n"
[[withhold.rules]]
id = "c"
marker = "abcd"
''')
    policy = wh.parse_policy(doc, profile_id="tst", profile_version=1, profile_sha256="sha256:" + "0" * 64)
    assert policy.archive_depth == 4 and policy.record() == _recorded(policy)
    assert POLICY.archive_depth is None


def _recorded(policy):
    """The recorded policy: it never carries the depth."""
    return wh.WithheldPolicy(policy.profile_id, policy.profile_version, policy.profile_sha256,
                             tuple((r.id, r.kind, r.scope) for r in policy.rules), policy.scan_rules)


# ------------------------------------------------------------------------------------------------ the planner
def _plan(policy, archive: bytes, ext: str, selected: Mapping[str, bytes], not_selected: Iterable[str],
          extra: Iterable[tuple[bytes, str]] = ()) -> wh.WithholdPlan:
    """A corpus of one stored archive, its selected members stored as their own objects, plus ``extra`` objects."""
    container = _sha(archive)
    fn = "f" * 64
    members, origins = [], [OriginRow(container, Origin("zenodo", {"doi": "10.5281/zenodo.1", "file": f"a.{ext}"}))]
    blobs = [(archive, ext)]
    for label, data in selected.items():
        members.append(MemberRow(container, fn, label, 8, _crc(data), len(data), _sha(data), "selected"))
        origins.append(OriginRow(_sha(data), Origin("member", {"container": container, "label": label, "method": 8,
                                                                 "crc32": _crc(data), "size": len(data)})))
        blobs.append((data, "json"))
    members += [MemberRow(container, fn, label, 8, "00000000", 1, None, "not_selected") for label in not_selected]
    for data, extra_ext in extra:
        origins.append(OriginRow(_sha(data), Origin("zenodo", {"doi": "10.5281/zenodo.1", "file": "b.bin"})))
        blobs.append((data, extra_ext))
    objects, files = _store(*blobs)
    present = {sha: (label, len(files[label])) for sha, label in objects.items()}
    return wh.plan_withholding(rows=[], register=[], members=members, origins=origins, present=present, tombstones=[],
                               snapshots={}, stream=_stream(files), derived=lambda r: [], artefacts=lambda r: [],
                               policy=policy)  # fmt: skip


def _shipped_policy(family: str, profile: str) -> wh.WithholdPolicy:
    data = resources.files("agentprov").joinpath("adapters", family, "profiles", f"{profile}.profile.toml").read_bytes()
    policy = wh.policy_of_profile(data, profile_id=profile, profile_version=1)
    assert policy is not None and policy.byte_rules
    return policy


def _entry(plan: wh.WithholdPlan, sha: str):
    assert plan.document is not None
    return next(e for e in plan.document.entries if e.sha256 == sha)


def test_geminicli_d23_7_a_key_in_an_unselected_claude_code_file_withholds_the_tar():
    """D.23.7: a key-shaped value in a ``claude_code`` file the profile does not select, inside the zstd tar."""
    policy = _shipped_policy("geminicli", "code-agent-misalignment-geminicli")
    key = ("AI" + "za" + "SyTEST0SENTINEL0bugpass0d450x000000").encode()
    assert len(key) == 39
    stream = b'{"type": "result"}\n'
    archive = fs.tzst([("RESULTS_build/cells/gemini_cli__m/s__v/gemini_stream.jsonl", stream),
                       ("RESULTS_build/cells/claude_code__m/s__v/transcript.jsonl", b'{"env": "' + key + b'"}\n')])
    assert key not in archive
    plan = _plan(policy, archive, "zst", {"RESULTS_build/cells/gemini_cli__m/s__v/gemini_stream.jsonl": stream},
                 ["RESULTS_build/cells/claude_code__m/s__v/transcript.jsonl"])
    entry = _entry(plan, _sha(archive))
    assert (entry.reason, entry.basis) == ("secret", "profile_rule")
    assert entry.finding is not None and entry.finding.detector == DECODED_DETECTOR
    assert entry.finding.rule.endswith(":google-api-key-shape") and entry.affected_executions == ()
    assert plan.objects == {_sha(archive)}  # the selected stream stays released: it holds no key


def test_credleak_d265_a_canary_in_an_unselected_collector_log_withholds_the_zip():
    """D-265: the collector logs the profile does not select, in the zip."""
    policy = _shipped_policy("credleak", "credleak-p15b")
    cell = b'{"cell": 1, "text": "' + b"z" * 300 + b'"}'
    log = b"egress: token=xCANARYx sent to collector\n" + b"q" * 300
    archive = fs.zip_bytes([("p15b-run-data/01-injection-map/cell.json", cell), ("p15b-run-data/collector/egress.log", log)])
    assert b"CANARY" not in archive
    plan = _plan(policy, archive, "zip", {"p15b-run-data/01-injection-map/cell.json": cell},
                 ["p15b-run-data/collector/egress.log"])
    entry = _entry(plan, _sha(archive))
    assert entry.basis == "profile_rule" and entry.finding is not None and entry.finding.detector == DECODED_DETECTOR
    assert plan.objects == {_sha(archive)}


def test_an_archive_withheld_by_its_member_keeps_the_container_basis():
    """A selected member holding the canary is withheld itself; its archive by the closure, as before D-450."""
    archive = fs.zip_bytes([("results/run1.json", HIDDEN)])
    plan = _plan(POLICY, archive, "zip", {"results/run1.json": HIDDEN}, [])
    assert _entry(plan, _sha(archive)).basis == "container"
    assert _entry(plan, _sha(HIDDEN)).basis == "profile_rule"


def test_an_unscanned_archive_is_withheld_unread_not_refused():
    """D-454: an archive the decoded scan cannot read, and that nothing else withholds, is withheld itself (basis
    ``unscanned``, the policy's reason, object level, ledger 0.3) and the seal report lists its chain and code."""
    archive = fs.zip_bytes([("a.json", CLEAN)])
    deferred = bz2.compress(CLEAN)
    plan = _plan(POLICY, archive, "zip", {"a.json": CLEAN}, [], extra=[(deferred, "bin")])
    entry = _entry(plan, _sha(deferred))
    assert (entry.reason, entry.basis, entry.finding, entry.affected_executions) == ("secret", "unscanned", None, ())
    assert entry.public_note == wh.UNSCANNED_NOTE
    assert plan.objects == {_sha(deferred)} and plan.executions == frozenset()  # the good archive stays released
    assert plan.document is not None and plan.document.format == "agentprov-withheld/0.3"
    assert len(plan.unscanned) == 1 and plan.unscanned[0].endswith("(ingest.stream.codec)")
    flagged = b"BZh" + HIDDEN  # sniffed as bz2 (unscanned) but its stored bytes hold the canary: the rule's basis wins
    plan = _plan(POLICY, archive, "zip", {"a.json": CLEAN}, [], extra=[(flagged, "bin")])
    assert plan.objects == {_sha(flagged)} and _entry(plan, _sha(flagged)).basis == "profile_rule"
    assert plan.unscanned == () and plan.document is not None and plan.document.format == "agentprov-withheld/0.1"


def test_an_unscanned_member_withholds_its_archive_as_a_container():
    """D-454 spread (AD-12): an unreadable member stored as its own object is withheld unread, and the archive holding
    its bytes is closed as a container; the good member next to it stays released. The chain names both labels."""
    inner = bz2.compress(CLEAN)
    archive = fs.zip_bytes([("ok/a.json", CLEAN), ("logs/run.bz2", inner)])
    plan = _plan(POLICY, archive, "zip", {"ok/a.json": CLEAN, "logs/run.bz2": inner}, [])
    assert _entry(plan, _sha(inner)).basis == "unscanned" and _entry(plan, _sha(archive)).basis == "container"
    assert plan.objects == {_sha(inner), _sha(archive)}
    (line,) = plan.unscanned
    assert line.endswith("!/logs/run.bz2 (ingest.stream.codec)") and _sha(archive) in line


def test_without_byte_rules_nothing_is_decoded():
    policy = wh.parse_policy(tomllib.loads('''
[withhold]
reason = "secret"
public_note = "issue rule only"
[[withhold.rules]]
id = "flag"
issue = "tst.flagged"
'''), profile_id="tst", profile_version=1, profile_sha256="sha256:" + "0" * 64)
    plan = _plan(policy, bz2.compress(HIDDEN), "bin", {}, [])  # unscanned, but no byte rule asks for a scan
    assert plan.empty


# ------------------------------------------------------------------------------------------------ the backstops
def test_rescan_reports_decoded_hits_and_unscanned_archives():
    archive = fs.zip_bytes([("results/run1.json", CLEAN), ("config/env.json", HIDDEN)])
    deferred = bz2.compress(CLEAN)
    objects, files = _store((archive, "zip"), (deferred, "bin"))
    labels = sorted(files)
    zip_label, bz2_label = objects[_sha(archive)], objects[_sha(deferred)]
    assert wh.rescan(labels, _stream(files), POLICY, decode=False) == []
    assert sorted(wh.rescan(labels, _stream(files), POLICY)) == sorted([(zip_label, "canary"),
                                                                        (bz2_label, wh.UNSCANNED_RULE)])
    unread: list[tuple[str, str]] = []
    assert wh.rescan(labels, _stream(files), POLICY, unscanned=unread) == [(zip_label, "canary")]
    assert unread == [(bz2_label, "ingest.stream.codec")]


def test_the_reserved_rule_id_is_never_a_valid_rule_id():
    with pytest.raises(wh.WithholdError):
        wh.parse_policy(tomllib.loads(f'''
[withhold]
reason = "secret"
public_note = "n"
[[withhold.rules]]
id = "{wh.UNSCANNED_RULE}"
marker = "abcd"
'''), profile_id="tst", profile_version=1, profile_sha256="sha256:" + "0" * 64)



# ------------------------------------------------------------------------------------------------ D-453: local headers
def _cut(archive: bytes) -> bytes:
    """The archive without its central directory and end record (an ``.eval`` cut at a size cap)."""
    return archive[: archive.index(b"PK\x01\x02")]


def test_a_zip_cut_before_its_central_directory_is_read_by_its_local_headers():
    archive = _cut(fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)]))
    assert SECRET.encode() not in archive
    _objects, scan = _scan((archive, "zip"))
    assert scan.hits == {_sha(archive): frozenset({"canary"})} and scan.unscanned == {}
    assert scan.partial == frozenset({_sha(archive)})


def test_a_cut_inside_a_deflate_stream_reads_what_exists():
    whole = _cut(fs.zip_bytes([("config/env.json", HIDDEN), ("tail.json", b'{"t": "' + b"w" * 5000 + b'"}')]))
    cut = whole[: len(whole) - 200]  # inside the second entry's stream
    _objects, scan = _scan((cut, "zip"))
    assert scan.hits == {_sha(cut): frozenset({"canary"})} and scan.unscanned == {}
    _objects, clean = _scan((_cut(fs.zip_bytes([("a.json", CLEAN), ("b.json", CLEAN * 20)]))[:-100], "zip"))
    assert clean.hits == {} and clean.unscanned == {} and len(clean.partial) == 1


def test_a_stored_entry_is_read_by_size_and_junk_between_headers_is_skipped():
    plain = fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)], method=0)
    cut = _cut(plain)
    second = cut.index(b"PK\x03\x04", 1)
    spliced = cut[:second] + b"\x00junk-between-headers\x00" + cut[second:]
    _objects, scan = _scan((spliced, "zip"))
    assert scan.hits == {_sha(spliced): frozenset({"canary"})} and scan.unscanned == {}


def test_a_nested_zip_inside_a_cut_zip_is_read_in_turn():
    inner = fs.zip_bytes([("deep/env.json", HIDDEN)])
    archive = _cut(fs.zip_bytes([("a.json", CLEAN), ("inner.zip", inner)]))
    _objects, scan = _scan((archive, "zip"))
    assert scan.hits == {_sha(archive): frozenset({"canary"})} and scan.unscanned == {}


def _patch_flags(archive: bytes, flags: int, *, zero_sizes: bool = False) -> bytes:
    """Set the general-purpose flags of the first local header (and zero its sizes for a bit-3 entry)."""
    data = bytearray(archive)
    data[6:8] = flags.to_bytes(2, "little")
    if zero_sizes:
        data[18:26] = bytes(8)
    return bytes(data)


@pytest.mark.parametrize(("flags", "method", "zero", "code"), [
    (0x01, 8, False, "ingest.archive.encrypted"),
    (0x08, 0, True, "ingest.archive.format"),
])  # fmt: skip
def test_an_entry_the_local_read_cannot_decode_keeps_the_archive_unscanned(flags, method, zero, code):
    archive = _patch_flags(_cut(fs.zip_bytes([("a.json", CLEAN), ("b.json", CLEAN)], method=method)), flags,
                           zero_sizes=zero)  # fmt: skip
    _objects, scan = _scan((archive, "zip"))
    assert scan.unscanned == {_sha(archive): code}
    plan = _plan(POLICY, archive, "zip", {}, [])
    assert _entry(plan, _sha(archive)).basis == "unscanned"  # D-454: withheld unread, never released


def test_another_method_keeps_the_archive_unscanned():
    data = bytearray(_cut(fs.zip_bytes([("a.json", CLEAN)])))
    data[8:10] = (12).to_bytes(2, "little")  # bzip2 method
    _objects, scan = _scan((bytes(data), "zip"))
    assert scan.unscanned == {_sha(bytes(data)): "ingest.archive.method"}


def test_a_deflate_bomb_in_a_cut_zip_stops_at_the_ratio_limit():
    bomb = _cut(fs.zip_bytes([("big.bin", b"\x00" * (8 << 20))]))
    _objects, scan = _scan((bomb, "zip"))
    assert scan.unscanned == {_sha(bomb): "ingest.archive.ratio"} and scan.hits == {}


def test_a_complete_zip_is_never_read_by_its_local_headers():
    _objects, scan = _scan((fs.zip_bytes([("config/env.json", HIDDEN)]), "zip"))
    assert scan.partial == frozenset() and len(scan.hits) == 1


def test_the_seal_plan_counts_partial_reads_and_releases_a_clean_cut_zip():
    archive = _cut(fs.zip_bytes([("a.json", CLEAN), ("b.json", CLEAN)]))
    plan = _plan(POLICY, archive, "zip", {}, [])
    assert plan.empty and plan.partial == 1
    secret = _cut(fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)]))
    plan = _plan(POLICY, secret, "zip", {}, [])
    entry = _entry(plan, _sha(secret))
    assert entry.basis == "profile_rule" and entry.finding is not None and entry.finding.detector == DECODED_DETECTOR


def test_the_local_header_read_runs_in_t1_workers():
    archive = _cut(fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)]))
    _objects, scan = _scan((archive, "zip"), in_process=False)
    assert scan.hits == {_sha(archive): frozenset({"canary"})} and scan.partial == frozenset({_sha(archive)})


def test_a_zip_signature_without_an_entry_stays_unscanned():
    junk = b"PK\x03\x04" + b"\x00" * 200  # a header of zeros: no name, so not an entry
    _objects, scan = _scan((junk, "zip"))
    assert scan.unscanned == {_sha(junk): "ingest.archive.format"} and scan.hits == {}


# ------------------------------------------------------------------------------------------------ container reason order
TWO_REASONS = wh.parse_policy(tomllib.loads('''
[withhold]
reason = "secret"
public_note = "a planted test canary"
[[withhold.rules]]
id = "canary"
pattern = "CANARY-[A-Z]{8}"
scope = "object"
[[withhold.rules]]
id = "account"
pattern = "/Us' + 'ers/[a-z]{3,8}/"
scope = "object"
reason = "personal_data"
public_note = "a test account path"
'''.replace("' + '", "")), profile_id="tst", profile_version=1, profile_sha256="sha256:" + "0" * 64)


@pytest.mark.parametrize("pad", range(6))
def test_a_container_takes_the_first_reason_of_its_members_whatever_their_order(pad):
    """A container of a secret member and a personal_data member is withheld for ``secret`` (REASONS order), not for the
    reason of whichever member the closure reaches first (digest order; found by the D-609 build)."""
    secret = HIDDEN + b" " * pad
    personal = b'{"cwd": "/Us' + b'ers/tstabc/work", "pad": "' + b"z" * (300 + pad) + b'"}'
    archive = fs.zip_bytes([("a/secret.json", secret), ("b/cwd.json", personal)])
    plan = _plan(TWO_REASONS, archive, "zip", {"a/secret.json": secret, "b/cwd.json": personal}, [])
    assert _entry(plan, _sha(secret)).reason == "secret" and _entry(plan, _sha(personal)).reason == "personal_data"
    container = _entry(plan, _sha(archive))
    assert (container.basis, container.reason) == ("container", "secret")


def test_the_default_worker_count_is_the_host_default(monkeypatch):
    """Mac Studio tuning A2: ``workers=None`` takes :func:`resolve_worker_count` (0), no longer ``min(4, CPUs)``. Perf
    round 2: that many roots are read at once, each by a one-worker pool of its own; in process, one."""
    import agentprov.corpus.withhold_scan as ws

    seen: list[int] = []
    real = ws.WorkerPool

    def pool(**kw):
        seen.append(kw["workers"])
        return real(**kw)

    monkeypatch.setattr(ws, "resolve_worker_count", lambda requested: 13 if requested == 0 else requested)
    monkeypatch.setattr(ws, "WorkerPool", pool)
    assert [ws.root_readers(w, in_process=False) for w in (None, 2)] == [13, 2]
    assert ws.root_readers(None, in_process=True) == 1
    objects, files = _store((fs.zip_bytes([("a.json", CLEAN)]), "zip"))
    for workers in (None, 2):
        scan_archives(objects, _stream(files), POLICY.byte_rules, in_process=False, release=False, workers=workers)
    assert seen == [1] * 15  # 13 readers, then 2; every pool has one worker


# ------------------------------------------------------------------------------------------------ perf round 2: roots in parallel
def _mixed() -> list[tuple[bytes, str]]:
    """Every outcome at once: hits, nested hits, a clean zip, a split archive read through its parts, a split archive with
    a missing part, a cut zip read by its local headers, an unreadable codec, trailing bytes and a plain document."""
    split_whole = fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)])
    parts = fs.split(split_whole, 100)
    lonely = _hidden_zip()
    blobs = [(fs.zip_bytes([(f"r{i}/a.json", CLEAN), (f"r{i}/env.json", HIDDEN)]), "zip") for i in range(5)]
    blobs += [(fs.zip_bytes([(f"c{i}.json", CLEAN)]), "zip") for i in range(5)]
    blobs += [(fs.zip_bytes([("a.json", CLEAN), ("inner.zip", fs.zip_bytes([("deep/env.json", HIDDEN)]))]), "zip")]
    blobs += [(split_descriptor([(_sha(p), len(p)) for p in parts]), "json"), *((p, "bin") for p in parts)]
    blobs += [(split_descriptor([(_sha(lonely), len(lonely)), ("e" * 64, 10)]), "json"), (lonely, "zip")]
    blobs += [(_cut(fs.zip_bytes([("a.json", CLEAN), ("config/env.json", HIDDEN)])), "zip")]
    blobs += [(bz2.compress(HIDDEN), "bin"), (fs.zip_bytes([("a.json", CLEAN)]) + gzip.compress(HIDDEN), "zip")]
    return blobs + [(CLEAN, "json")]


def test_the_scan_is_the_same_at_any_worker_count_iteration_order_included():
    objects, files = _store(*_mixed())
    scans = [scan_archives(objects, _stream(files), POLICY.byte_rules, release=False, workers=w) for w in (1, 4, 16)]
    first = scans[0]
    assert len(first.hits) == 9 and len(first.unscanned) == 3 and len(first.partial) == 1  # the fixture covers them all
    for scan in scans[1:]:
        assert scan == first
        assert list(scan.hits) == list(first.hits) and list(scan.unscanned) == list(first.unscanned)


def test_member_scan_is_never_entered_twice_at_once():
    import threading
    import time

    objects, files = _store(*_mixed())
    inside, most, lock = [0], [0], threading.Lock()
    calls: list[tuple[str, str, str]] = []

    def member_scan(root: str, locator: str, part: str, chunks: Iterable[bytes]) -> frozenset[str]:
        with lock:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.002)  # widen the window two calls would have to overlap in
        found = wh.scan_chunks(chunks, POLICY.byte_rules)
        calls.append((root, locator, part))
        with lock:
            inside[0] -= 1
        return found

    serial = scan_archives(objects, _stream(files), POLICY.byte_rules, release=False, workers=1, member_scan=member_scan)
    serial_calls = sorted(calls)
    calls.clear()
    parallel = scan_archives(objects, _stream(files), POLICY.byte_rules, release=False, workers=8, member_scan=member_scan)
    assert most[0] == 1 and parallel == serial and sorted(calls) == serial_calls


def test_an_error_in_one_root_is_raised_and_the_scratch_store_is_removed(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    objects, files = _store(*((fs.zip_bytes([(f"m{i}.json", CLEAN)]), "zip") for i in range(6)))
    poisoned = sorted(objects)[3]

    def member_scan(root: str, locator: str, part: str, chunks: Iterable[bytes]) -> frozenset[str]:
        if root == poisoned:
            raise RuntimeError("member scan failed")
        return wh.scan_chunks(chunks, POLICY.byte_rules)

    with pytest.raises(RuntimeError, match="member scan failed"):
        scan_archives(objects, _stream(files), POLICY.byte_rules, release=False, workers=4, member_scan=member_scan)
    assert list((tmp_path / "home" / "tmp").iterdir()) == []
