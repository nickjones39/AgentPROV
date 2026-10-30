"""The fixture-tree caps (docs/architecture K.4.1(5); DECISIONS D-360): ``tests/FIXTURES.json`` and its checker.

Sizes only: the synthetic cases below never touch fixture content (R-42).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentprov.testing import fixture_caps
from agentprov.testing.fixture_caps import Caps, parse_caps, problems

REPO = Path(__file__).resolve().parents[2]
KIB, MIB = 1024, 1024 * 1024


def _caps(oversize=None, exceptions=None) -> Caps:
    return Caps(16 * MIB, MIB, 512 * KIB, dict(oversize or {}), dict(exceptions or {}))


def test_the_shipped_caps_are_the_decided_ones():
    doc = json.loads((REPO / "tests" / "FIXTURES.json").read_bytes())
    caps = parse_caps(doc)
    assert (caps.total_bytes, caps.file_bytes, caps.source_budget_bytes) == (16 * MIB, MIB, 512 * KIB)
    assert all(reason.strip() for reason in caps.oversize_files.values())
    assert all(reason.strip() and budget > 512 * KIB for budget, reason in caps.source_exceptions.values())
    assert doc["decision"].startswith("D-360")


def test_the_repository_tree_is_within_its_caps():
    root = REPO / "tests" / "fixtures"
    if not root.is_dir():
        pytest.skip("no fixture tree")
    assert fixture_caps.check_tree(root) == []


def test_a_tree_within_every_cap_has_no_problem():
    assert problems({"a/x.json": 100 * KIB, "b/y.json": 200 * KIB}, _caps()) == []


def test_an_over_budget_source_without_an_exception_fails():
    found = problems({"big/x.json": 400 * KIB, "big/y.json": 200 * KIB}, _caps())
    assert len(found) == 1 and found[0].startswith("big/:") and "no exception" in found[0]


def test_an_over_budget_source_whose_exception_has_no_reason_fails():
    found = problems({"big/x.json": 600 * KIB}, _caps(exceptions={"big": (700 * KIB, "  ")}))
    assert found == ["big/: the source exception has no reason"]


def test_an_exception_with_a_reason_admits_the_source_up_to_its_budget():
    caps = _caps(exceptions={"big": (700 * KIB, "the golden set")})
    assert problems({"big/x.json": 600 * KIB}, caps) == []
    assert problems({"big/x.json": 800 * KIB}, caps) == [f"big/: {800 * KIB} B is over its recorded budget of {700 * KIB} B"]


def test_stale_exceptions_and_oversize_entries_fail():
    caps = _caps(oversize={"a/gone.eval": "removed"}, exceptions={"small": (700 * KIB, "was large")})
    found = problems({"small/x.json": 10 * KIB}, caps)
    assert any(p.startswith("a/gone.eval:") for p in found) and any(p.startswith("small/:") for p in found)


def test_an_oversize_entry_whose_file_the_export_keeps_private_may_be_absent():
    caps = _caps(oversize={"inspect/big.eval": "one log", "other/gone.eval": "removed"})
    found = problems({}, caps, private={"inspect/big.eval"})
    assert found == ["other/gone.eval: oversize entry for a file that is absent or within the per-file cap"]
    assert problems({}, _caps(oversize={"cl/x/big.eval": "copyleft"}), private={"cl/"}) == []
    # present, the file is checked as before: a private class excuses only its absence
    assert problems({"inspect/big.eval": 10 * KIB}, caps, private={"inspect/big.eval"})[0].startswith("inspect/big.eval:")


def test_export_private_follows_the_d943_fixture_rule(tmp_path):
    def source(rel, entries):
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
        (tmp_path / rel / "SOURCE.json").write_text(json.dumps(entries), encoding="utf-8")

    source("mit", [{"sample_file": "a.json", "synthetic": False, "licence_class": "permissive"}])
    source("syn", [{"sample_file": "b.json", "synthetic": True}])
    source("harm", [{"sample_file": "c.eval", "synthetic": False, "licence_class": "restricted_use"},
                    {"sample_file": "../LICENSES/H.txt", "synthetic": False, "licence_class": "restricted_use"}])
    source("nodoc", {"synthetic": False})
    source("gpl", [{"sample_file": "d.json", "synthetic": False, "licence_class": "restricted"}])
    assert fixture_caps.export_private(tmp_path) == {"harm/c.eval", "LICENSES/H.txt", "nodoc/", "gpl/"}


def test_a_file_over_one_mib_needs_an_oversize_entry_with_a_reason():
    sizes = {"src/big.eval": 2 * MIB}
    exceptions = {"src": (3 * MIB, "one complete log")}
    assert any("not listed in oversize_files" in p for p in problems(sizes, _caps(exceptions=exceptions)))
    assert problems(sizes, _caps(oversize={"src/big.eval": ""}, exceptions=exceptions)) == \
        ["src/big.eval: the oversize entry has no reason"]
    assert problems(sizes, _caps(oversize={"src/big.eval": "one log"}, exceptions=exceptions)) == []


def test_the_total_cap_counts_every_file():
    sizes = {f"s{i}/x.bin": 500 * KIB for i in range(40)}  # 40 sources, each within budget, 19.5 MiB in all
    assert problems(sizes, _caps()) == [f"the fixture tree holds {40 * 500 * KIB} B, over the {16 * MIB} B cap"]


def test_a_malformed_caps_file_is_refused():
    with pytest.raises(ValueError):
        parse_caps({"format": "other"})
    with pytest.raises(ValueError):
        parse_caps({"format": fixture_caps.FORMAT, "caps": {"total_bytes": 0, "file_bytes": 1, "source_budget_bytes": 1}})
    with pytest.raises(ValueError):
        parse_caps({"format": fixture_caps.FORMAT, "caps": {"total_bytes": 1, "file_bytes": 1, "source_budget_bytes": 1},
                    "source_exceptions": [{"source": "a", "budget_bytes": 2, "reason": "x"},
                                          {"source": "a", "budget_bytes": 2, "reason": "y"}]})
