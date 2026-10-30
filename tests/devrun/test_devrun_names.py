"""GUI review GR-26 (in the core since D-705: ``agentprov devrun prune``): a dev run's prune deletes only folders that are dev runs (a whole ``<timestamp>[-N]`` name and a
regular ``devrun.json`` of the dev-run format), never through a linked ``dev-runs`` folder, newest by stamp and suffix."""

from __future__ import annotations

import json
from pathlib import Path

from agentprov.cli.devrun import prune
from agentprov.devrun.plan import DEVRUN_FORMAT

RUNS = ("20200101T000000Z", "20210101T000000Z", "20220101T000000Z")


def make_run(root: Path, name: str, fmt: str = DEVRUN_FORMAT) -> Path:
    run = root / name
    run.mkdir(parents=True)
    (run / "devrun.json").write_text(json.dumps({"format": fmt}), encoding="utf-8")
    return run


def test_prune_spares_folders_that_only_start_with_a_timestamp(tmp_path: Path) -> None:
    root = tmp_path / "dev-runs"
    for name in RUNS:
        make_run(root, name)
    notes = root / ("20150101T000000Z" + "_my" + "_notes")
    notes.mkdir()
    (notes / "mine.txt").write_text("keep me", encoding="utf-8")
    backup = make_run(root, "20990101T000000Z" + ".bak")  # a copy, not a run, even with a manifest
    deleted = prune(tmp_path, 1, delete=True)
    assert sorted(p.name for p in deleted) == list(RUNS[:2])
    assert (root / RUNS[2]).is_dir() and (notes / "mine.txt").is_file() and backup.is_dir()


def test_prune_needs_a_dev_run_manifest(tmp_path: Path) -> None:
    root = tmp_path / "dev-runs"
    for name in RUNS:
        make_run(root, name)
    bare = root / "20190101T000000Z"
    (bare / "x").mkdir(parents=True)  # no devrun.json
    other = make_run(root, "20180101T000000Z", fmt="some-other/0.1")
    linked = root / "20170101T000000Z"
    linked.mkdir()
    (linked / "devrun.json").symlink_to(root / RUNS[0] / "devrun.json")
    deleted = prune(tmp_path, 2, delete=True)
    assert [p.name for p in deleted] == [RUNS[0]]
    assert bare.is_dir() and other.is_dir() and linked.is_dir()


def test_prune_refuses_a_linked_dev_runs_folder(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    for name in RUNS:
        make_run(elsewhere, name)
    home = tmp_path / "home"
    home.mkdir()
    (home / "dev-runs").symlink_to(elsewhere, target_is_directory=True)
    assert prune(home, 1, delete=True) == []
    assert sorted(p.name for p in elsewhere.iterdir()) == list(RUNS)


def test_prune_orders_same_second_runs_by_number(tmp_path: Path) -> None:
    root = tmp_path / "dev-runs"
    stamp = "20200101T000000Z"
    for name in (stamp, f"{stamp}-2", f"{stamp}-10"):
        make_run(root, name)
    deleted = prune(tmp_path, 1, delete=True)
    assert sorted(p.name for p in deleted) == [stamp, f"{stamp}-2"]
    assert (root / f"{stamp}-10").is_dir()
