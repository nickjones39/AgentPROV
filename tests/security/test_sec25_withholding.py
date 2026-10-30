"""SEC-25 continued: the purge-to-release path (P-3 resolved; G.9.5, G.9.6; HL H.4.5, H.5.5; D-230..D-236).

End to end: import (release mode) -> seal 0.1.0 -> ``purge`` of the leaked object -> re-version (``CHANGES.toml`` 0.2.0,
``release.previous``) -> seal 0.2.0 -> ``verify --level chain --release``. Checked:

* the sealed 0.2.0 corpus verifies in release mode (exit 0, no finding): the tombstone is accepted because
  ``WITHHELD.json`` lists the object (``tombstoned_withheld``), and the withheld execution left the index;
* **no file** of the sealed tree, of its deposit draft or of any command output holds the leaked value or any 8-character
  fragment of it; the private sidecar ``DIR.withheld/`` still holds the AER that does (renamed, never deleted);
* ``WITHHELD.json`` lists the object with its digest and pinned origin, the execution with its stage digests (so it can be
  recomputed locally from the pin), and the manifest declares it (``files.withheld``; ``raw_set`` disposition
  ``withheld``; ``issues_by_code["release.withheld"]``); the datasheet reports the count and the reason;
* the deposit builder accepts the corpus; a tombstone that ``WITHHELD.json`` does not list still fails release mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest
import verify_support as vs
import withheld_harness as wh
from corpus_harness import verify

cli = harness.cli


@pytest.fixture
def purged(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> dict[str, Any]:
    return wh.purged_sealed(tmp_path_factory, tmp_path / "corpora")


def test_sec25_a_purged_working_corpus_seals_as_a_new_version_and_verifies_in_release_mode(cli, purged):
    root = purged["root"]
    report = purged["report"]
    assert report.counters["withheld_objects"] == 1 and report.counters["withheld_executions"] == 1
    assert report.counters["executions"] == 1 and report.sidecar is not None and report.sidecar.name == "c.withheld"
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 0 and run.codes() == {}, run.codes()
    counters = run.json()["counters"]
    assert counters["tombstoned_withheld"] == 1 and counters["withheld_objects"] == 1
    assert counters["withheld_executions"] == 1 and counters["tombstoned"] == 0
    assert wh.fragments_in(run.out + run.err) == 0


def test_sec25_no_released_byte_holds_the_value_and_the_private_sidecar_keeps_it(purged):
    released = wh.files(purged["root"])
    leaking = sorted(label for label, data in released.items() if wh.fragments_in(data))
    assert leaking == []
    assert not any(label.endswith(purged["leak"] + ".json") for label in released)
    assert not any(purged["ex"] in label for label in released)
    private = wh.files(purged["sidecar"])
    held = [label for label, data in private.items() if wh.fragments_in(data)]
    assert any(label.startswith("aer/") and purged["ex"] in label for label in held)  # renamed, never deleted
    (row,) = [json.loads(line) for line in private["executions.jsonl"].split(b"\n") if line]
    assert row["ex"] == purged["ex"] and row["digests"]["aer"] == purged["aer_digest"]
    assert private["WITHHELD.json"] == released["WITHHELD.json"]


def test_sec25_withheld_json_records_the_object_and_the_execution_without_the_value(purged):
    from agentprov.corpus.withheld import decode_withheld

    root = purged["root"]
    data = (root / "WITHHELD.json").read_bytes()
    assert wh.fragments_in(data) == 0
    document = decode_withheld(data)
    (entry,) = document.entries
    assert entry.sha256 == purged["leak"] and (entry.reason, entry.basis, entry.decided_on) == ("secret", "purge", wh.DAY)
    assert entry.affected_executions == (purged["ex"],) and entry.media_type == "application/json"
    origins = [json.loads(line)["origin"] for line in (root / "raw" / "origins.jsonl").read_bytes().split(b"\n")
               if line and json.loads(line)["sha256"] == "sha256:" + purged["leak"]]
    assert [dict(o) for o in entry.origins] == origins and origins[0]["kind"] == "git"
    (execution,) = document.executions
    assert execution.ex == purged["ex"] and execution.digests["aer"] == purged["aer_digest"]
    assert execution.snapshot_ids == ("2024-06",)


def test_sec25_the_manifest_declares_the_withholding(purged):
    from agentprov.corpus.manifest import file_ref

    root = purged["root"]
    m = vs.manifest(root)
    assert m["corpus_version"] == "0.2.0"
    assert m["release"]["previous"] == {"content_digest": purged["v010"].content_digest, "corpus_version": "0.1.0"}
    assert m["files"]["withheld"] == file_ref("WITHHELD.json", (root / "WITHHELD.json").read_bytes(), jsonl=False)
    assert m["counts"]["executions"] == 1 and m["counts"]["issues_by_code"]["release.withheld"] == 1
    assert m["counts"]["candidates"] == m["counts"]["executions"] + m["counts"]["not_imported"]
    assert m["licences"]["policy"]["raw_policy"] == "include"
    assert (root / "schemas" / "withheld-0.1.schema.json").is_file()
    first = vs.manifest(purged["first"])
    assert first["counts"]["executions"] == 2 and "withheld" not in first["files"]
    assert first["digests"]["raw_set"] != m["digests"]["raw_set"]


def test_sec25_the_datasheet_reports_the_count_and_the_reason(purged):
    text = (purged["root"] / "DATASHEET.md").read_text("utf-8")
    assert "Withheld items: 2 (H.4.5): 1 raw objects" in text
    assert "| secret | purged from the private raw store (G.9.6) | 1 | 1 |" in text
    assert wh.fragments_in(text) == 0
    assert "Withheld items: 0 (H.4.5)." in (purged["first"] / "DATASHEET.md").read_text("utf-8")


def test_sec25_the_deposit_builder_accepts_the_new_version_and_its_draft_holds_no_fragment(purged, tmp_path):
    import release_support as rs

    report = rs.build([purged["root"]], tmp_path / "deposit")
    assert report.corpora[0]["corpus_id"] == "mini-agentdojo"
    for path in sorted((tmp_path / "deposit").rglob("*")):
        if path.is_file():
            assert wh.fragments_in(path.read_bytes()) == 0, path.name


def test_sec25_a_tombstone_withheld_json_does_not_list_still_fails_release_mode(cli, purged):
    """The acceptance is exact: the tombstone of an object that ``WITHHELD.json`` does not list (a forged tombstone over a
    second, removed object, with the manifest and checksums regenerated) stays ``tombstoned`` and fails release mode."""
    from agentprov.corpus.purge import Tombstone, decode_tombstones, encode_tombstones

    root = purged["root"]
    label = sorted(str(p.relative_to(root)) for p in (root / "raw" / "objects").rglob("*.json"))[0]
    other = label.rsplit("/", 1)[-1].split(".", 1)[0]
    (root / label).chmod(0o644)
    (root / label).unlink()
    for parent in ((root / label).parent, root / "raw" / "objects"):
        if not any(parent.iterdir()):
            parent.rmdir()  # a sealed tree has no empty directory (H.1.5(4))
    tombstones = decode_tombstones((root / "raw" / "tombstones.jsonl").read_bytes())
    (root / "raw" / "tombstones.jsonl").write_bytes(encode_tombstones([*tombstones, Tombstone(other, "secret", wh.DAY)]))
    vs.reforge(root)
    run = verify(cli, root, "--level", "chain", "--release", "--root-digest", vs.root_digest(root))
    assert run.code == 1 and run.codes().get("raw.tombstoned") == 1
    assert run.json()["counters"]["tombstoned_withheld"] == 1
