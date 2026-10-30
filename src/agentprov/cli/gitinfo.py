"""The checkout the running AgentPROV code comes from: its commit and cleanliness (HL H.2.7; D-780).

``corpus/`` and the runner run no subprocess, so the CLI computes these facts and passes them in: the sealing commit to
:func:`agentprov.corpus.package.seal` (``ProducerFacts``) and the building commit to
:class:`agentprov.corpus.writer.CorpusWriter` (``BuildStep``). Both read the agentprov **source root** (``REPO_ROOT``),
never the current directory, through the absolute ``git`` path with ``--no-optional-locks``, no prompt, no pager and
no fsmonitor. Nothing in the environment can name a commit: the value is what ``git`` reports for that checkout.

Not every install is a checkout. From a wheel the source root is wherever site-packages sits, and ``git -C`` there would
find an *enclosing* repository (a virtual environment inside a project) and report its HEAD. The commit is therefore
taken only when ``git rev-parse --show-toplevel`` is the source root itself and the package source is there; otherwise
the answer is ``not_a_source_checkout``, never another repository's commit.
"""

from __future__ import annotations

import functools
import hashlib
import os
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Final

from agentprov import __version__
from agentprov.corpus.buildstep import BuildStep

__all__ = ["REPO_ROOT", "build_step", "checkout_state", "distributions_sha256", "git_facts"]

REPO_ROOT: Final = Path(__file__).resolve().parents[3]


def _git(repo: Path, *args: str) -> str | None:
    executable = shutil.which("git")
    if executable is None:
        return None
    # no GIT_* variable of the caller reaches git (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE ... would name another repository
    # or index): the answer is about the checkout at ``repo`` and nothing else
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
           "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"}
    try:
        done = subprocess.run([executable, "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo),
                               *args], capture_output=True, env=env, check=False, timeout=120)  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None


def _is_checkout_root(repo: Path) -> bool:
    top = _git(repo, "rev-parse", "--show-toplevel")
    if top is None or not (repo / "src" / "agentprov" / "__init__.py").is_file():
        return False
    try:
        return Path(top.strip()).resolve() == repo.resolve()
    except OSError:
        return False


def checkout_state(repo: Path = REPO_ROOT) -> tuple[str | None, bool, str | None]:
    """``(commit, clean, absent_reason)`` of the checkout at ``repo``: a commit and its cleanliness, or ``(None, False,
    reason)`` with the reason one of ``git_unavailable``, ``not_a_source_checkout`` and ``git_failed``."""
    if shutil.which("git") is None:
        return None, False, "git_unavailable"
    if not _is_checkout_root(repo):
        return None, False, "not_a_source_checkout"
    head = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain")
    commit = head.strip() if head is not None and len(head.strip()) == 40 else None
    if commit is None or status is None:
        return None, False, "git_failed"
    return commit, status.strip() == "", None


def git_facts(repo: Path = REPO_ROOT) -> tuple[str | None, bool]:
    """``(commit, clean)`` of the AgentPROV checkout that runs the command (H.2.7); ``(None, False)`` when unknown."""
    commit, clean, _reason = checkout_state(repo)
    return commit, clean


def distributions_sha256() -> str:
    """``sha256:`` of the sorted ``name==version\\n`` lines of the installed distributions (H.2.7)."""
    lines = sorted({f"{d.metadata['Name']}=={d.version}\n" for d in metadata.distributions() if d.metadata["Name"]})
    return "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


@functools.cache
def _facts() -> tuple[str | None, bool, str | None, str | None]:
    commit, clean, reason = checkout_state()
    return commit, clean, reason, None if commit is not None else distributions_sha256()


def build_step(command: str) -> BuildStep:
    """The record of this process as the builder of a corpus (``command``: import, run, derive or recompute). The git
    facts are read once per process, before the command writes anything."""
    commit, clean, reason, digest = _facts()
    if commit is not None:
        return BuildStep(command, __version__, git_commit=commit, git_tree_clean=clean)
    return BuildStep(command, __version__, git_commit_absent_reason=reason, distributions_sha256=digest)
