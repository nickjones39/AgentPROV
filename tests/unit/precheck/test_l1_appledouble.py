"""L1-09 classes of OS-metadata member labels (synthetic labels only)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "precheck"


@pytest.fixture(scope="module")
def ad() -> Any:
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("l1_appledouble", TOOLS / "l1_appledouble.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("label", "expected"), [
    ("runs/a/trace.json", []),
    ("runs/a/._trace.json", ["appledouble"]),
    ("__MACOSX/runs/a/._trace.json", ["appledouble", "macosx_dir"]),
    ("__MACOSX/runs/a/", ["macosx_dir"]),
    ("logs/x.zip!/__MACOSX/logs/._y.eval", ["appledouble", "macosx_dir"]),
    ("runs/.DS_Store", ["ds_store"]),
    ("runs/Thumbs.db", ["other_os"]),
    ("runs/._.DS_Store", ["appledouble"]),
])  # fmt: skip
def test_classes_of(ad: Any, label: str, expected: list[str]) -> None:
    assert ad.classes_of(label) == expected


def test_count_include_exposure(ad: Any) -> None:
    entries = [SimpleNamespace(label="a/x.eval", disposition="listed", size=10),
               SimpleNamespace(label="__MACOSX/a/._x.eval", disposition="listed", size=4),
               SimpleNamespace(label="a/._y.json", disposition="not_selected", size=4)]  # fmt: skip
    out = ad.count(entries, {"a/x.eval": "selected", "__MACOSX/a/._x.eval": "stray"})
    assert out["metadata_members"] == 2 and out["metadata_include_match"] == 1
    assert out["by_class"]["appledouble"] == {"include_match": 1, "include_match_bytes": 4, "not_selected": 1, "walked": 2}
    assert out["final_disposition"]["macosx_dir"] == {"stray": 1}
