"""Deferrals part A: the import refusals lifted (D-200..D-203; MN N.2.2; HL H.7.2; D.2.9).

* **Archive inputs** (D-200): a download pin's file is stored with the pin's origin, expanded in place by the ``expand``
  stage and its selected members are mapped whole with ``member`` origins; ``recompute`` re-expands it byte for byte.
* **The Zenodo pin record** (D-201): record id and version label, and the offline ``--verify-against-pin`` check.
* **Several snapshots per corpus** (D-202): H.7.2's collapse, the replayed re-map and the sealed manifest's checks.
* **Import-side blobs** (D-203): ``[import] blobs`` files are stored first and referenced by digest.

Inputs are the committed, licence-cleared FooBench and golden AgentDojo fixtures, loaded programmatically and never
printed. No network.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov.adapters.runner.importer import ArchiveTree, IdentityRefusedError, LocalTree, import_source
from agentprov.corpus.manifest import origin_matches_pin
from agentprov.corpus.writer import CorpusWriter
from agentprov.errors import AgentProvError
from agentprov.raw.fetch import DigestMismatchError, FetchError, Recipe, verify_download

REPO = Path(__file__).resolve().parents[3]
FOO = REPO / "tests" / "fixtures" / "foobench"
FOO_FILES = ("trace-001.jsonl", "sub-trace-001.jsonl", "screenshot-0.png")
HEAD = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
COMMITS = {"2024-06": support.C274885, "head": HEAD}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _zip(path: Path, members: dict[str, bytes]) -> tuple[str, int]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    path.write_bytes(buf.getvalue())
    return hashlib.sha256(buf.getvalue()).hexdigest(), len(buf.getvalue())


def _foo_zip(path: Path, *, extra: dict[str, bytes] | None = None) -> dict[str, Any]:
    members = {f"deposit/traces/{name}": (FOO / name).read_bytes() for name in FOO_FILES}
    members["deposit/README.txt"] = b"not selected\n"
    members.update(extra or {})
    sha, size = _zip(path, members)
    return {"role": "fixture", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
            "file": path.name, "sha256": sha, "bytes": size}


def _import_archive(tmp: Path, out: str = "c", **kwargs: Any) -> tuple[Any, Path, dict[str, Any]]:
    pin = kwargs.pop("pin", None) or _foo_zip(tmp / "deposit.zip")
    tree = ArchiveTree(tmp / pin["file"], pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    kwargs.setdefault("in_process", True)
    with CorpusWriter(tmp / out) as writer:
        report = import_source("foobench", tree, corpus=writer, profile_id="foobench", part="fixture", pin=pin, **kwargs)
    return report, tmp / f"{out}.partial", pin


# ------------------------------------------------------------------------------------------------ archive inputs (D-200)
def test_an_archive_input_is_stored_with_its_pin_origin_and_its_members_are_mapped_whole(tmp_path):
    report, partial, pin = _import_archive(tmp_path)
    assert report.counters["seen"] == 1 and report.counters["mapped"] == 1 and report.counters["degenerate"] == 0
    origins = _jsonl(partial / "raw" / "origins.jsonl")
    containers = [o for o in origins if o["origin"]["kind"] == "zenodo"]
    assert containers == [{"origin": {"doi": "10.5281/zenodo.1", "file": "deposit.zip", "kind": "zenodo"},
                           "sha256": "sha256:" + pin["sha256"]}]
    members = _jsonl(partial / "raw" / "members.jsonl")
    by_label = {m["label"]: m["disposition"] for m in members}
    assert by_label["deposit/README.txt"] == "not_selected"  # outside the selection: never decompressed (R-40)
    assert by_label["deposit/traces/trace-001.jsonl"] == by_label["deposit/traces/screenshot-0.png"] == "selected"
    (row,) = _jsonl(partial / "executions.jsonl")
    header = json.loads((partial / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
    origin = header["artifacts"][0]["origin"]
    assert origin["kind"] == "member" and origin["container"] == pin["sha256"]
    assert origin["label"] == "deposit/traces/trace-001.jsonl"
    snapshot = json.loads((partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert snapshot["input"] == {"bytes": pin["bytes"], "kind": "archive", "label": "deposit.zip",
                                 "sha256": "sha256:" + pin["sha256"]}
    assert snapshot["pin"] == {"bytes": pin["bytes"], "doi": "10.5281/zenodo.1", "file": "deposit.zip", "kind": "zenodo",
                               "record": 1, "role": "fixture", "sha256": pin["sha256"], "version": "v1"}
    stages = {s["stage"] for s in json.loads((partial / "derivation.json").read_text("utf-8"))["stages"]}
    assert "expand" in stages


def test_register_subjects_of_archive_members_name_the_container(tmp_path):
    pin = _foo_zip(tmp_path / "deposit.zip", extra={"deposit/traces/.DS_Store": b"x", "deposit/x/other.jsonl": b'{"a": 1}\n'})
    report, partial, _ = _import_archive(tmp_path, pin=pin)
    assert report.counters["seen"] == 2 and report.counters["registered"] == 1
    entries = [e for e in _jsonl(partial / "register.jsonl") if e["code"] == "select.not_execution_artefact"]
    assert [e["subject"] for e in entries] == [{"path": "deposit.zip!/deposit/x/other.jsonl", "snapshot_id": "fixture"}]


def test_an_archive_input_that_is_not_an_archive_fails_and_maps_nothing(tmp_path):
    bad = tmp_path / "deposit.zip"
    bad.write_bytes(b"not a zip at all")
    pin = {"role": "fixture", "kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "deposit.zip",
           "sha256": hashlib.sha256(bad.read_bytes()).hexdigest(), "bytes": bad.stat().st_size}
    report, partial, _ = _import_archive(tmp_path, pin=pin)
    assert report.exit_code == 1 and report.counters["mapped"] == 0
    assert report.failures and report.failures[0]["stage"] == "expand"
    assert any(e["code"].startswith("ingest.") for e in _jsonl(partial / "register.jsonl"))


def test_an_archive_of_a_container_dialect_is_no_longer_refused(tmp_path):
    # D-380 lifted D-200's exit-5 refusal: the container members of an archive input are expanded at level 2 and mapped
    # (tests/adapters/runner/test_nested_archives.py). This deposit holds no member the profile's include names.
    pin = _foo_zip(tmp_path / "deposit.zip")
    tree = ArchiveTree(tmp_path / "deposit.zip", pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("agent-security-tools-survey", tree, corpus=writer, part="agentharm", in_process=True,
                               pin=pin)
    assert report.counters["seen"] == 0 and not report.failures


def test_the_same_archive_imports_byte_identically_and_recompute_re_expands_it(tmp_path, monkeypatch, capsys):
    _report, first, pin = _import_archive(tmp_path, "a")
    _import_archive(tmp_path, "b", pin=pin)
    assert support.tree_bytes(first, skip=("corpus.json",)) == support.tree_bytes(tmp_path / "b.partial", skip=("corpus.json",))
    code, summary = _recompute(first, tmp_path, monkeypatch, capsys)
    assert code == 0, summary
    assert summary["counters"]["identical"] == summary["counters"]["selected"] == 1


def _recompute(src: Path, tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[int, Any]:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(src), "--dry-run", "--no-reuse", "--in-process", "--json", "--progress", "off"])
    out = capsys.readouterr().out
    return code, json.loads(out)


# ------------------------------------------------------------------------------------------------ blobs (D-203)
def test_blob_files_are_stored_first_and_the_aer_references_them_by_digest(tmp_path):
    report, partial, _ = _import_archive(tmp_path)
    png = hashlib.sha256((FOO / "screenshot-0.png").read_bytes()).hexdigest()
    assert any(o["sha256"] == "sha256:" + png for o in _jsonl(partial / "raw" / "origins.jsonl"))
    (row,) = _jsonl(partial / "executions.jsonl")
    seal = json.loads((partial / row["paths"]["aer"]).read_bytes().splitlines()[-1])
    assert seal["blobs"] == ["sha256:" + png]
    assert not [f for f in report.failures if f["code"] == "validate.failed"]  # AER-V21 finds the blob in the store
    assert not any(e["subject"].get("path", "").endswith("screenshot-0.png") for e in _jsonl(partial / "register.jsonl"))


def test_a_blob_file_in_a_tree_is_stored_with_its_pinned_origin(tmp_path):
    root = tmp_path / "in"
    root.mkdir()
    for name in FOO_FILES:
        (root / name).write_bytes((FOO / name).read_bytes())
    check = support.vouch(root, repo="https://github.com/nickjones39/AgentPROV", commit="a" * 40)
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("foobench", LocalTree(root), corpus=writer, profile_id="foobench", part="fixture",
                               in_process=True, pin_check=check)
    assert report.counters["mapped"] == 1
    png = hashlib.sha256((FOO / "screenshot-0.png").read_bytes()).hexdigest()
    blob_origins = [o["origin"] for o in _jsonl(tmp_path / "c.partial" / "raw" / "origins.jsonl") if o["sha256"].endswith(png)]
    assert blob_origins == [{"blob_sha1": support.golden.git_blob_sha1((FOO / "screenshot-0.png").read_bytes()),
                             "commit": "a" * 40, "kind": "git", "path": "screenshot-0.png",
                             "repo": "https://github.com/nickjones39/AgentPROV"}]
    assert not [f for f in report.failures if f["code"] == "validate.failed"]


# ------------------------------------------------------------------------------------------------ Zenodo pins (D-201)
def _recipe(**overrides: Any) -> Recipe:
    pin = {"kind": "zenodo", "role": "r", "doi": "10.5281/zenodo.23218779", "file": "a.zip", "sha256": "0" * 64, "size": 3}
    pin.update(overrides)
    return Recipe.from_pin(pin)


def test_a_zenodo_pin_record_names_record_version_file_size_and_digests():
    recipe = _recipe(record=23218779, version="v2", md5="1" * 32)
    assert recipe.pin_record() == {"bytes": 3, "doi": "10.5281/zenodo.23218779", "file": "a.zip", "kind": "zenodo",
                                   "md5": "1" * 32, "record": 23218779, "role": "r", "sha256": "0" * 64, "version": "v2"}
    assert _recipe().pin_record()["record"] == 23218779  # derived from the version DOI when not pinned
    with pytest.raises(FetchError, match="record"):
        _recipe(record=1)
    with pytest.raises(FetchError, match="version"):
        _recipe(version="v2\n")


def test_verify_download_checks_name_size_md5_and_sha256_offline():
    data = b"abc"
    good = Recipe.from_pin({"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "a.zip", "size": 3,
                            "sha256": hashlib.sha256(data).hexdigest(), "md5": hashlib.md5(data).hexdigest()})
    assert verify_download(io.BytesIO(data), "a.zip", good) == (hashlib.sha256(data).hexdigest(),
                                                                 hashlib.md5(data).hexdigest(), 3)
    with pytest.raises(DigestMismatchError):
        verify_download(io.BytesIO(data), "b.zip", good)
    with pytest.raises(DigestMismatchError):
        verify_download(io.BytesIO(b"abd"), "a.zip", good)
    with pytest.raises(DigestMismatchError):
        verify_download(io.BytesIO(b"abcd"), "a.zip", good)
    md5_only = Recipe.from_pin({"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "a.zip", "md5": "0" * 32})
    with pytest.raises(FetchError) as unverifiable:
        verify_download(io.BytesIO(data), "a.zip", md5_only)
    assert unverifiable.value.code == "raw.fetch.unverifiable"


def test_the_import_cli_checks_an_archive_input_against_a_download_pin(tmp_path):
    from agentprov.adapters.profiles import load_profile
    from agentprov.cli.common import Context, UnsupportedCapability
    from agentprov.cli.import_ import _tree
    from agentprov.ingest.limits import IngestLimits

    pin = _foo_zip(tmp_path / "deposit.zip")
    args = argparse.Namespace(fetch=False, input=str(tmp_path / "deposit.zip"), verify_against_pin=True,
                              allow_hardlinks=False, allow_network=False, dry_run=False, cache_dir=None)
    ctx = Context(args=args, env={})
    tree, check = _tree(args, ctx, load_profile("foobench"), pin, IngestLimits(), None)
    assert isinstance(tree, ArchiveTree) and check is None and tree.sha256 == pin["sha256"]
    with pytest.raises(DigestMismatchError):
        _tree(args, ctx, load_profile("foobench"), {**pin, "sha256": "0" * 64}, IngestLimits(), None)
    args.verify_against_pin = False
    with pytest.raises(AgentProvError) as unpinned:
        _tree(args, ctx, load_profile("foobench"), pin, IngestLimits(), None)
    assert unpinned.value.code == "raw.origin.local"
    with pytest.raises(UnsupportedCapability):  # a .zip under a git pin stays refused (exit 5)
        _tree(args, ctx, load_profile("foobench"), {"kind": "git", "commit": "a" * 40, "role": "x"}, IngestLimits(), None)


# ------------------------------------------------------------------------------------------------ snapshots (D-202)
def _tree(root: Path, source: Path, labels: list[str]) -> Path:
    for label in labels:
        target = root / label
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / label).read_bytes())
    return root


def _snapshot(tree: Path, corpus: Path, part: str, **kwargs: Any) -> Any:
    commit = COMMITS[part]
    kwargs.setdefault("in_process", True)
    with CorpusWriter(corpus) as writer:
        return import_source("agentdojo", LocalTree(tree), corpus=writer, part=part, corpus_id="agentdojo-upstream",
                             pin_check=support.vouch(tree, commit=commit),
                             pin={"commit": commit, "kind": "git", "role": part}, **kwargs)


@pytest.fixture
def two_snapshots(tmp_path: Path) -> tuple[Path, list[str]]:
    """Three golden native AgentDojo logs (never printed): logs 0-1 in the June-2024 snapshot, 1-2 in head."""
    source = tmp_path / "all"
    labels = sorted(support.agentdojo_tree(source, count=3))
    corpus = tmp_path / "c"
    assert _snapshot(_tree(tmp_path / "in-june", source, labels[:2]), corpus, "2024-06").exit_code == 0
    assert _snapshot(_tree(tmp_path / "in-head", source, labels[1:]), corpus, "head").exit_code == 0
    return corpus.with_name("c.partial"), labels


def test_a_second_snapshot_collapses_shared_bytes_into_one_execution_listing_both(two_snapshots):
    partial, labels = two_snapshots
    rows = _jsonl(partial / "executions.jsonl")
    assert sorted(tuple(r["snapshot_ids"]) for r in rows) == [("2024-06",), ("2024-06", "head"), ("head",)]
    shared = next(r for r in rows if len(r["snapshot_ids"]) == 2)
    assert shared["n_origins"] == 2
    header = json.loads((partial / shared["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
    assert header["artifacts"][0]["origin"]["commit"] == support.C274885  # the snapshot that imported it first
    collapsed = [e for e in _jsonl(partial / "register.jsonl") if e["code"] == "dedup.collapsed"]
    assert [(e["subject"]["snapshot_id"], e["subject"]["path"]) for e in collapsed] == [("head", labels[1])]
    source = json.loads((partial / "corpus.json").read_text("utf-8"))["sources"][0]
    assert source["parts"] == ["2024-06", "head"]
    assert [(s["snapshot_id"], s["part"], s["counts"]["executions"]) for s in source["snapshots"]] == [
        ("2024-06", "2024-06", 2), ("head", "head", 2)]
    assert [s["pin"]["commit"] for s in source["snapshots"]] == [support.C274885, HEAD]


def test_a_resumed_snapshot_is_skipped_not_collapsed_again(two_snapshots, tmp_path):
    partial, labels = two_snapshots
    before = support.tree_bytes(partial)
    report = _snapshot(tmp_path / "in-head", tmp_path / "c", "head")
    assert report.counters["skipped_resume"] == 2 and report.counters["duplicates"] == 0
    assert support.tree_bytes(partial) == before


def test_another_profile_or_corpus_id_is_still_refused(two_snapshots, tmp_path):
    with CorpusWriter(tmp_path / "c") as writer, pytest.raises(IdentityRefusedError):
        import_source("agentdojo", LocalTree(tmp_path / "in-head"), corpus=writer, part="head", corpus_id="other",
                      pin_check=support.vouch(tmp_path / "in-head", commit=HEAD), in_process=True)


def test_recompute_replays_the_snapshots_in_import_order_byte_identically(two_snapshots, tmp_path, monkeypatch, capsys):
    partial, _labels = two_snapshots
    code, summary = _recompute(partial, tmp_path, monkeypatch, capsys)
    assert code == 0, summary
    assert summary["counters"]["identical"] == summary["counters"]["selected"] == 3
    assert not summary.get("corpus_changes")


def test_origin_matches_pin_tells_each_snapshot_its_own_origins():
    git = {"kind": "git", "repo": "https://x", "commit": HEAD, "path": "p", "blob_sha1": "b" * 40}
    assert origin_matches_pin(git, {"kind": "git", "commit": HEAD})
    assert not origin_matches_pin(git, {"kind": "git", "commit": support.C274885})
    zen = {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "a.zip"}
    assert origin_matches_pin(zen, {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "a.zip"})
    assert not origin_matches_pin(zen, {"kind": "zenodo", "doi": "10.5281/zenodo.2", "file": "a.zip"})
    assert not origin_matches_pin({"kind": "member"}, {"kind": "zenodo"}) and not origin_matches_pin(git, None)


def test_a_re_map_after_a_profile_change_is_not_refused(two_snapshots, tmp_path, monkeypatch, capsys):
    """The regeneration round's case: a corpus imported under an earlier source-profile digest is re-mapped with the
    shipped profile. The new tree starts from the source's manifest, which names the old digest; G4's profile check
    guards a snapshot added to a corpus, never a re-map of the snapshots it already lists."""
    from agentprov.cli.main import main

    partial, _labels = two_snapshots
    old = "sha256:" + "0" * 64
    manifest = json.loads((partial / "corpus.json").read_text("utf-8"))
    manifest["sources"][0]["profile"]["sha256"] = old
    (partial / "corpus.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(partial), "--stages", "aer,sem,prov,validation", "--dry-run", "--no-reuse",
                 "--in-process", "--json", "--progress", "off"])
    summary = json.loads(capsys.readouterr().out)
    assert code != 4 and "identity" not in json.dumps(summary.get("error") or {}), summary
    assert summary["counters"]["selected"] == 3


def test_the_re_mapped_manifest_names_the_shipped_profile(two_snapshots, tmp_path, monkeypatch, capsys):
    from agentprov.adapters.profiles import load_profile
    from agentprov.cli.main import main

    partial, _labels = two_snapshots
    manifest = json.loads((partial / "corpus.json").read_text("utf-8"))
    manifest["sources"][0]["profile"]["sha256"] = "sha256:" + "0" * 64
    (partial / "corpus.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    main(["recompute", "--corpus", str(partial), "--out", str(tmp_path / "new"), "--stages", "aer,sem,prov,validation",
          "--no-reuse", "--in-process", "--json", "--progress", "off"])
    new = json.loads((tmp_path / "new.partial" / "corpus.json").read_text("utf-8"))["sources"][0]
    assert new["profile"]["sha256"] == "sha256:" + load_profile("agentdojo-upstream").sha256
    assert [s["snapshot_id"] for s in new["snapshots"]] == ["2024-06", "head"]


def test_a_new_snapshot_under_another_profile_digest_is_still_refused(tmp_path):
    source = tmp_path / "all"
    labels = sorted(support.agentdojo_tree(source, count=3))
    corpus = tmp_path / "c"
    assert _snapshot(_tree(tmp_path / "in-june", source, labels[:2]), corpus, "2024-06").exit_code == 0
    partial = corpus.with_name("c.partial")
    manifest = json.loads((partial / "corpus.json").read_text("utf-8"))
    manifest["sources"][0]["profile"]["sha256"] = "sha256:" + "0" * 64
    (partial / "corpus.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(IdentityRefusedError):
        _snapshot(_tree(tmp_path / "in-head", source, labels[1:]), corpus, "head")
