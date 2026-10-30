"""Ingest formats, follow-up (D-247-D-249): archive inputs stored as byte parts, and top-level tar archive inputs.

* **Split archive inputs** (D-249, on the D-200 path): each part is stored with its pinned origin, the split descriptor
  (D-244) with a ``split`` origin, and the members are mapped exactly as for one downloaded zip; ``recompute`` and
  ``verify --level rederive`` replay it byte-identically; a second snapshot collapses on the descriptor, not the parts;
  the CLI checks every part offline and the large-download consent counts the parts' total; sealing records ``parts``.
* **Top-level tar archive inputs** (D-247, D-240): a deposit pin's ``tar.gz`` or ``tar.zst`` goes through the same path,
  gated by the same limits as a zip.

Inputs are the committed, licence-cleared FooBench fixtures, never printed. No network.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov.adapters.runner.importer import ArchiveTree, import_source
from agentprov.corpus.manifest import ManifestError, origin_matches_pin, snapshot_origin_from_pin
from agentprov.corpus.writer import CorpusWriter
from agentprov.errors import AgentProvError
from agentprov.raw.fetch import (
    DigestMismatchError,
    FetchError,
    LargeDownloadRefusedError,
    part_recipes,
    require_split_consent,
    split_pin_record,
    verify_parts,
)
from agentprov.raw.members import split_descriptor
from agentprov.raw.origins import Origin, OriginError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "security"))
from format_support import tar_bytes, zstd_stream  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FOO = REPO / "tests" / "fixtures" / "foobench"
FOO_FILES = ("trace-001.jsonl", "sub-trace-001.jsonl", "screenshot-0.png")
DOI = "10.5281/zenodo.7"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _members() -> dict[str, bytes]:
    out = {f"deposit/traces/{name}": (FOO / name).read_bytes() for name in FOO_FILES}
    out["deposit/README.txt"] = b"not selected\n"
    return out


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:  # stored: members cross the part boundaries
        for name, data in _members().items():
            archive.writestr(name, data)
    return buf.getvalue()


def _split_deposit(root: Path, *, part_size: int = 1500, kind: str = "zenodo") -> tuple[dict[str, Any], list[Path]]:
    """The zip written as ``deposit.zip.part-000k`` files in ``root`` and its split pin."""
    root.mkdir(parents=True, exist_ok=True)
    data = _zip_bytes()
    chunks = [data[i : i + part_size] for i in range(0, len(data), part_size)]
    paths, parts = [], []
    for k, chunk in enumerate(chunks):
        path = root / f"deposit.zip.part-{k:04d}"
        path.write_bytes(chunk)
        paths.append(path)
        parts.append({"file": path.name, "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest(),
                      "md5": hashlib.md5(chunk).hexdigest()})  # fmt: skip
    if kind == "zenodo":
        pin = {"role": "fixture", "kind": "zenodo", "doi": DOI, "record": 7, "file": "deposit.zip",
               "archive": "split-zip", "parts": parts}  # fmt: skip
    else:
        pin = {"role": "fixture", "kind": "hf", "dataset": "owner/name", "revision": "c" * 40, "gated": False,
               "file": "logs/deposit.zip", "archive": "split-zip",
               "parts": [{**p, "file": "logs/" + p["file"]} for p in parts]}  # fmt: skip
    return pin, paths


def _split_tree(pin: dict[str, Any], paths: list[Path]) -> ArchiveTree:
    recipes = part_recipes(pin)
    checked = verify_parts(lambda name: (paths[0].parent / name).open("rb"), recipes)
    return ArchiveTree.split([(p, sha, size) for p, (sha, size) in zip(paths, checked, strict=True)], pin=pin)


def _import(tree: Any, pin: dict[str, Any], corpus: Path, **kwargs: Any) -> Any:
    kwargs.setdefault("in_process", True)
    with CorpusWriter(corpus) as writer:
        return import_source("foobench", tree, corpus=writer, profile_id="foobench", part="fixture", pin=pin, **kwargs)


def _recompute(src: Path, tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[int, Any]:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(src), "--dry-run", "--no-reuse", "--in-process", "--json", "--progress", "off"])
    return code, json.loads(capsys.readouterr().out)


# ------------------------------------------------------------------------------------------------ split pins (raw)
def test_a_split_pin_gives_one_recipe_per_part_in_order_and_its_record(tmp_path):
    pin, _paths = _split_deposit(tmp_path / "in")
    recipes = part_recipes(pin)
    assert [r.file for r in recipes] == [p["file"] for p in pin["parts"]] and all(r.sha256 for r in recipes)
    record = split_pin_record(pin)
    assert record["archive"] == "split-zip" and record["file"] == "deposit.zip" and record["record"] == 7
    assert [p["file"] for p in record["parts"]] == [p["file"] for p in pin["parts"]] and "sha256" not in record
    for bad in ({**pin, "sha256": "0" * 64}, {**pin, "parts": pin["parts"][:1]},
                {**pin, "parts": [pin["parts"][0], pin["parts"][0]]},
                {**pin, "parts": [{k: v for k, v in pin["parts"][0].items() if k != "sha256"}, *pin["parts"][1:]]},
                {**pin, "parts": [{**pin["parts"][0], "url": "https://x"}, *pin["parts"][1:]]}):  # fmt: skip
        with pytest.raises(FetchError):
            part_recipes(bad)


def test_verify_parts_checks_every_part_and_never_trusts_the_order_of_names(tmp_path):
    pin, paths = _split_deposit(tmp_path / "in")
    recipes = part_recipes(pin)
    assert [s for s, _ in verify_parts(lambda n: (tmp_path / "in" / n).open("rb"), recipes)] == [
        p["sha256"] for p in pin["parts"]]
    swapped = paths[1].read_bytes()
    paths[1].write_bytes(paths[2].read_bytes())  # a local copy with the right name but another part's bytes
    paths[2].write_bytes(swapped)
    with pytest.raises(DigestMismatchError):
        verify_parts(lambda n: (tmp_path / "in" / n).open("rb"), recipes)


def test_the_large_download_consent_counts_the_total_of_the_parts():
    parts = [{"file": f"x.zip.{i}", "bytes": 60 << 20, "sha256": f"{i:064x}"} for i in range(2)]
    recipes = part_recipes({"kind": "zenodo", "doi": DOI, "file": "x.zip", "archive": "split-zip", "parts": parts})
    with pytest.raises(LargeDownloadRefusedError):  # 2 x 60 MiB: each part is below 100 MiB, the total is not
        require_split_consent(recipes, False)
    assert require_split_consent(recipes, True) == 120 << 20
    small = part_recipes({"kind": "zenodo", "doi": DOI, "file": "x.zip", "archive": "split-zip",
                          "parts": [{**p, "bytes": 10} for p in parts]})  # fmt: skip
    assert require_split_consent(small, False) == 20


def test_the_split_origin_kind():
    origin = Origin.split("deposit.zip", ["a" * 64, "b" * 64])
    assert origin.to_json() == {"archive": "zip", "kind": "split", "label": "deposit.zip", "parts": ["a" * 64, "b" * 64]}
    for bad in ({"archive": "tar", "label": "x", "parts": ["a" * 64] * 2}, {"archive": "zip", "label": "x", "parts": ["a" * 64]},
                {"archive": "zip", "label": "x", "parts": ["A" * 64, "b" * 64]}, {"archive": "zip", "parts": ["a" * 64] * 2}):
        with pytest.raises(OriginError):
            Origin("split", bad)


# ------------------------------------------------------------------------------------------------ split import (D-249)
@pytest.mark.parametrize("kind", ["zenodo", "hf"])
def test_a_split_archive_input_stores_its_parts_and_descriptor_and_maps_the_members(tmp_path, kind):
    pin, paths = _split_deposit(tmp_path / "in", kind=kind)
    assert len(paths) >= 3
    report = _import(_split_tree(pin, paths), pin, tmp_path / "c")
    assert report.counters["mapped"] == 1 and not report.failures  # FooBench is a toy: its row has mapping issues
    partial = tmp_path / "c.partial"
    origins = _jsonl(partial / "raw" / "origins.jsonl")
    shas = [p["sha256"] for p in pin["parts"]]
    descriptor = hashlib.sha256(split_descriptor([(s, p["bytes"]) for s, p in zip(shas, pin["parts"], strict=True)])).hexdigest()
    by_sha = {o["sha256"].removeprefix("sha256:"): o["origin"] for o in origins}
    assert by_sha[descriptor] == {"archive": "zip", "kind": "split", "label": "deposit.zip", "parts": shas}
    for part in pin["parts"]:
        origin = by_sha[part["sha256"]]
        assert origin == ({"doi": DOI, "file": part["file"], "kind": "zenodo"} if kind == "zenodo"
                          else {"kind": "hf", "path": part["file"], "repo": "owner/name", "revision": "c" * 40})
    members = _jsonl(partial / "raw" / "members.jsonl")
    assert {m["container"] for m in members} == {"sha256:" + descriptor}
    (row,) = _jsonl(partial / "executions.jsonl")
    header = json.loads((partial / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
    assert header["artifacts"][0]["origin"]["container"] == descriptor
    snapshot = json.loads((partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert snapshot["input"]["sha256"] == "sha256:" + descriptor and snapshot["input"]["label"] == "deposit.zip"
    assert [p["sha256"] for p in snapshot["input"]["parts"]] == ["sha256:" + s for s in shas]
    assert snapshot["input"]["bytes"] == sum(p["bytes"] for p in pin["parts"])
    assert snapshot["pin"]["archive"] == "split-zip" and len(snapshot["pin"]["parts"]) == len(paths)
    subjects = {e["subject"]["path"] for e in _jsonl(partial / "register.jsonl") if "path" in e["subject"]}
    assert all(s.startswith("deposit.zip!/") for s in subjects)


def test_a_split_import_is_byte_identical_to_itself_and_recompute_and_rederive_replay_it(tmp_path, monkeypatch, capsys):
    pin, paths = _split_deposit(tmp_path / "in")
    _import(_split_tree(pin, paths), pin, tmp_path / "a")
    _import(_split_tree(pin, paths), pin, tmp_path / "b")
    first = tmp_path / "a.partial"
    assert support.tree_bytes(first, skip=("corpus.json",)) == support.tree_bytes(tmp_path / "b.partial", skip=("corpus.json",))
    code, summary = _recompute(first, tmp_path, monkeypatch, capsys)
    assert code == 0, summary
    assert summary["counters"]["identical"] == summary["counters"]["selected"] == 1
    from agentprov.corpus.verify import verify_corpus
    from agentprov.stats.source import import_hooks

    report = verify_corpus(first, level="rederive", import_hooks=import_hooks())
    assert report.counters.get("rederive_identical") == 1, report.counters


def test_a_second_snapshot_of_the_same_parts_collapses_on_the_descriptor(tmp_path):
    pin, paths = _split_deposit(tmp_path / "in")
    corpus = tmp_path / "c"
    assert _import(_split_tree(pin, paths), pin, corpus, snapshot_id="first").counters["mapped"] == 1
    report = _import(_split_tree(pin, paths), pin, corpus, snapshot_id="second")
    assert not report.failures and report.counters["duplicates"] == 1 and report.counters["mapped"] == 0
    partial = corpus.with_name("c.partial")
    (row,) = _jsonl(partial / "executions.jsonl")
    assert row["snapshot_ids"] == ["first", "second"]
    containers = {m["container"] for m in _jsonl(partial / "raw" / "members.jsonl")}
    assert len(containers) == 1  # one expansion, keyed by the descriptor; the parts are never primaries


def test_a_corrupt_part_order_is_caught_before_anything_is_stored(tmp_path):
    pin, paths = _split_deposit(tmp_path / "in")
    swapped = {**pin, "parts": [pin["parts"][1], pin["parts"][0], *pin["parts"][2:]]}
    tree = _split_tree(swapped, [paths[1], paths[0], *paths[2:]])  # every part matches its own pin, order is wrong
    report = _import(tree, swapped, tmp_path / "c")
    assert report.counters["mapped"] == 0
    assert report.failures and report.failures[0]["stage"] == "expand"


def test_the_import_cli_checks_every_part_of_a_split_pin(tmp_path):
    from agentprov.adapters.profiles import load_profile
    from agentprov.cli.common import Context
    from agentprov.cli.import_ import _tree
    from agentprov.ingest.limits import IngestLimits

    pin, _paths = _split_deposit(tmp_path / "in")
    args = argparse.Namespace(fetch=False, input=str(tmp_path / "in"), verify_against_pin=True, allow_hardlinks=False,
                              allow_network=False, dry_run=False, cache_dir=None)  # fmt: skip
    ctx = Context(args=args, env={})
    tree, check = _tree(args, ctx, load_profile("foobench"), pin, IngestLimits(), None)
    assert isinstance(tree, ArchiveTree) and check is None and tree.archive_parts is not None
    assert [p.sha256 for p in tree.archive_parts] == [p["sha256"] for p in pin["parts"]]
    bad = {**pin, "parts": [{**pin["parts"][0], "sha256": "0" * 64}, *pin["parts"][1:]]}
    with pytest.raises(DigestMismatchError):
        _tree(args, ctx, load_profile("foobench"), bad, IngestLimits(), None)
    args.input = str(tmp_path / "in" / "deposit.zip.part-0000")
    with pytest.raises(AgentProvError):  # a split pin's --input is the directory of its parts
        _tree(args, ctx, load_profile("foobench"), pin, IngestLimits(), None)


# ------------------------------------------------------------------------------------------------ pins and sealing
def test_origin_matches_pin_for_split_descriptors_and_parts(tmp_path):
    pin, _paths = _split_deposit(tmp_path / "in")
    shas = [p["sha256"] for p in pin["parts"]]
    assert origin_matches_pin({"kind": "split", "archive": "zip", "label": "deposit.zip", "parts": shas}, pin)
    assert not origin_matches_pin({"kind": "split", "archive": "zip", "label": "deposit.zip", "parts": shas[::-1]}, pin)
    assert origin_matches_pin({"kind": "zenodo", "doi": DOI, "file": pin["parts"][1]["file"]}, pin)
    assert not origin_matches_pin({"kind": "zenodo", "doi": DOI, "file": "deposit.zip"}, pin)
    assert not origin_matches_pin({"kind": "split", "archive": "zip", "label": "x", "parts": shas},
                                  {"kind": "zenodo", "doi": DOI, "file": "deposit.zip"})


def test_a_split_snapshot_seals_within_the_frozen_corpus_schema(tmp_path):
    """HF: ``hf {dataset, revision, gated, path}`` with ``path`` the parts' directory (the parts are object origins).
    Zenodo: refused, since the sealed origin names one ``file`` and corpus-0.1 has no ``parts`` (D-163). Corpus 0.2 adds
    ``parts`` (D-217; ``tests/unit/corpus/test_split_origin_parts.py``)."""
    v01 = {"corpus_format": "agentprov-corpus/0.1"}
    hf_pin, _ = _split_deposit(tmp_path / "hf", kind="hf")
    hf_record = split_pin_record(hf_pin)
    shas = [p["sha256"] for p in hf_pin["parts"]]
    descriptor = {"kind": "split", "archive": "zip", "label": "deposit.zip", "parts": shas}
    assert snapshot_origin_from_pin(hf_record, [descriptor], **v01) == {
        "dataset": "owner/name", "gated": False, "kind": "hf", "path": "logs", "revision": "c" * 40}
    with pytest.raises(ManifestError):
        snapshot_origin_from_pin(hf_record, [{**descriptor, "parts": shas[::-1]}], **v01)
    with pytest.raises(ManifestError):  # H.2.3 needs the gated flag
        snapshot_origin_from_pin({k: v for k, v in hf_record.items() if k != "gated"}, [descriptor], **v01)
    zen_pin, _ = _split_deposit(tmp_path / "zen")
    zen_desc = {**descriptor, "parts": [p["sha256"] for p in zen_pin["parts"]]}
    with pytest.raises(ManifestError, match="corpus-0.1"):
        snapshot_origin_from_pin(split_pin_record(zen_pin), [zen_desc], **v01)


def test_a_single_hf_archive_input_seals_too():
    record = {"kind": "hf", "repo": "owner/name", "revision": "c" * 40, "gated": True, "file": "batch.tar.zst"}
    origins = [{"kind": "hf", "repo": "owner/name", "revision": "c" * 40, "path": "batch.tar.zst"}]
    assert snapshot_origin_from_pin(record, origins) == {"dataset": "owner/name", "gated": True, "kind": "hf",
                                                         "path": "batch.tar.zst", "revision": "c" * 40}
    with pytest.raises(ManifestError):
        snapshot_origin_from_pin(record, [{**origins[0], "path": "other.zip"}])


# ------------------------------------------------------------------------------------------------ tar inputs (D-247)
def _tar_deposit(root: Path, codec: str, *, directory: bool = True) -> dict[str, Any]:
    entries = [("deposit", None)] if directory else []
    raw = tar_bytes([*entries, *((name, data) for name, data in _members().items())], fmt=tarfile.PAX_FORMAT)
    data = gzip.compress(raw, mtime=0) if codec == "gzip" else zstd_stream(raw)
    name = "deposit.tar.gz" if codec == "gzip" else "deposit.tar.zst"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(data)
    return {"role": "fixture", "kind": "zenodo", "doi": DOI, "file": name, "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


@pytest.mark.parametrize("codec", ["gzip", "zstd"])
def test_a_top_level_tar_archive_input_is_imported_and_replayed(tmp_path, codec, monkeypatch, capsys):
    pin = _tar_deposit(tmp_path / "in", codec)
    tree = ArchiveTree(tmp_path / "in" / pin["file"], pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    report = _import(tree, pin, tmp_path / "c")
    assert report.counters["mapped"] == 1 and not report.failures
    partial = tmp_path / "c.partial"
    members = {m["label"]: (m["disposition"], m["method"]) for m in _jsonl(partial / "raw" / "members.jsonl")}
    assert members["deposit/README.txt"] == ("not_selected", 0)
    assert members["deposit/traces/trace-001.jsonl"] == ("selected", 0)
    code, summary = _recompute(partial, tmp_path, monkeypatch, capsys)
    assert code == 0 and summary["counters"]["identical"] == 1, summary


@pytest.mark.parametrize("codec", ["gzip", "zstd", "zip"])
def test_tar_and_zip_archive_inputs_meet_the_same_limits(tmp_path, codec):
    """Deferrals point 5: max_members, max_member_bytes, max_total_bytes and names gate a tar as they gate a zip."""
    from agentprov.ingest.archives import iter_zip_members, open_archive
    from agentprov.ingest.limits import IngestLimits

    if codec == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in _members().items():
                z.writestr(name, data)
        data = buf.getvalue()
    else:
        # entries count alike in both formats (a directory entry counts too), so the tar has none here, as the zip
        data = (tmp_path / "in" / _tar_deposit(tmp_path / "in", codec, directory=False)["file"]).read_bytes()
    sizes = sorted(len(v) for v in _members().values())

    def outcome(limits: IngestLimits) -> list[tuple[str | None, str, str | None]] | str:
        try:
            archive = open_archive(io.BytesIO(data), limits, release=False, depth=1)
            return [(m.label, m.disposition, m.code) for m in iter_zip_members(archive, None, limits)]
        except AgentProvError as exc:
            return str(exc.code)

    base = IngestLimits()
    assert outcome(base.replace(max_members=3)) == "ingest.archive.members"
    assert all(d == "selected" for _l, d, _c in outcome(base.replace(max_members=4)))  # type: ignore[union-attr]
    capped = outcome(base.replace(max_member_bytes=sizes[-1] - 1))
    assert [c for _l, _d, c in capped if c] == ["ingest.archive.size"]  # type: ignore[union-attr]
    total = outcome(base.replace(max_total_bytes=sum(sizes) - 1))
    assert [c for _l, _d, c in total if c] == ["ingest.archive.size"]  # type: ignore[union-attr]
    assert outcome(base.replace(max_archive_depth=1)) != "ingest.archive.depth"  # level 1 is allowed
    with pytest.raises(AgentProvError) as deep:
        open_archive(io.BytesIO(data), base.replace(max_archive_depth=1), release=False, depth=2)
    assert deep.value.code == "ingest.archive.depth"


def test_an_hf_archive_input_under_a_directory_is_replayed(tmp_path, monkeypatch, capsys):
    """The ``hf`` origin's label is its full path, the recorded input label the base name: the replay finds the archive
    input by its recorded digest (before D-249 it looked the base name up among the full paths and refused)."""
    zen = _tar_deposit(tmp_path / "in", "zstd")
    pin = {"role": "fixture", "kind": "hf", "dataset": "owner/name", "revision": "c" * 40, "gated": False,
           "file": "batches/" + zen["file"], "sha256": zen["sha256"], "bytes": zen["bytes"]}  # fmt: skip
    tree = ArchiveTree(tmp_path / "in" / zen["file"], pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    assert _import(tree, pin, tmp_path / "c").counters["mapped"] == 1
    code, summary = _recompute(tmp_path / "c.partial", tmp_path, monkeypatch, capsys)
    assert code == 0 and summary["counters"]["identical"] == 1, summary
