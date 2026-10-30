"""The full-history index (deferrals part B; ``agentprov.raw.history.FullHistoryIndex``).

Pure tests on hand-made log blocks: every version ever added under a prefix gets its introducing commit by the rule of
the pinned indexes, superseded versions are kept with no pin, the pinned rows agree with each pin's own index, and a
pinned blob the walked history does not reach refuses the whole index.
"""

from __future__ import annotations

import json

import pytest

from agentprov.raw.history import (
    FULL_INDEX_FORMAT,
    HistoryError,
    LogCommit,
    build_full_index,
    build_index,
    introducing_commits,
)

C1, C2, C3 = "1" * 40, "2" * 40, "3" * 40
B1, B2, B3 = "a" * 40, "b" * 40, "c" * 40
REPO = "https://github.com/o/r"

# runs/x was B1 (C1), replaced by B2 (C2); runs/y is B3 (C2); src/z is outside the prefix
BLOCKS = [
    LogCommit(C2, 1, 200, (("runs/x", B2), ("runs/y", B3), ("src/z", B1))),
    LogCommit(C1, 0, 100, (("runs/x", B1),)),
]
PINS = {"old": {"runs/x": B1, "src/z": B1}, "new": {"runs/x": B2, "runs/y": B3, "src/z": B1}}
PIN_COMMITS = {"old": C1, "new": C2}


def _full() -> object:
    return build_full_index(REPO, C2, "runs/", PINS, PIN_COMMITS, introducing_commits(BLOCKS, None, prefix="runs/"),
                            history_commits=2)


def test_every_version_under_the_prefix_gets_its_introducing_commit():
    best = introducing_commits(BLOCKS, None, prefix="runs/")
    assert best == {("runs/x", B1): (100, C1), ("runs/x", B2): (200, C2), ("runs/y", B3): (200, C2)}


def test_superseded_versions_are_kept_and_pins_are_named():
    full = _full()
    assert full.rows[("runs/x", B1)] == (C1, ("old",))
    assert full.rows[("runs/x", B2)] == (C2, ("new",))
    assert full.rows[("runs/y", B3)] == (C2, ("new",))


def test_the_pinned_rows_agree_with_each_pins_own_index():
    full = _full()
    for role, tree in PINS.items():
        own = build_index(REPO, PIN_COMMITS[role], "4" * 40, {p: b for p, b in tree.items() if p.startswith("runs/")},
                          introducing_commits(BLOCKS, tree))
        assert full.pinned_rows(role) == dict(own.rows)


def test_the_file_is_deterministic_and_counts_superseded_rows():
    data = _full().to_bytes()
    assert data == _full().to_bytes()
    header, *rows = (json.loads(line) for line in data.splitlines())
    assert header["format"] == FULL_INDEX_FORMAT and header["entries"] == 3 and header["superseded"] == 0
    assert header["pins"] == {"new": C2, "old": C1} and header["prefix"] == "runs/"
    assert [(r["p"], r["b"], r["pins"]) for r in rows] == [("runs/x", B1, ["old"]), ("runs/x", B2, ["new"]),
                                                          ("runs/y", B3, ["new"])]
    pins_without_old = {"new": PINS["new"]}
    lone = build_full_index(REPO, C2, "runs/", pins_without_old, {"new": C2}, introducing_commits(BLOCKS, None, prefix="runs/"))
    assert json.loads(lone.to_bytes().splitlines()[0])["superseded"] == 1  # runs/x@B1 is held by no pin


def test_a_pinned_blob_the_history_does_not_reach_refuses_the_index():
    with pytest.raises(HistoryError) as err:
        build_full_index(REPO, C2, "runs/", {"new": {"runs/q": B1}}, {"new": C2}, introducing_commits(BLOCKS, None, prefix="runs/"))
    assert err.value.code == "raw.history.incomplete"
