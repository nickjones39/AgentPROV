"""``tools/gen_docs.py``: one file per entry and committed generated indexes (D-421, D-422).

Synthetic documents in temporary git repositories exercise the mechanics: the byte-identical split, new entries,
conflicts resolved by regeneration, and ``--adopt`` for branches started before the migration. One test splits
*copies* of today's DECISIONS.md, regen-batch.md and AGENTS.md (in ``tmp_path``) to show the migration would be
byte-identical; the real files are only read.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import gen_docs as gd
import pytest
from wf_support import commit, git, write

REPO = Path(__file__).resolve().parents[3]

DECISIONS = """# Brief

## D0. Principle

Text with a bullet that is not an entry:
- just prose.

## Addendum D

- **D-1 (U-15).** First.
- **D-3 (2026-10-08, x).** Third, placed before D-2 on purpose.
  - Rejected: nothing.
- **D-2 (2026-10-08, y).** Second, proposed.
- D-4–D-5 are reserved.
- **D-3 addendum (2026-10-09).** A top-level addendum.
"""

REGEN = """# Regeneration batch

Intro.

| # | Item | Source | Changes | Notes |
|---|---|---|---|---|
| 1 | B1 | a | b | c |
| — | remeasured | a | b | c |
| 2 | B2 | a | b | c |

Notes between the table and the sections.

## Item 2 (planned, 2026-10-12)

Body of item 2.

## Items 3 and 4 (implemented)

Body.

## A bundle (2026-10-12; D-56)

Bundle body.
"""

AGENTS = """# AGENTS.md

## 0. START HERE

### Parallel sessions (from 2026-10-11): ownership rules

Intro paragraph.
- **Phase 10b:** dtap.
  - detail.
- **Phase 11** (finished): corpus.

### Phase 10b: details

Middle text.

## 13. History

- **2026-10-07.** Architecture phase:
  - investigation.
- **2026-10-08.** Phase 4 (baseline bridge).
"""


@pytest.fixture
def docs_repo(repo: Path) -> Path:
    write(repo, "docs/architecture/DECISIONS.md", DECISIONS)
    write(repo, "docs/reports/analysis/regen-batch.md", REGEN)
    write(repo, "AGENTS.md", AGENTS)
    sha = commit(repo, "docs")
    git(repo, "update-ref", "refs/remotes/origin/main", sha)
    return repo


def _gd(repo: Path, *args: str) -> int:
    return gd.main(["-C", str(repo), *args])


def test_not_migrated_passes_the_check(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _gd(docs_repo, "--check") == 0
    assert capsys.readouterr().out.count("not migrated") == 3


def test_a_target_left_out_of_the_tree_is_absent_and_passes(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D-1004: the public export has neither AGENTS.md nor docs/agents/; --check and --write pass and write nothing."""
    assert _gd(docs_repo, "--split", "agents") == 0
    (docs_repo / "AGENTS.md").unlink()
    shutil.rmtree(docs_repo / "docs/agents")
    commit(docs_repo, "the public export's tree")
    capsys.readouterr()
    assert _gd(docs_repo, "--check", "agents") == 0 and _gd(docs_repo, "--write", "agents") == 0
    assert capsys.readouterr().out.count("gen-docs: agents: absent (AGENTS.md and docs/agents/ are not in this tree)") == 2
    assert not (docs_repo / "AGENTS.md").exists() and not (docs_repo / "docs/agents").exists()


def test_split_is_byte_identical_and_named_stably(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _gd(docs_repo, "--split", "decisions", "regen-batch", "agents") == 0
    assert git(docs_repo, "status", "--porcelain", "--", "AGENTS.md", "docs/architecture/DECISIONS.md",
               "docs/reports/analysis/regen-batch.md") == ""
    d = docs_repo / "docs/architecture/decisions"
    assert sorted(p.name for p in d.glob("*.md")) == [
        "D-1.md", "D-2.md", "D-3-addendum.md", "D-3.md", "D-4-note.md", "_preamble.md"]
    assert (d / "_legacy-order-entries.txt").read_text().split() == [
        "D-1.md", "D-3.md", "D-2.md", "D-4-note.md", "D-3-addendum.md"]
    assert (d / "D-3.md").read_text() == "- **D-3 (2026-10-08, x).** Third, placed before D-2 on purpose.\n" \
                                         "  - Rejected: nothing.\n"
    assert "just prose" in (d / "_preamble.md").read_text()
    r = docs_repo / "docs/reports/analysis/regen-batch"
    assert sorted(p.name for p in (r / "rows").glob("*.md")) == ["1.md", "2.md", "dash.md"]
    assert sorted(p.name for p in (r / "sections").glob("*.md")) == ["a-bundle.md", "item-2.md", "items-3-and-4.md"]
    a = docs_repo / "docs/agents"
    assert sorted(p.name for p in (a / "sessions").glob("*.md")) == ["phase-10b.md", "phase-11.md"]
    assert sorted(p.name for p in (a / "history").glob("*.md")) == ["2026-10-07-architecture-phase.md",
                                                                    "2026-10-08-phase-4.md"]
    assert (a / "_middle.md").read_text().startswith("### Phase 10b: details")  # blank line stays with the bullet
    assert _gd(docs_repo, "--check") == 0
    assert _gd(docs_repo, "--split", "decisions") == 2  # already split
    assert "already split" in capsys.readouterr().out


def test_blocks_and_amendments_are_named_after_what_they_are() -> None:
    """A block bullet (``D-a..D-b``, ``–``, ``to``) must not take ``D-a.md`` from the real ``D-a`` that follows it, and
    amendments are named, not numbered by position (both seen on main, 2026-10-22)."""
    text = ("# Brief\n\n"
            "- **D-390..D-399 (2026-10-14, GUI research):** the block.\n"
            "- **D-390 (2026-10-14, toolkit).** First of the block.\n"
            "- **D-670–D-679 (2026-10-22, defences):** another block.\n"
            "- **D-660 to D-669 (2026-10-22, Inspect):** a third.\n"
            "- **D-621 (2026-10-22, binding checks).** The decision.\n"
            "- **D-621 amendment (2026-10-22, minors).** One.\n"
            "- **D-621 amendment 2 (2026-10-22, V-2).** Two.\n"
            "- **D-31 addendum (2026-10-14, bumps).** A.\n"
            "- **D-31 addendum (2026-10-22, aprov).** B.\n")
    (_preamble, (_part, items)) = gd.split_decisions(text)
    assert [name for name, _body in items] == [
        "D-390-D-399.md", "D-390.md", "D-670-D-679.md", "D-660-D-669.md", "D-621.md", "D-621-amendment.md",
        "D-621-amendment-2.md", "D-31-addendum.md", "D-31-addendum-2.md"]


def test_split_refuses_a_file_it_cannot_reproduce(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(docs_repo, "docs/architecture/DECISIONS.md", DECISIONS + "## A heading after the entries\n")
    assert _gd(docs_repo, "--split", "decisions") == 2
    assert "is neither an entry nor inside one" in capsys.readouterr().out
    assert not (docs_repo / "docs/architecture/decisions").exists()


def test_a_status_edit_keeps_the_file_name(docs_repo: Path) -> None:
    edited = REGEN.replace("## Item 2 (planned, 2026-10-12)", "## Item 2 (implemented, 2026-10-14)")
    segments = gd.split_regen_batch(edited)
    names = [n for n, _t in segments[3][1]]
    assert names == ["item-2.md", "items-3-and-4.md", "a-bundle.md"]


def test_new_entries_regenerate_after_legacy_in_number_order(docs_repo: Path,
                                                             capsys: pytest.CaptureFixture[str]) -> None:
    assert _gd(docs_repo, "--split", "decisions") == 0
    commit(docs_repo, "migrate decisions")
    d = docs_repo / "docs/architecture/decisions"
    write(d, "D-12.md", "- **D-12 (2026-10-14, z).** Twelfth.\n")
    write(d, "D-10.md", "- **D-10 (2026-10-14, z).** Tenth.\n")
    capsys.readouterr()
    assert _gd(docs_repo, "--check", "decisions") == 1
    assert "is stale" in capsys.readouterr().out
    assert _gd(docs_repo, "--write", "decisions") == 0
    text = (docs_repo / "docs/architecture/DECISIONS.md").read_text()
    assert text == DECISIONS + "- **D-10 (2026-10-14, z).** Tenth.\n- **D-12 (2026-10-14, z).** Twelfth.\n"
    (d / "D-2.md").unlink()
    assert _gd(docs_repo, "--write", "decisions") == 2
    assert "legacy fragment(s) missing: D-2.md" in capsys.readouterr().out


def test_two_branches_adding_entries_resolve_by_regenerating(docs_repo: Path) -> None:
    assert _gd(docs_repo, "--split", "decisions") == 0
    commit(docs_repo, "migrate")
    d = Path("docs/architecture/decisions")
    git(docs_repo, "switch", "-q", "-c", "a")
    write(docs_repo, str(d / "D-10.md"), "- **D-10.** A.\n")
    assert _gd(docs_repo, "--write", "decisions") == 0
    commit(docs_repo, "a adds D-10")
    git(docs_repo, "switch", "-q", "-c", "b", "main")
    write(docs_repo, str(d / "D-20.md"), "- **D-20.** B.\n")
    assert _gd(docs_repo, "--write", "decisions") == 0
    commit(docs_repo, "b adds D-20")
    merge = subprocess.run(["git", "merge", "-q", "--no-edit", "a"], cwd=docs_repo, capture_output=True, text=True)
    assert merge.returncode != 0 and "DECISIONS.md" in git(docs_repo, "diff", "--name-only", "--diff-filter=U")
    assert _gd(docs_repo, "--write", "decisions") == 0  # the documented resolution: regenerate, never hand-merge
    git(docs_repo, "add", "-A")
    git(docs_repo, "commit", "-q", "--no-edit")
    assert (docs_repo / "docs/architecture/DECISIONS.md").read_text().endswith("- **D-10.** A.\n- **D-20.** B.\n")
    assert _gd(docs_repo, "--check") == 0


def test_adopt_moves_a_pre_migration_branch_into_fragments(docs_repo: Path,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    git(docs_repo, "switch", "-q", "-c", "old-branch")  # started before the migration, edits the file directly
    write(docs_repo, "docs/architecture/DECISIONS.md",
          DECISIONS.replace("Second, proposed.", "Second, user-approved.") + "- **D-30 (2026-10-14).** New.\n")
    write(docs_repo, "AGENTS.md", AGENTS.replace("- **Phase 11** (finished): corpus.",
                                                 "- **Phase 11** (finished, merged): corpus.\n"
                                                 "- **Workflow tools** (branch `workflow-tools`): tools."))
    commit(docs_repo, "direct edits")
    git(docs_repo, "switch", "-q", "main")
    assert _gd(docs_repo, "--split", "decisions", "agents") == 0
    commit(docs_repo, "migrate")
    git(docs_repo, "switch", "-q", "old-branch")
    git(docs_repo, "merge", "-q", "--no-edit", "main")  # clean: the migration did not change the generated bytes
    assert _gd(docs_repo, "--check") == 1
    capsys.readouterr()
    assert _gd(docs_repo, "--adopt", "decisions", "agents") == 0
    out = capsys.readouterr().out
    assert "wrote docs/architecture/decisions/D-2.md" in out and "wrote docs/architecture/decisions/D-30.md" in out
    assert "wrote docs/agents/sessions/phase-11.md" in out and "wrote docs/agents/sessions/workflow-tools.md" in out
    assert _gd(docs_repo, "--check") == 0
    assert "user-approved" in (docs_repo / "docs/architecture/decisions/D-2.md").read_text()


def test_adopt_reports_entries_missing_from_the_file(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _gd(docs_repo, "--split", "decisions") == 0
    write(docs_repo, "docs/architecture/DECISIONS.md", DECISIONS.replace("- **D-1 (U-15).** First.\n", ""))
    capsys.readouterr()
    assert _gd(docs_repo, "--adopt", "decisions") == 0
    assert "D-1.md has no entry" in capsys.readouterr().out
    assert (docs_repo / "docs/architecture/decisions/D-1.md").is_file()  # never deleted


@pytest.mark.parametrize("rel", ["docs/architecture/DECISIONS.md", "docs/reports/analysis/regen-batch.md", "AGENTS.md"])
def test_todays_files_split_byte_identically(rel: str, tmp_path: Path) -> None:
    """Migration readiness: a copy of today's file splits into fragments that regenerate it byte for byte."""
    target = next(t for t in gd.TARGETS.values() if t.path == rel)
    if (REPO / target.directory).exists():
        pytest.skip(f"{target.name} is already migrated (tests/repo checks the generated file)")
    if gd.left_out(REPO, target):
        pytest.skip(f"{rel} is not in this tree (the public export leaves it out, D-1004)")
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / rel, tmp_path / rel)
    assert gd.split(tmp_path, target) > 0
    assert gd.generate(tmp_path, target).encode("utf-8") == (REPO / rel).read_bytes()


def _post_split_branch(docs_repo: Path) -> None:
    """``main`` is split and has an entry written by hand under its own file name; the branch starts after that."""
    assert _gd(docs_repo, "--split", "decisions", "agents") == 0
    write(docs_repo, "docs/agents/sessions/my-session-entry.md", "- **Workflow tools** (branch `wt`): tools.\n")
    assert _gd(docs_repo, "--write", "agents") == 0
    commit(docs_repo, "migrate, plus a hand-named session entry")
    git(docs_repo, "switch", "-q", "-c", "new-branch")


def test_adopt_refuses_a_branch_started_after_the_split(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """2026-10-23: --adopt on a post-split branch wrote a second fragment for every hand-named entry (the split
    derives ``workflow-tools.md`` for ``my-session-entry.md``), so each appeared twice."""
    _post_split_branch(docs_repo)
    write(docs_repo, "AGENTS.md", (docs_repo / "AGENTS.md").read_text().replace("tools.\n", "tools, merged.\n"))
    commit(docs_repo, "a direct edit")
    before = git(docs_repo, "status", "--porcelain")
    capsys.readouterr()
    assert _gd(docs_repo, "--adopt", "agents") == 2
    out = capsys.readouterr().out
    assert "refused: HEAD started after the split" in out and "--write" in out
    assert git(docs_repo, "status", "--porcelain") == before  # nothing written
    assert not (docs_repo / "docs/agents/sessions/workflow-tools.md").exists()
    git(docs_repo, "merge", "-q", "--no-edit", "main")  # merging main does not move the fork point
    assert _gd(docs_repo, "--adopt", "agents") == 2
    assert _gd(docs_repo, "--adopt", "--base", "no-such-ref", "agents") == 2
    assert "cannot tell where 'HEAD' left" in capsys.readouterr().out


def test_adopt_never_writes_an_entry_twice(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Where --adopt may run, an entry whose text already is a fragment under another name is skipped, not
    duplicated, and that fragment is not reported missing."""
    _post_split_branch(docs_repo)
    capsys.readouterr()
    assert _gd(docs_repo, "--adopt", "--base", "HEAD~1", "agents") == 0  # pretend the branch predates the split
    out = capsys.readouterr().out
    assert "not written: docs/agents/sessions/workflow-tools.md (same text as docs/agents/sessions/" \
           "my-session-entry.md)" in out
    assert "has no entry" not in out and not (docs_repo / "docs/agents/sessions/workflow-tools.md").exists()
    assert _gd(docs_repo, "--check") == 0


def test_adopt_on_a_train_names_the_merged_branch(docs_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The merge train runs --adopt on its own post-split branch after merging a pre-split one: ``--branch`` names
    the merged branch, whose fork point decides."""
    git(docs_repo, "switch", "-q", "-c", "old-branch")
    write(docs_repo, "docs/architecture/DECISIONS.md", DECISIONS + "- **D-30 (2026-10-14).** New.\n")
    commit(docs_repo, "a direct edit before the split")
    git(docs_repo, "switch", "-q", "main")
    _post_split_branch(docs_repo)  # the train branch "new-branch"
    git(docs_repo, "merge", "-q", "--no-edit", "old-branch")
    capsys.readouterr()
    assert _gd(docs_repo, "--adopt", "decisions") == 2  # the train's own HEAD started after the split
    assert _gd(docs_repo, "--adopt", "--branch", "old-branch", "decisions") == 0
    assert "wrote docs/architecture/decisions/D-30.md" in capsys.readouterr().out


PARTS = 'width = 2\ndirectory = "decision-log"\ntitle = "Decisions D-{lo}–D-{hi}"\nlabel = "D-{lo}–D-{hi}"\n'


def _parts_repo(docs_repo: Path) -> Path:
    """``decisions`` split, then generated as an index plus parts of two numbers each (D-1003)."""
    assert _gd(docs_repo, "--split", "decisions") == 0
    write(docs_repo, "docs/architecture/decisions/_parts.toml", PARTS)
    assert _gd(docs_repo, "--write", "decisions") == 0
    commit(docs_repo, "decisions in parts")
    return docs_repo / "docs/architecture"


def _entries(part: Path) -> str:
    return part.read_text().split(gd.ENTRIES_MARK + "\n", 1)[1]


def test_parts_hold_the_entries_by_number_range_in_their_order(docs_repo: Path,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    arch = _parts_repo(docs_repo)
    log = arch / "decision-log"
    assert sorted(p.name for p in log.glob("*.md")) == [
        "DECISIONS-0000-0001.md", "DECISIONS-0002-0003.md", "DECISIONS-0004-0005.md"]
    assert _entries(log / "DECISIONS-0000-0001.md") == "- **D-1 (U-15).** First.\n"
    assert _entries(log / "DECISIONS-0002-0003.md") == (  # the file's order, not the number order
        "- **D-3 (2026-10-08, x).** Third, placed before D-2 on purpose.\n  - Rejected: nothing.\n"
        "- **D-2 (2026-10-08, y).** Second, proposed.\n- **D-3 addendum (2026-10-09).** A top-level addendum.\n")
    assert _entries(log / "DECISIONS-0004-0005.md") == "- D-4–D-5 are reserved.\n"
    assert "# Decisions D-2–D-3" in (log / "DECISIONS-0002-0003.md").read_text()
    index = (arch / "DECISIONS.md").read_text()
    assert index.startswith(DECISIONS[:DECISIONS.index("- **D-1")]) and "**D-1 (U-15)" not in index
    assert "| [DECISIONS-0002-0003.md](decision-log/DECISIONS-0002-0003.md) | D-2–D-3 | 3 |" in index
    assert gd.read_generated(docs_repo, gd.TARGETS["decisions"]) == (
        DECISIONS[:DECISIONS.index("- **D-1")] + "".join(_entries(p) for p in sorted(log.glob("*.md"))))
    capsys.readouterr()
    assert _gd(docs_repo, "--check") == 0
    write(arch, "decisions/D-10.md", "- **D-10 (2026-10-30).** Tenth.\n")
    assert _gd(docs_repo, "--check", "decisions") == 1
    out = capsys.readouterr().out
    assert "DECISIONS-0010-0011.md is stale" in out and "DECISIONS.md is stale" in out
    assert _gd(docs_repo, "--write", "decisions") == 0
    assert _entries(log / "DECISIONS-0010-0011.md") == "- **D-10 (2026-10-30).** Tenth.\n"
    assert _gd(docs_repo, "--check") == 0


def test_a_part_no_longer_generated_fails_the_check_and_write_removes_it(docs_repo: Path,
                                                                         capsys: pytest.CaptureFixture[str]) -> None:
    arch = _parts_repo(docs_repo)
    write(arch, "decisions/_parts.toml", PARTS.replace("width = 2", "width = 10"))
    capsys.readouterr()
    assert _gd(docs_repo, "--check", "decisions") == 1
    assert "DECISIONS-0002-0003.md is no longer generated" in capsys.readouterr().out
    assert _gd(docs_repo, "--write", "decisions") == 0
    assert sorted(p.name for p in (arch / "decision-log").glob("*.md")) == ["DECISIONS-0000-0009.md"]
    assert _gd(docs_repo, "--check") == 0


def test_adopt_reads_the_index_and_parts_back(docs_repo: Path) -> None:
    arch = _parts_repo(docs_repo)
    part = arch / "decision-log/DECISIONS-0002-0003.md"
    part.write_text(part.read_text().replace("Second, proposed.", "Second, user-approved."))
    written, absent, same = gd.adopt(docs_repo, gd.TARGETS["decisions"])
    assert written == ["docs/architecture/decisions/D-2.md"] and absent == [] and same == []
    assert "user-approved" in (arch / "decisions/D-2.md").read_text()


def test_the_decisions_parts_stay_well_under_the_repository_limit() -> None:
    """D-1003: no generated decisions file nears tests/repo's 1 MiB cap."""
    files = gd.generate_files(REPO, gd.TARGETS["decisions"])
    assert len(files) > 1 and max(len(t.encode("utf-8")) for t in files.values()) < (1 << 20) // 2
