"""URL download pins as archive inputs (D-455; R-10j-3; HL H.2.3 ``url``).

A ``url`` pin's file (a Figshare-shaped deposit here: a test deposit with its own pin, never a real one) is imported as
an archive input like a Zenodo or Hugging Face file: checked against the pinned SHA-256 and size, stored, expanded in
place and its members mapped. A URL is a mutable origin, so the import records when the file was retrieved: the fetch
cache's acquisition record, else the pin's ``retrieved_at``; with neither it is refused, never stamped with the time
of the import (invariant 2). The sealed snapshot origin is ``{kind: url, url, retrieved_at}``.

Members are the committed, licence-cleared FooBench fixture files, loaded programmatically and never printed. No
network: the one download goes through ``FakeTransport``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.runner.importer import ArchiveTree, import_source
from agentprov.corpus.manifest import ManifestError, origin_matches_pin, snapshot_origin_from_pin
from agentprov.corpus.writer import CorpusWriter
from agentprov.errors import AgentProvError
from agentprov.raw.fetch import ACQUISITIONS_NAME, DigestMismatchError, Fetcher, Recipe
from agentprov.raw.origins import OriginUnpinnedError

REPO = Path(__file__).resolve().parents[3]
FOO = REPO / "tests" / "fixtures" / "foobench"
FOO_FILES = ("trace-001.jsonl", "sub-trace-001.jsonl", "screenshot-0.png")
URL = "https://figshare.com/ndownloader/files/90000001"
RETRIEVED_AT = "2026-09-30T12:34:56Z"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def _deposit(path: Path, **pin: Any) -> dict[str, Any]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FOO_FILES:
            archive.writestr(f"deposit/traces/{name}", (FOO / name).read_bytes())
    path.write_bytes(buf.getvalue())
    return {"role": "fixture", "kind": "url", "url": URL, "file": path.name,
            "sha256": hashlib.sha256(buf.getvalue()).hexdigest(), "bytes": len(buf.getvalue()), **pin}  # fmt: skip


def _import(tmp: Path, pin: dict[str, Any], out: str = "c", **tree: Any) -> tuple[Any, Path]:
    archive = ArchiveTree(tmp / pin["file"], pin=pin, sha256=pin["sha256"], size=pin["bytes"], **tree)
    with CorpusWriter(tmp / out) as writer:
        report = import_source("foobench", archive, corpus=writer, profile_id="foobench", part="fixture", pin=pin,
                               in_process=True)  # fmt: skip
    return report, tmp / f"{out}.partial"


def _cli_args(tmp: Path, **overrides: Any) -> argparse.Namespace:
    values = {"fetch": False, "input": str(tmp / "deposit.zip"), "verify_against_pin": True, "allow_hardlinks": False,
              "allow_network": False, "dry_run": False, "cache_dir": None, **overrides}  # fmt: skip
    return argparse.Namespace(**values)


# ------------------------------------------------------------------------------------------------ the pinned time
def test_a_url_archive_input_records_the_pins_retrieval_time_and_seals_a_url_origin(tmp_path):
    pin = _deposit(tmp_path / "deposit.zip", retrieved_at=RETRIEVED_AT)
    report, partial = _import(tmp_path, pin)
    assert report.counters["mapped"] == 1 and report.counters["degenerate"] == 0  # the toy fixture's own issues aside
    origins = [o["origin"] for o in _jsonl(partial / "raw" / "origins.jsonl")]
    containers = [o for o in origins if o["kind"] == "url"]
    assert containers == [{"kind": "url", "retrieved": "2026-09-30", "url": URL}]  # the object origin keeps the date
    snapshot = json.loads((partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert snapshot["pin"] == {"bytes": pin["bytes"], "file": "deposit.zip", "kind": "url", "retrieved_at": RETRIEVED_AT,
                               "role": "fixture", "sha256": pin["sha256"], "url": URL}  # fmt: skip
    assert snapshot["input"]["kind"] == "archive" and snapshot["input"]["label"] == "deposit.zip"
    sealed = snapshot_origin_from_pin(snapshot["pin"], [o for o in origins if o["kind"] != "member"] + [{"kind": "member"}])
    assert sealed == {"kind": "url", "retrieved_at": RETRIEVED_AT, "url": URL}


def test_the_same_url_deposit_imports_byte_identically_and_recompute_re_expands_it(tmp_path, monkeypatch, capsys):
    from agentprov.cli.main import main

    pin = _deposit(tmp_path / "deposit.zip", retrieved_at=RETRIEVED_AT)
    _import(tmp_path, pin, "a")
    _import(tmp_path, pin, "b")
    first, second = tmp_path / "a.partial", tmp_path / "b.partial"
    names = sorted(p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file() and p.name != "corpus.json")
    assert names == sorted(p.relative_to(second).as_posix() for p in second.rglob("*")
                           if p.is_file() and p.name != "corpus.json")  # fmt: skip
    assert all((first / n).read_bytes() == (second / n).read_bytes() for n in names)
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(first), "--dry-run", "--no-reuse", "--in-process", "--json", "--progress", "off"])
    summary = json.loads(capsys.readouterr().out)
    assert code == 0, summary
    assert summary["counters"]["identical"] == summary["counters"]["selected"] == 1  # the url label re-maps (rawtree)


# ------------------------------------------------------------------------------------------------ refusals
@pytest.mark.parametrize("retrieved_at", [None, "2026-09-30", "2026-09-30T12:34:56+00:00", "", 1727699696])
def test_without_a_recorded_retrieval_time_the_url_import_is_refused(tmp_path, retrieved_at):
    pin = _deposit(tmp_path / "deposit.zip")
    if retrieved_at is not None:
        pin["retrieved_at"] = retrieved_at
    with pytest.raises(OriginUnpinnedError) as refused:
        ArchiveTree(tmp_path / "deposit.zip", pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    assert refused.value.code == "raw.origin.unpinned" and refused.value.exit_code == 3
    assert not (tmp_path / "c.partial").exists()


@pytest.mark.parametrize("fetched", [None, RETRIEVED_AT])
def test_a_date_only_retrieved_key_is_refused_even_beside_a_valid_time(tmp_path, fetched):
    pin = _deposit(tmp_path / "deposit.zip", retrieved_at=RETRIEVED_AT, retrieved="2026-09-30")
    with pytest.raises(OriginUnpinnedError, match="date-only"):
        ArchiveTree(tmp_path / "deposit.zip", pin=pin, sha256=pin["sha256"], size=pin["bytes"], retrieved_at=fetched)


def test_the_shipped_dca_pin_is_an_archive_input_with_its_recorded_time(tmp_path):
    from agentprov.adapters.profiles import load_profile

    (pin,) = load_profile("dca-agentdojo").data["source"]["pins"]
    tree = ArchiveTree(tmp_path / str(pin["file"]), pin=pin, sha256=str(pin["sha256"]), size=int(pin["size"]))
    assert tree.retrieved_at == "2026-10-11T09:46:41Z"
    assert tree.origin.to_json() == {"kind": "url", "retrieved": "2026-10-11", "url": pin["url"]}


def test_the_cli_checks_a_url_deposit_against_its_pin_and_refuses_a_missing_time(tmp_path):
    from agentprov.adapters.profiles import load_profile
    from agentprov.cli.common import Context
    from agentprov.cli.import_ import _tree
    from agentprov.ingest.limits import IngestLimits

    pin = _deposit(tmp_path / "deposit.zip", retrieved_at=RETRIEVED_AT)
    args = _cli_args(tmp_path)
    ctx = Context(args=args, env={})
    profile = load_profile("foobench")
    tree, check = _tree(args, ctx, profile, pin, IngestLimits(), None)
    assert isinstance(tree, ArchiveTree) and check is None and tree.retrieved_at == RETRIEVED_AT
    assert tree.origin.to_json() == {"kind": "url", "retrieved": "2026-09-30", "url": URL}
    with pytest.raises(DigestMismatchError):  # sha mismatch: refused before anything is built
        _tree(args, ctx, profile, {**pin, "sha256": "0" * 64}, IngestLimits(), None)
    with pytest.raises(OriginUnpinnedError):
        _tree(args, ctx, profile, {k: v for k, v in pin.items() if k != "retrieved_at"}, IngestLimits(), None)


# ------------------------------------------------------------------------------------------------ the fetched time
class _Response:
    """One served body (the ``raw.fetch.HttpResponse`` shape)."""

    def __init__(self, body: bytes, url: str) -> None:
        self.status, self.headers, self.url, self._body = 200, {}, url, io.BytesIO(body)

    def read(self, n: int = -1, /) -> bytes:
        return self._body.read(n)

    def close(self) -> None:
        pass


class _Transport:
    """Serves one URL; no network."""

    def __init__(self, url: str, body: bytes) -> None:
        self.url, self.body = url, body

    def open(self, url: str, **_kwargs: Any) -> _Response:
        assert url == self.url
        return _Response(self.body, url)


def _seed_cache(tmp: Path, pin: dict[str, Any]) -> Path:
    cache = tmp / "cache"
    stamp = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
    fetcher = Fetcher(cache, allow_network=True, transport=_Transport(URL, (tmp / pin["file"]).read_bytes()),
                      now=lambda: stamp)  # fmt: skip
    result = fetcher.fetch(Recipe.from_pin(pin))
    assert result.network_used and result.retrieved_at == "2026-10-01T08:00:00Z"
    return cache


def test_a_cache_hit_reads_the_retrieval_time_from_the_acquisition_record(tmp_path):
    pin = _deposit(tmp_path / "deposit.zip")
    cache = _seed_cache(tmp_path, pin)
    offline = Fetcher(cache, allow_network=False, now=lambda: datetime(2030, 1, 1, tzinfo=UTC))
    hit = offline.fetch(Recipe.from_pin(pin))
    assert not hit.network_used and hit.retrieved_at == "2026-10-01T08:00:00Z"  # the record's time, not this call's
    (cache / ACQUISITIONS_NAME).unlink()
    assert Fetcher(cache, allow_network=False).fetch(Recipe.from_pin(pin)).retrieved_at is None  # never inferred


def test_import_fetch_uses_the_acquisition_record_over_the_pin_and_refuses_without_either(tmp_path):
    from agentprov.adapters.profiles import load_profile
    from agentprov.cli.common import CommandResult, Context
    from agentprov.cli.import_ import _tree
    from agentprov.ingest.limits import IngestLimits

    pin = _deposit(tmp_path / "deposit.zip", retrieved_at=RETRIEVED_AT)
    cache = _seed_cache(tmp_path, pin)
    args = _cli_args(tmp_path, fetch=True, input=None, verify_against_pin=False, cache_dir=str(cache))
    ctx = Context(args=args, env={})
    tree, _check = _tree(args, ctx, load_profile("foobench"), pin, IngestLimits(), CommandResult())
    assert isinstance(tree, ArchiveTree) and tree.retrieved_at == "2026-10-01T08:00:00Z"
    (cache / ACQUISITIONS_NAME).unlink()
    tree, _check = _tree(args, ctx, load_profile("foobench"), pin, IngestLimits(), CommandResult())
    assert tree.retrieved_at == RETRIEVED_AT  # no record: the pin's own time
    bare = {k: v for k, v in pin.items() if k != "retrieved_at"}
    with pytest.raises(OriginUnpinnedError):
        _tree(args, ctx, load_profile("foobench"), bare, IngestLimits(), CommandResult())


# ------------------------------------------------------------------------------------------------ manifest
def test_the_sealed_url_origin_needs_the_pins_time_and_a_matching_object():
    pin = {"kind": "url", "url": URL, "file": "deposit.zip", "retrieved_at": RETRIEVED_AT}
    good = [{"kind": "url", "url": URL, "retrieved": "2026-09-30"}, {"kind": "member"}]
    assert snapshot_origin_from_pin(pin, good) == {"kind": "url", "retrieved_at": RETRIEVED_AT, "url": URL}
    for bad_pin in ({**pin, "retrieved_at": None}, {**pin, "retrieved_at": "2026-09-30"}):
        with pytest.raises(ManifestError) as unpinned:
            snapshot_origin_from_pin(bad_pin, good)
        assert unpinned.value.code == "corpus.manifest.unpinned"
    for objects in ([{"kind": "url", "url": URL, "retrieved": "2026-09-29"}],
                    [{"kind": "url", "url": URL + "0", "retrieved": "2026-09-30"}],
                    [*good, {"kind": "url", "url": URL, "retrieved": "2026-09-30"}],
                    [*good, {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "x.zip"}]):  # fmt: skip
        with pytest.raises(ManifestError) as mismatch:
            snapshot_origin_from_pin(pin, objects)
        assert mismatch.value.code == "corpus.manifest.pin"
    with pytest.raises(ManifestError) as local:
        snapshot_origin_from_pin(pin, [*good, {"kind": "local"}])
    assert local.value.code == "corpus.manifest.local_origin"


def test_origin_matches_pin_tells_a_url_snapshot_its_own_origin():
    origin = {"kind": "url", "url": URL, "retrieved": "2026-09-30"}
    assert origin_matches_pin(origin, {"kind": "url", "url": URL})
    assert not origin_matches_pin(origin, {"kind": "url", "url": URL + "0"})
    assert not origin_matches_pin(origin, {"kind": "zenodo", "doi": "10.5281/zenodo.1", "file": "deposit.zip"})


def test_a_url_pin_cannot_name_an_archive_in_byte_parts(tmp_path):
    pin = {"kind": "url", "url": URL, "file": "deposit.zip", "archive": "split-zip", "retrieved_at": RETRIEVED_AT,
           "parts": [{"file": "a.z01", "sha256": "0" * 64, "bytes": 1}, {"file": "a.zip", "sha256": "1" * 64, "bytes": 1}]}
    with pytest.raises(AgentProvError) as refused:
        ArchiveTree.split([(tmp_path / "a.z01", "0" * 64, 1), (tmp_path / "a.zip", "1" * 64, 1)], pin=pin)
    assert refused.value.code == "adapter.archive_input"
