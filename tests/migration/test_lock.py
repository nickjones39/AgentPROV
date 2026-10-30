"""``agentprov.migration.lock``: the J.1.4 tree listing digest and the committed ``migration/baseline.lock.json`` (J.1.5)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from agentprov.migration import lock as lk

REPO = Path(__file__).resolve().parents[2]

#: J.1.4: the five tree listing digests of the frozen baseline.
J14 = {
    "release_transcripts": (17664, "46273b01df12d7636da355c07b9fea6d77c328dcd025e6340b183eac6dd8a1ed"),
    "release_graphs": (17664, "86fcc8bab2abdcd48603998ec7ed097e1641433164cc0436d2a3f235bd883c4c"),
    "converted_transcripts": (18027, "ef778a3da0d15aca384b0143cac80d31ff833604dbae0b839faf1e54211627a5"),
    "converted_graphs": (18027, "ac1bf7000e507c831aa592d28a212bc16a61c6a2950efe703b3de42086a33bb7"),
    "native_runs": (18234, "6dc33c9c83c3dd3feb7805079f55575d1c83804f99681ca69a650d117e63664c"),
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------- tree_listing


def test_tree_listing_follows_j14_exactly(tmp_path):
    files = {"b/x.json": b"1", "a/y.json": b"22", "a/B.json": b"333", "z.txt": b"4444", "é/f.json": b"5"}
    for rel, data in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(data)
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    (tmp_path / "a" / "._y.json").write_bytes(b"apple double")
    listing = lk.tree_listing(tmp_path, lambda rel: rel.endswith(".json"))
    chosen = sorted(r for r in files if r.endswith(".json"))  # code-point order: "B" < "y", "é" last
    assert [r for r, _ in listing.entries] == chosen == ["a/B.json", "a/y.json", "b/x.json", "é/f.json"]
    text = "".join(f"{_sha(files[r])}  {r}\n" for r in chosen)
    assert listing.files == 4 and listing.listing_sha256 == _sha(text.encode("utf-8"))


def test_tree_listing_skips_symlinks_and_is_independent_of_the_worker_count(tmp_path):
    for i in range(40):
        (tmp_path / f"d{i % 3}").mkdir(exist_ok=True)
        (tmp_path / f"d{i % 3}" / f"f{i}.json").write_bytes(str(i).encode())
    (tmp_path / "outside.json").write_bytes(b"target")
    try:
        os.symlink(tmp_path / "outside.json", tmp_path / "d0" / "link.json")
        os.symlink(tmp_path / "d1", tmp_path / "dirlink")
    except OSError:
        pytest.skip("symlinks are not available on this host")
    one = lk.tree_listing(tmp_path, lk.PREDICATES["json"], workers=1)
    many = lk.tree_listing(tmp_path, lk.PREDICATES["json"], workers=8)
    assert one == many
    assert one.files == 41 and all("link" not in rel for rel, _ in one.entries)


def test_tree_listing_of_an_empty_selection_and_of_a_missing_root(tmp_path):
    empty = lk.tree_listing(tmp_path, lambda rel: False)
    assert (empty.files, empty.listing_sha256) == (0, _sha(b""))
    with pytest.raises(FileNotFoundError):
        lk.tree_listing(tmp_path / "nope", lambda rel: True)


def test_the_three_predicates_of_j14():
    t, g, j = lk.PREDICATES["transcript"], lk.PREDICATES["graph"], lk.PREDICATES["json"]
    assert t("m/prov/a/x.transcript.json") and not t("m/prov/a/x.json")
    assert g("m/prov/a/x.json") and not g("m/prov/a/x.transcript.json") and not g("m/manifest.json") and not g("m/a/x.json")
    assert j("any/x.json") and j("x.transcript.json") and not j("x.txt")


# --------------------------------------------------------------------------------------------- the committed lock


@pytest.fixture(scope="module")
def committed():
    return lk.load_lock()


def test_the_committed_lock_pins_the_frozen_baseline(committed):
    fw = committed.framework
    assert committed.lock == "agentprov-baseline-lock/1" and committed.frozen_on == "2026-10-07"
    assert fw.commit == "579a908354b93361efe0905ffb7623256aa96a06" and fw.describe == "corpus-v2.3-26-g579a908"
    assert (fw.tag.name, fw.tag.object, fw.tag.pushed) == ("agentprov-baseline-2026-10-07", "be0866ca2dfe4bfa37584b3268d52b5c314bb71a", False)
    assert dict(fw.existing_tags) == {
        "corpus-v2.2": "e920e660ad15454843ecb8cddfacc0aa7956a208",
        "corpus-v2.3": "a7002b49d74ef873364c2e093613651acad170f6",
    }
    assert len(fw.tracked_files) == 13 and fw.tracked_files["pyproject.toml"].startswith("75ce2dbd")
    assert dict(fw.package) == {"name": "agentdojo-prov", "version": "1.0.0"}
    env = committed.environment
    assert (env.python, env.uv, env.agentdojo) == ("3.12.14", "0.12.18", "0.1.35")
    assert env.pip_freeze_sha256 == "0f566a9501eb5b91e6ec8e1e968cf7701ace465673890c3b501328a71759499e"
    assert env.packages["prov"] == "3.2.2" and env.packages["rdflib"] == "7.6.0"
    assert committed.investigation_record["BASELINE.md"].startswith("20e36bce")
    assert committed.investigation_record["baseline.json"].startswith("3155e38a")
    assert committed.investigation_record["golden_index.json"].startswith("1b19afba")
    assert committed.results["pytest"] == {"collected": 363, "passed": 362, "failed": 0, "skipped": 1, "warnings": 693}


def test_the_committed_lock_carries_the_five_j14_tree_digests(committed):
    assert list(committed.trees) == list(J14)
    for name, (files, digest) in J14.items():
        pin = committed.trees[name]
        assert (pin.files, pin.listing_sha256) == (files, digest)
        assert (pin.root, pin.predicate) == lk.TREE_SPECS[name]


def test_the_committed_lock_round_trips_through_the_model_in_j15_key_order(committed):
    raw = json.loads((REPO / "migration" / "baseline.lock.json").read_text(encoding="utf-8"))
    assert committed.to_json() == raw and list(committed.to_json()) == list(raw)
    assert list(raw) == ["lock", "frozen_on", "framework", "environment", "results", "trees", "investigation_record"]
    assert lk.lock_sha256() == _sha((REPO / "migration" / "baseline.lock.json").read_bytes())


def test_the_two_j16_hashes_are_recorded(committed):
    """J.1.6, recorded in phase 8: the requirements hash is the committed hash-locked export's, and the wheel hash is the
    reproducible wheel built from 579a908 with the build backend pinned by migration/baseline-build-constraints.txt."""
    env = committed.environment
    assert env.requirements_lock_sha256 == _sha((REPO / "migration" / "baseline-requirements.txt").read_bytes())
    assert env.baseline_wheel_sha256 == "3dcf0ed052040ce04bfef76a1d5313306e05056db48b80e2a9b8048628a47b53"
    constraints = (REPO / "migration" / "baseline-build-constraints.txt").read_text(encoding="utf-8")
    assert "setuptools==84.0.0" in constraints and constraints.count("--hash=sha256:") >= 1


# --------------------------------------------------------------------------------------------- validation


def _raw():
    return json.loads((REPO / "migration" / "baseline.lock.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(lock="other/1"),
        lambda d: d["framework"].update(commit="abc"),
        lambda d: d["framework"]["tag"].update(object="Z" * 40),
        lambda d: d["framework"]["tag"].update(pushed="no"),
        lambda d: d["framework"]["tracked_files"].update({"x": "short"}),
        lambda d: d["environment"].update(requirements_lock_sha256="nothex"),
        lambda d: d["trees"].pop("native_runs"),
        lambda d: d["trees"]["native_runs"].update(root="elsewhere"),
        lambda d: d["trees"]["release_graphs"].update(files="many"),
        lambda d: d["trees"]["release_graphs"].update(listing_sha256="1234"),
        lambda d: d.update(investigation_record={"x": "y"}),
    ],
)
def test_parse_lock_rejects_invalid_locks(mutate):
    raw = _raw()
    mutate(raw)
    with pytest.raises(lk.LockError):
        lk.parse_lock(json.dumps(raw).encode())


def test_parse_lock_rejects_non_json_duplicates_and_non_objects(tmp_path):
    for bad in (b"not json", b'{"lock": "a", "lock": "b"}', b"[]"):
        with pytest.raises(lk.LockError):
            lk.parse_lock(bad)
    with pytest.raises(lk.LockError, match="cannot read"):
        lk.load_lock(tmp_path / "missing.json")
    assert lk.LockError.exit_code == 3
