"""L1-10 screen of non-JSON raw-store files (synthetic text only)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "precheck"))


@pytest.fixture(scope="module")
def lc() -> Any:
    import l1_context

    return l1_context


def test_screen_counts_without_values(lc: Any) -> None:
    name = "alice" + "smith"
    key = "AKIA" + "Q" * 16
    text = f"cd /Users/{name}/proj && cp /home/ubuntu/x . # {key}\n/Users/{name}/again\n"
    res = lc.screen(text, operator="someoneelse")
    named = {k: v for k, v in res["hits"].items() if k.endswith(":named")}
    assert sum(named.values()) == 2 and any(k.endswith(":generic") for k in res["hits"])
    assert res["hits"]["secret:aws-access-key-id"] == 1
    assert all(len(d) == 12 and name not in d for ds in res["digests"].values() for d in ds)
    assert lc.screen(f"/Users/{name}/x", operator=name)["operator"] == 1


def test_candidates_skip_json_and_selected(lc: Any) -> None:
    ents = [SimpleNamespace(label=lab, own=lab, disposition="listed") for lab in ("a/README.md", "a/x.json", "a/run.py", "a/u.json")]
    disp = {"a/README.md": "context", "a/x.json": "context", "a/run.py": "blob", "a/u.json": "selected"}
    assert [e.label for e in lc.candidates(ents, disp)] == ["a/README.md", "a/run.py"]
