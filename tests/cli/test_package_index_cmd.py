"""``agentprov package --index`` (HL H.10.7; D-941 L-5, D-947): the index-only umbrella deposit through the CLI.

Part deposits are built by the real builder from the sealed test corpora; their draft receipts are written here in the
uploader's 0.2 shape (``tests/unit/release/test_index.py`` makes them with the uploader itself, on its fake server).
Checked: exit 0, the closing "nothing has been uploaded or published" line and a valid summary; a dry run writes nothing;
the usage errors; exit 4 for a receipt that is not complete.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_UNIT = Path(__file__).resolve().parents[1] / "unit"
for _path in (_UNIT / "raw", _UNIT / "corpus", _UNIT / "release"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import release_support as rs  # noqa: E402

RELEASE_TOML = '''title = "AgentPROV test collection"
description_preamble = "An index built by the CLI tests."
keywords = ["test"]
version = "0.1.0"

[[creators]]
name = "Test Creator"
'''


def _receipt(part: Path, number: int, **changes: Any) -> Path:
    manifest = json.loads((part / "DEPOSIT-MANIFEST.json").read_text("utf-8"))
    raw = (part / "DEPOSIT-MANIFEST.json").read_bytes()
    files = [{k: e[k] for k in ("bytes", "md5", "name", "sha256")} | {"uploaded": True}
             for key in ("archives", "documents") for e in manifest[key]]
    files.append({"bytes": len(raw), "md5": hashlib.md5(raw).hexdigest(), "name": "DEPOSIT-MANIFEST.json",
                  "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "uploaded": True})
    data = {"format": "agentprov-zenodo-draft-receipt/0.2", "target": "sandbox", "host": "sandbox.zenodo.org",
            "draft_dir": part.name, "kind": "new", "status": "complete", "deposition_id": 5000 + number,
            "reserved_doi": f"10.5072/zenodo.{5000 + number}", "reserved_recid": 5000 + number, "communities": [],
            "files": files, "metadata": {"title": f"Part {number}", "license": "mit"}, **changes}
    path = part.parent / f"{part.name}.zenodo-sandbox-draft-receipt.json"
    path.write_text(json.dumps(data), "utf-8")
    return path


@pytest.fixture
def setup(tmp_path_factory, tmp_path, monkeypatch):
    from agentprov.cli import package

    monkeypatch.setattr(package, "git_facts", lambda repo=package.REPO_ROOT: (rs.PRODUCER.git_commit, True))
    monkeypatch.setattr(package, "_is_ignored", lambda tree, path: True)
    metadata = tmp_path / "release.toml"
    metadata.write_text(RELEASE_TOML)
    (tmp_path / "parts").mkdir()
    corpora, receipts = [], []
    for number, corpus_id in enumerate(("mini-mit", "mini-mit-b"), start=1):
        root = rs.sealed(tmp_path_factory, tmp_path / "corpora", corpus_id)
        part = tmp_path / "parts" / f"r{number}-{corpus_id}"
        rs.build([root], part)
        corpora.append(root)
        receipts.append(_receipt(part, number))
    return corpora, receipts, metadata


def _args(out: Path, metadata: Path, corpora: list[Path], receipts: list[Path]) -> list[str]:
    args = ["package", "--index", str(out), "--metadata", str(metadata), "--release-date", "2026-10-11"]
    for corpus in corpora:
        args += ["--corpus", str(corpus)]
    for receipt in receipts:
        args += ["--part", str(receipt)]
    return args


def test_index_mode_writes_the_index_and_says_nothing_was_published(cli, setup, tmp_path, check_summary):
    corpora, receipts, metadata = setup
    run = cli(*_args(tmp_path / "index", metadata, corpora, receipts), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["counters"] == {"bytes": summary["counters"]["bytes"], "corpora": 2, "documents": 6, "parts": 2}
    assert "Nothing has been uploaded or published." in run.err
    assert "r1-mini-mit: reserved DOI 10.5072/zenodo.5001; licence class MIT; corpora mini-mit" in run.err
    index = json.loads((tmp_path / "index" / "COLLECTION-INDEX.json").read_text("utf-8"))
    assert [p["reserved_doi"] for p in index["parts"]] == ["10.5072/zenodo.5001", "10.5072/zenodo.5002"]
    assert index["version"] == "0.1.0"


def test_a_dry_run_writes_nothing(cli, setup, tmp_path):
    corpora, receipts, metadata = setup
    run = cli(*_args(tmp_path / "index", metadata, corpora, receipts), "--dry-run", "--json")
    assert run.code == 0 and run.json()["dry_run"] is True
    assert "would write" in run.err and not (tmp_path / "index").exists()


def test_usage_errors_exit_2(cli, setup, tmp_path):
    corpora, receipts, metadata = setup
    out = tmp_path / "index"
    base = _args(out, metadata, corpora, receipts)
    assert cli(*base, "--deposit", str(tmp_path / "d")).code == 2
    assert cli(*base, "--max-archive-bytes", "100000").code == 2
    assert cli(*base, "--allow-mixed-licence-classes").code == 2
    assert cli(*base, "--corpus-version", "0.1.0").code == 2
    assert cli(*[a for a in base if a not in ("--release-date", "2026-10-11")]).code == 2
    assert cli(*[a for a in base if a not in ("--metadata", str(metadata))]).code == 2
    no_parts = [a for a in base if a != "--part" and a not in map(str, receipts)]
    assert cli(*no_parts).code == 2  # --index without a --part
    assert cli("package", "--corpus", str(corpora[0]), "--part", str(receipts[0])).code == 2  # --part without --index
    assert not out.exists()


def test_an_incomplete_part_is_refused_exit_4(cli, setup, tmp_path):
    corpora, receipts, metadata = setup
    _receipt(receipts[1].parent / receipts[1].name.split(".zenodo-")[0], 2, status="uploading")
    run = cli(*_args(tmp_path / "index", metadata, corpora, receipts), "--json")
    assert run.code == 4 and run.json()["outcome"] == "refused"
    assert not (tmp_path / "index").exists()
