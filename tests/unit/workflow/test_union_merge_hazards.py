"""Why the shared docs do not use ``merge=union`` (design ``docs/reports/workflow-tools/design.md`` §2.1, D-421).

Git's union driver keeps both sides of a conflict but first drops the lines the two sides share at its edges. On
decision entries and regen-batch rows, which are edited after they are written and often end alike, that corrupts
them without a conflict being reported. These tests pin that behaviour. If a future git stops doing it, they fail,
and the decision can be revisited; until then, union is used only for the id-ledger mirror (see
``test_reserve_id.py::test_mirror_union_merge_keeps_every_reservation``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from wf_support import commit, git, write

BASE = "# Decisions\n\n- **D-1.** First.\n  - user-approved.\n\n- **D-2.** Second, proposed.\n"


@pytest.fixture
def union_repo(tmp_path: Path) -> Path:
    root = tmp_path / "union"
    root.mkdir()
    git(root, "init", "-q", "-b", "base")
    write(root, ".gitattributes", "D.md merge=union\n")
    write(root, "D.md", BASE)
    commit(root, "base")
    return root


def _branch(root: Path, name: str, text: str) -> None:
    git(root, "switch", "-q", "-c", name, "base")
    write(root, "D.md", text)
    commit(root, name)


def _merge(root: Path, ours: str, theirs: str) -> str:
    git(root, "switch", "-q", ours)
    git(root, "merge", "-q", "--no-edit", theirs)  # no conflict is reported
    return (root / "D.md").read_text(encoding="utf-8")


def test_shared_trailing_lines_are_lost_from_one_entry(union_repo: Path) -> None:
    _branch(union_repo, "e", BASE + "\n- **D-421.** Alpha.\n\n  Rejected alternatives:\n  - none.\n\n"
                                    "  Status: proposed.\n")
    _branch(union_repo, "f", BASE + "\n- **D-401.** Beta, longer first line.\n  extra beta line\n\n"
                                    "  Rejected alternatives:\n  - pytest-parallel.\n\n  Status: proposed.\n")
    merged = _merge(union_repo, "f", "e")
    assert merged.count("Status: proposed.") == 1, "both entries kept their status: re-check D-421"
    d401 = merged[merged.index("D-401"):merged.index("D-421")]
    assert "Status: proposed." not in d401  # D-401 silently lost its closing lines


def test_a_status_edit_next_to_an_append_resurrects_the_old_line(union_repo: Path) -> None:
    _branch(union_repo, "approve", BASE.replace("Second, proposed.", "Second, user-approved."))
    _branch(union_repo, "append", BASE + "\n- **D-3.** Third.\n")
    merged = _merge(union_repo, "approve", "append")
    assert "Second, user-approved." in merged and "Second, proposed." in merged
    assert len(re.findall(r"^- \*\*D-2\.\*\*", merged, flags=re.M)) == 2


def test_table_rows_duplicate_and_number_collisions_pass_silently(union_repo: Path) -> None:
    table = BASE + "\n| # | Item | Status |\n|---|---|---|\n| 28 | strings | planned |\n\nNotes.\n"
    write(union_repo, "D.md", table)
    commit(union_repo, "table")
    git(union_repo, "branch", "-f", "table-base")
    git(union_repo, "switch", "-q", "-c", "t1", "table-base")
    write(union_repo, "D.md", table.replace("| 28 | strings | planned |",
                                            "| 28 | strings | implemented |\n| 29 | carved blobs | approved |"))
    commit(union_repo, "t1")
    git(union_repo, "switch", "-q", "-c", "t2", "table-base")
    write(union_repo, "D.md", table.replace("| 28 | strings | planned |",
                                            "| 28 | strings | planned |\n| 29 | split parts | proposed |"))
    commit(union_repo, "t2")
    merged = _merge(union_repo, "t1", "t2")
    assert len(re.findall(r"^\| 28 \|", merged, flags=re.M)) == 2
    assert len(re.findall(r"^\| 29 \|", merged, flags=re.M)) == 2
