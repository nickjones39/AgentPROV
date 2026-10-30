"""What a branch changed, for the "new family touches only the family" guards (invariant 5; D.12.3 and its analogues).

Each family's ``test_new_family_no_core_change.py`` compares the branch with the base it started from. The base is the
merge base of ``HEAD`` with ``origin/main`` and with the local ``main``, whichever is newer. A worktree's local ``main`` is
often stale: after the branch merges ``origin/main``, a merge base taken with the stale ``main`` would count every
commit merged from ``origin/main`` as the branch's own and flag main's own files as core changes. A local ``main`` ahead
of ``origin/main`` (merged but not yet pushed) is used when it is the newer one. Without either ref, or without git, the
guard is skipped with the reason.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

#: Tried in this order; the newest merge base wins, and ``origin/main`` breaks a tie between unrelated bases.
BASE_REFS = ("origin/main", "main")


def _git(repo: Path, *args: str) -> str | None:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def merge_base(repo: Path) -> tuple[str | None, str]:
    """The base commit and how it was chosen, or ``(None, reason)``."""
    if shutil.which("git") is None:
        return None, "git is not installed"
    if _git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        return None, f"{repo} is not a git checkout"
    bases: list[tuple[str, str]] = []
    for ref in BASE_REFS:
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
            continue
        base = _git(repo, "merge-base", "HEAD", ref)
        if base:
            bases.append((ref, base))
    if not bases:
        return None, f"no {' or '.join(BASE_REFS)} to diff against (or no shared history with HEAD)"
    for ref, base in bases:
        if all(_git(repo, "merge-base", "--is-ancestor", other, base) is not None for _r, other in bases):
            return base, f"merge base with {ref}"
    ref, base = bases[0]
    return base, f"merge base with {ref}"


def branch_changes(repo: Path) -> tuple[set[str] | None, str]:
    """The files the branch changed since its base (tracked diffs plus untracked, not ignored), or ``(None, reason)``."""
    base, how = merge_base(repo)
    if base is None:
        return None, how
    changed = set((_git(repo, "diff", "--name-only", base) or "").split())
    changed |= set((_git(repo, "ls-files", "--others", "--exclude-standard") or "").split())
    return changed, how


def changed_or_skip(repo: Path) -> set[str]:
    """:func:`branch_changes`, skipping the calling test with the reason when there is nothing to compare with."""
    changed, how = branch_changes(repo)
    if changed is None:
        pytest.skip(f"the new-family guard needs a base to compare with: {how}")
    return changed
