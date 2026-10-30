"""The deposit builder (``agentprov.release.builder``; HL H.10, HL-T9; DoD Q.20, Q.28; D-42).

Sealed test corpora (``release_support``) are deposited with an injected scanner (no gitleaks). Checked: the deposit
composition and its manifests; the archive format U4's archive-mode ``verify`` reads (prefixed, sorted members, fixed
timestamp, permissions and compression, no extra field, no directory entry, sha256 equal to ``checksums.sha256``, every
file of the tree exactly once); byte-identical builds (Q.20); splitting on shard boundaries; every refusal (unsealed,
scan missing/stale/untriaged/real, advisory, ``test_only``, ``withhold``, dev validation, ``views/``, the interpreter
floor, existing or overlapping output), each writing nothing; a corpus changed after sealing; the claims lint; no
process and no socket during a build; the metadata never invents a DOI.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import socket
import subprocess
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import release_support as rs

from agentprov import envinfo
from agentprov.corpus.integrity import parse_checksums, root_digest
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.release import builder
from agentprov.release.builder import (
    COMPRESS_LEVEL,
    DEPOSIT_MANIFEST,
    DEPOSIT_METADATA,
    EXTERNAL_ATTR,
    DepositError,
    DepositRefusedError,
    archive_date_time,
    members_sha256,
    scan_path_for,
)
from agentprov.release.metadata import ScanRefusedError


@pytest.fixture
def mit(tmp_path_factory, tmp_path) -> Path:
    return rs.sealed(tmp_path_factory, tmp_path / "corpora", "mini-mit")


def _deposit_manifest(out: Path) -> dict:
    return json.loads((out / DEPOSIT_MANIFEST).read_text("utf-8"))


def _assert_nothing_written(out: Path) -> None:
    assert not out.exists() and not out.with_name(out.name + ".partial").exists()


# ------------------------------------------------------------------------------------------------ composition (H.10.3)
def test_deposit_composition_and_manifest(mit, tmp_path):
    out = tmp_path / "deposit"
    report = rs.build([mit], out)
    names = sorted(p.name for p in out.iterdir())
    assert {"README.md", "CHANGELOG.md", "DATASHEET-mini-mit.md", DEPOSIT_MANIFEST, DEPOSIT_METADATA,
            "mini-mit-v0.1.0.meta.zip", "mini-mit-v0.1.0.raw.001.zip", "mini-mit-v0.1.0.aer.001.zip",
            "mini-mit-v0.1.0.sem-agentdojo.suites-2.001.zip", "mini-mit-v0.1.0.prov-agentprov-prov-0.1.001.zip"} == set(names)
    assert (out / "DATASHEET-mini-mit.md").read_bytes() == (mit / "DATASHEET.md").read_bytes()  # a byte copy (REP-3)
    dm = _deposit_manifest(out)
    assert dm["format"] == "agentprov-deposit-manifest/0.1" and dm["status"] == "draft-unpublished"
    assert dm["release_date"] == "2026-10-11" and dm["mixed_licence_classes"] is False
    corpus = dm["corpora"][0]
    assert corpus["root_digest"] == root_digest(mit) and corpus["content_digest"] == rs.manifest(mit)["content_digest"]
    assert corpus["licence_class"] == {"restrictions": [], "spdx": "MIT"}
    assert corpus["coverage"]["archived"] == corpus["coverage"]["files"]
    assert corpus["release_scan"]["tools"][0] == {"name": "agentprov-path-scan", "version": "6"}
    for archive in dm["archives"]:
        data = (out / archive["name"]).read_bytes()
        assert archive["bytes"] == len(data)
        assert archive["sha256"] == "sha256:" + hashlib.sha256(data).hexdigest()
        assert archive["md5"] == hashlib.md5(data, usedforsecurity=False).hexdigest()
    for document in dm["documents"]:
        assert document["sha256"] == "sha256:" + hashlib.sha256((out / document["name"]).read_bytes()).hexdigest()
    assert {d["name"] for d in dm["documents"]} == {"README.md", "CHANGELOG.md", "DATASHEET-mini-mit.md", DEPOSIT_METADATA}
    assert report.counters["archives"] == len(dm["archives"]) == 5
    readme = (out / "README.md").read_text("utf-8")
    assert root_digest(mit) in readme and "Nothing has been uploaded or published." in readme


def test_archives_are_an_image_of_the_sealed_tree_in_the_documented_format(mit, tmp_path):
    out = tmp_path / "deposit"
    rs.build([mit], out)
    dm = _deposit_manifest(out)
    entries, findings = parse_checksums((mit / "checksums.sha256").read_bytes())
    assert not findings
    expected = {e.path: e.sha256 for e in entries}
    expected["checksums.sha256"] = hashlib.sha256((mit / "checksums.sha256").read_bytes()).hexdigest()
    seen: dict[str, str] = {}
    for archive in dm["archives"]:
        with zipfile.ZipFile(out / archive["name"]) as zf:  # read in memory, never extracted
            infos = zf.infolist()
            names = [i.filename for i in infos]
            assert names == sorted(names, key=lambda n: n.encode())
            assert zf.comment == b""
            listing = []
            for info in infos:
                assert info.filename.startswith("mini-mit-v0.1.0/") and not info.is_dir()
                assert info.date_time == (2026, 10, 11, 0, 0, 0)
                assert info.create_system == 3 and info.external_attr == EXTERNAL_ATTR
                assert info.compress_type == zipfile.ZIP_DEFLATED and info.extra == b"" and info.comment == b""
                assert info.flag_bits & 0x08 == 0  # no data descriptor
                label = info.filename.removeprefix("mini-mit-v0.1.0/")
                digest = hashlib.sha256(zf.read(info)).hexdigest()
                assert label not in seen
                seen[label] = digest
                listing.append((digest, info.filename))
            assert archive["n_members"] == len(infos)
            assert archive["members_sha256"] == members_sha256(listing)
            stage = archive["stage"]
            for label in (n.removeprefix("mini-mit-v0.1.0/") for n in names):
                if stage == "meta":
                    assert not label.startswith(("raw/objects/", "aer/", "sem/", "prov/"))
                else:
                    assert label.startswith({"raw": "raw/objects/", "aer": "aer/"}.get(stage, stage.replace("-", "/", 1) + "/"))
    assert seen == expected  # every file of the tree exactly once, byte-equal (closed world)
    assert {"checksums.sha256", "corpus.json", "rules/corpus-spec.toml", "schemas/corpus-0.2.schema.json"} <= {
        n.removeprefix("mini-mit-v0.1.0/") for n in zipfile.ZipFile(out / "mini-mit-v0.1.0.meta.zip").namelist()}
    assert dm["archive_policy"]["compress_level"] == COMPRESS_LEVEL and dm["archive_policy"]["zip64"] is False


def test_two_builds_are_byte_identical_q20(mit, tmp_path_factory, tmp_path):
    rs.build([mit], tmp_path / "a")
    rs.build([mit], tmp_path / "b")
    first = rs.tree_bytes(tmp_path / "a")
    assert first == rs.tree_bytes(tmp_path / "b")
    other = rs.sealed(tmp_path_factory, tmp_path / "other", "mini-mit")  # an independently copied seal
    rs.build([other], tmp_path / "c")
    assert first == rs.tree_bytes(tmp_path / "c")


def test_the_release_date_sets_member_timestamps_clamped_to_1980(mit, tmp_path):
    assert archive_date_time(date(1970, 1, 1)) == (1980, 1, 1, 0, 0, 0)
    assert archive_date_time(date(1980, 1, 1)) == (1980, 1, 1, 0, 0, 0)
    rs.build([mit], tmp_path / "d", release_date=date(1975, 6, 1))
    with zipfile.ZipFile(tmp_path / "d" / "mini-mit-v0.1.0.meta.zip") as zf:
        assert {i.date_time for i in zf.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_dry_run_plans_and_writes_nothing(mit, tmp_path):
    out = tmp_path / "deposit"
    report = rs.build([mit], out, dry_run=True)
    assert report.dry_run and [a["name"] for a in report.archives][0] == "mini-mit-v0.1.0.meta.zip"
    _assert_nothing_written(out)


# ------------------------------------------------------------------------------------------------ splitting (H.10.4)
def _fake_corpus(members):
    return SimpleNamespace(members=members, prefix="c-v0.1.0", corpus_id="c")


def _m(label, size):
    return builder._Member(label, size, "0" * 64)


def test_archives_split_on_shard_boundaries_only():
    members = [_m("corpus.json", 100)]
    for shard in ("00", "01", "02", "03"):
        members += [_m(f"aer/{shard}/ex_{shard}{i}.aer.jsonl", 3000) for i in range(2)]
    one_shard = sum(builder._member_bound(len("c-v0.1.0/") + len(m.label), m.size) for m in members[1:3])
    plan = builder._plan(_fake_corpus(members), one_shard * 2 + 22)
    aer = [a for a in plan if a.stage == "aer"]
    assert [a.name for a in aer] == ["c-v0.1.0.aer.001.zip", "c-v0.1.0.aer.002.zip"]
    assert [a.shards for a in aer] == [["00", "01"], ["02", "03"]]
    assert all(len({m.label.split("/")[1] for m in a.members}) == len(a.shards) for a in aer)
    with pytest.raises(DepositRefusedError) as exc:  # a shard is never split
        builder._plan(_fake_corpus(members), one_shard - 1 + 22)
    assert exc.value.code == "release.refused.shard_too_large" and exc.value.exit_code == 4


def test_the_member_count_limit_splits_too(monkeypatch):
    monkeypatch.setattr(builder, "MAX_MEMBERS", 4)
    members = [_m("corpus.json", 10)] + [_m(f"raw/objects/{h}/{h}{i}.json", 10) for h in ("aa", "bb", "cc") for i in range(2)]
    plan = builder._plan(_fake_corpus(members), 1 << 20)
    assert [a.shards for a in plan if a.stage == "raw"] == [["aa", "bb"], ["cc"]]


def test_real_archives_stay_below_the_limit_and_cover_the_tree(mit, tmp_path):
    full = rs.build([mit], tmp_path / "full", dry_run=True)
    meta = next(a for a in full.archives if a["name"].endswith(".meta.zip"))
    limit = meta["uncompressed_bytes"] * 2 + 65536
    rs.build([mit], tmp_path / "split", max_archive_bytes=limit)
    dm = _deposit_manifest(tmp_path / "split")
    assert all(a["bytes"] <= limit for a in dm["archives"])
    assert dm["corpora"][0]["coverage"]["archived"] == dm["corpora"][0]["coverage"]["files"]


def test_a_too_small_limit_is_refused(mit, tmp_path):
    with pytest.raises(DepositRefusedError) as exc:
        rs.build([mit], tmp_path / "x", max_archive_bytes=4096)
    assert exc.value.code == "release.refused.archive_too_large"
    with pytest.raises(DepositRefusedError) as exc:
        rs.build([mit], tmp_path / "x", max_archive_bytes=1 << 31)  # ZIP64 would be needed
    assert exc.value.exit_code == 2
    _assert_nothing_written(tmp_path / "x")


# ------------------------------------------------------------------------------------------------ refusals (HL-T9)
def test_a_working_corpus_is_refused(tmp_path_factory, tmp_path):
    import seal_support as ss

    working = ss.working_corpus(tmp_path_factory, tmp_path / "w" / "mini")
    with pytest.raises(DepositRefusedError) as exc:
        rs.build([working], tmp_path / "out")
    assert exc.value.code == "release.refused.unsealed" and exc.value.exit_code == 4
    _assert_nothing_written(tmp_path / "out")


def test_no_scan_result_is_refused_not_skipped(mit, tmp_path):
    with pytest.raises(ScanRefusedError) as exc:
        rs.build([mit], tmp_path / "out", scan=lambda root, digest: None)
    assert exc.value.code == "release.refused.scan_missing" and exc.value.exit_code == 4
    with pytest.raises(ScanRefusedError):
        rs.build([mit], tmp_path / "out", scan=None)  # and no <corpus>.release-scan.json beside it
    _assert_nothing_written(tmp_path / "out")


def test_the_scan_beside_the_corpus_is_read(mit, tmp_path):
    scan_path_for(mit).write_text(json.dumps(rs.scan_document(mit, root_digest(mit))), "utf-8")
    rs.build([mit], tmp_path / "out", scan=None)
    assert (tmp_path / "out" / DEPOSIT_MANIFEST).is_file()


def test_a_scan_over_the_raw_input_json_limit_is_read_under_its_own_bounded_limit(mit, tmp_path, monkeypatch):
    """D-990: the scan document is read under ``RELEASE_SCAN_JSON_BYTES`` (1 GiB), not the 64 MiB raw-input limit, and
    stays bounded: a scan over the scan limit is still refused."""
    limits = builder.release_scan_limits()
    assert limits.max_json_bytes == builder.RELEASE_SCAN_JSON_BYTES == 1 << 30
    assert dataclasses.replace(limits, max_json_bytes=IngestLimits().max_json_bytes) == IngestLimits()  # only that limit
    assert builder.release_scan_limits(IngestLimits(max_json_bytes=2 << 30)).max_json_bytes == 2 << 30  # never lowered
    document = rs.scan_document(mit, root_digest(mit))
    data = json.dumps(document).encode("utf-8")
    scan_path_for(mit).write_bytes(data)
    raw = IngestLimits(max_json_bytes=16)  # a raw-input limit far below the scan's size
    assert builder._scan_document(mit, root_digest(mit), None, raw) == document
    monkeypatch.setattr(builder, "RELEASE_SCAN_JSON_BYTES", len(data) - 1)
    with pytest.raises(DepositRefusedError) as exc:
        builder._scan_document(mit, root_digest(mit), None, raw)
    assert exc.value.code == "release.refused.scan" and "larger than the file limit" in str(exc.value)


@pytest.mark.parametrize(("findings", "digest_ok", "code"), [
    ([], False, "release.refused.scan_stale"),
    ([{"fingerprint": "aer/00/x:generic-api-key:3", "triage": None, "reason": None}], True, "release.refused.scan_untriaged"),
    ([{"fingerprint": "aer/00/x:generic-api-key:3", "triage": "real", "reason": "a live key"}], True,
     "release.refused.scan_real"),
    ([{"fingerprint": "aer/00/x:generic-api-key:3", "triage": "synthetic-benchmark", "reason": ""}], True,
     "release.refused.scan_untriaged"),
])  # fmt: skip
def test_scan_results_must_match_and_be_triaged(mit, tmp_path, findings, digest_ok, code):
    def scan(root, digest):
        return rs.scan_document(root, digest if digest_ok else "sha256:" + "0" * 64, findings)

    with pytest.raises(ScanRefusedError) as exc:
        rs.build([mit], tmp_path / "out", scan=scan)
    assert exc.value.code == code and exc.value.exit_code == 4
    _assert_nothing_written(tmp_path / "out")


def test_triaged_findings_are_admitted_and_counted(mit, tmp_path):
    rows = [{"fingerprint": "aer/00/x:generic-api-key:3", "triage": "synthetic-benchmark", "reason": "benchmark fake key"}]
    report = rs.build([mit], tmp_path / "out", scan=lambda root, digest: rs.scan_document(root, digest, rows))
    assert report.corpora[0]["release_scan"]["by_triage"] == {"synthetic-benchmark": 1}


@pytest.mark.parametrize(("change", "code"), [
    (lambda m: m["producer"].__setitem__("interpreter_advisory",
                                         {"floor": "3.14.8", "missing": ["CVE-2026-15310"], "python_version": "3.14.6"}),
     "ingest.interpreter.unpatched"),
    (lambda m: m["validation"].__setitem__("mode", "dev"), "release.refused.dev_validation"),
    (lambda m: m["sources"][0]["snapshots"][0].__setitem__("raw_policy", "withhold"), "release.refused.withhold"),
    (lambda m: (m.__setitem__("mode", "live"), m.__setitem__("live", {"test_only": True})), "release.refused.test_only"),
])  # fmt: skip
def test_policy_refusals_exit_4(mit, tmp_path, change, code):
    rs.restamp(mit, change)
    with pytest.raises(AgentProvError) as exc:
        rs.build([mit], tmp_path / "out")
    assert exc.value.code == code and exc.value.exit_code == 4
    _assert_nothing_written(tmp_path / "out")


def test_a_views_tree_is_unsupported_exit_5(mit, tmp_path):
    aer = next(p for p in (mit / "aer").rglob("*.aer.jsonl"))
    ex = aer.name.removesuffix(".aer.jsonl")
    rs.restamp(mit, add={f"views/transcript-v1/{aer.parent.name}/{ex}.transcript.json": b"{}\n"})
    with pytest.raises(DepositRefusedError) as exc:
        rs.build([mit], tmp_path / "out")
    assert exc.value.code == "release.refused.views" and exc.value.exit_code == 5


def test_release_mode_refuses_below_the_interpreter_floor_exit_3(mit, tmp_path, monkeypatch):
    monkeypatch.setattr(envinfo, "_running_version", lambda: (3, 14, 7))
    with pytest.raises(AgentProvError) as exc:
        rs.build([mit], tmp_path / "out")
    assert exc.value.code == "ingest.interpreter.unpatched" and exc.value.exit_code == 3
    _assert_nothing_written(tmp_path / "out")


def test_existing_or_overlapping_output_is_refused(mit, tmp_path):
    (tmp_path / "out").mkdir()
    with pytest.raises(DepositRefusedError) as exc:
        rs.build([mit], tmp_path / "out")
    assert exc.value.code == "release.refused.exists"
    with pytest.raises(AgentProvError) as exc:
        rs.build([mit], mit / "deposit")
    assert exc.value.exit_code == 4


def test_the_same_corpus_twice_is_a_usage_error(mit, tmp_path_factory, tmp_path):
    other = rs.sealed(tmp_path_factory, tmp_path / "again", "mini-mit")
    with pytest.raises(DepositRefusedError) as exc:
        rs.build([mit, other], tmp_path / "out")
    assert exc.value.exit_code == 2


def test_a_corpus_changed_after_sealing_fails_verification_exit_1(mit, tmp_path):
    aer = next(p for p in (mit / "aer").rglob("*.aer.jsonl"))
    aer.write_bytes(aer.read_bytes() + b" ")
    with pytest.raises(DepositError) as exc:
        rs.build([mit], tmp_path / "out")
    assert exc.value.code == "release.failed.verify" and exc.value.exit_code == 1
    _assert_nothing_written(tmp_path / "out")


def test_an_injected_verifier_records_its_level_and_its_failure_refuses(mit, tmp_path):
    ok = builder.CorpusVerification("chain", True)
    report = rs.build([mit], tmp_path / "a", verify=lambda root: ok)
    assert report.corpora[0]["verification"] == {"level": "chain"}
    with pytest.raises(DepositError):
        rs.build([mit], tmp_path / "b", verify=lambda root: builder.CorpusVerification("chain", False, "seal mismatch"))
    _assert_nothing_written(tmp_path / "b")


def test_generated_text_passes_the_claims_lint_and_a_violation_fails(mit, tmp_path):
    from agentprov.adapters.registry.claims import lint_text

    def lint(location, text):
        return [(v.nc_id, v.location, v.detail) for v in lint_text(location, text)]

    rs.build([mit], tmp_path / "a", lint=lint)
    bad = rs.METADATA.__class__(**{**rs.METADATA.__dict__, "description_preamble": "A lossless record of every run."})
    with pytest.raises(DepositError) as exc:
        rs.build([mit], tmp_path / "b", lint=lint, metadata=bad)
    assert exc.value.code == "release.failed.lint"
    _assert_nothing_written(tmp_path / "b")


def test_a_build_starts_no_process_and_opens_no_socket(mit, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the deposit builder must be offline and start no process (H.10.1, G.9.4)")

    monkeypatch.setattr(subprocess.Popen, "__init__", forbidden)
    monkeypatch.setattr(socket.socket, "__init__", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    rs.build([mit], tmp_path / "out")
    assert (tmp_path / "out" / DEPOSIT_MANIFEST).is_file()


# ------------------------------------------------------------------------------------------------ metadata (H.10.5)
def test_metadata_is_a_draft_and_never_invents_a_doi(mit, tmp_path):
    rs.build([mit], tmp_path / "out")
    meta = json.loads((tmp_path / "out" / DEPOSIT_METADATA).read_text("utf-8"))
    assert meta["format"] == "agentprov-deposit/0.1" and meta["status"] == "draft-unpublished"
    assert meta["version_doi"] is None and meta["concept_doi"] is None  # none in release.toml: none in the draft
    assert meta["resource_type"] == "dataset" and meta["publication_date"] == "2026-10-11" and meta["version"] == "0.1.0"
    assert meta["creators"] == [{"affiliation": None, "name": "Test Creator", "orcid": None}]
    assert meta["licences"] == [{"archives": [a["name"] for a in _deposit_manifest(tmp_path / "out")["archives"]],
                                 "corpora": ["mini-mit"], "documents": ["DATASHEET-mini-mit.md"], "restrictions": [],
                                 "spdx": "MIT"}]
    assert meta["release_scans"][0]["tools"][1] == {"name": "gitleaks", "version": "8.30.1"}
    assert meta["root_digests"] == {"mini-mit": root_digest(mit)}
    m = rs.manifest(mit)
    origin = m["sources"][0]["snapshots"][0]["origin"]
    related = {(r["relation"], r["scheme"], r["identifier"]) for r in meta["related_identifiers"]}
    # every identifier comes from the sealed corpus (profile copy, pinned origin), each with its origin recorded
    assert ("IsDerivedFrom", "URL", f"{origin['repo']}/tree/{origin['commit']}") in related
    assert ("IsDerivedFrom", "DOI", "10.5281/zenodo.12528188") in related  # the AgentDojo profile's concept_doi
    assert ("References", "arXiv", "arXiv:2406.13352") in related
    assert all(r["origin"].startswith("corpus mini-mit") for r in meta["related_identifiers"])
    assert "Nothing has been uploaded or published." in meta["description"]


def test_no_description_paragraph_starts_with_a_list_bullet(mit, tmp_path):
    """The description is sent to Zenodo as HTML paragraphs, where a leading "- " is a literal hyphen (sandbox trial
    2026-10-23, D-800): each corpus is a plain paragraph, in the metadata and nowhere else."""
    rs.build([mit], tmp_path / "out")
    meta = json.loads((tmp_path / "out" / "deposit-metadata.json").read_text("utf-8"))
    paragraphs = [p for p in meta["description"].split("\n\n") if p.strip()]
    assert paragraphs and not [p for p in paragraphs if p.lstrip().startswith(("- ", "* ", "+ "))]
    assert any(p.startswith("Corpus mini-mit 0.1.0: ") and "root digest" in p for p in paragraphs)


def test_metadata_in_memory_is_not_a_zip_member_of_any_archive(mit, tmp_path):
    rs.build([mit], tmp_path / "out")
    for archive in _deposit_manifest(tmp_path / "out")["archives"]:
        with zipfile.ZipFile(io.BytesIO((tmp_path / "out" / archive["name"]).read_bytes())) as zf:
            assert not any(n.endswith((DEPOSIT_MANIFEST, DEPOSIT_METADATA, ".release-scan.json")) for n in zf.namelist())
