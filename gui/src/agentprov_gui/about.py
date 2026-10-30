"""The facts of the About window (design §6.8; D-399). No Qt here.

The commit comes from ``git rev-parse HEAD`` of the configured checkout, through the same hardening as the CLI's
``cli/package._git`` (no optional locks, no prompt, no pager, no fsmonitor, ``LC_ALL=C``, a timeout) and with the
GUI's environment allowlist (no inherited ``GIT_*``, ``*_API_KEY`` or ``UV_*``); "(modified)" is added when ``git
status --porcelain`` is not empty. The repository is shown as text, never as a link.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agentprov import versions

from agentprov_gui import __version__
from agentprov_gui.jobs.manager import allowlisted_env

__all__ = ["NOTICES", "REPOSITORY", "AboutFacts", "about_facts", "default_checkout", "git_commit"]

REPOSITORY: Final = "nickjones39/AgentPROV"
AUTHOR: Final = "Nicholas Jones"
LICENCE: Final = "MIT, free to use"
PURPOSE: Final = "Developed as part of PhD research."
NOTICES: Final = (
    "Qt 6 and PySide6 (Qt for Python): GNU LGPL v3. Qt is linked dynamically; the shared libraries are separate files "
    "and can be replaced with modified versions of the same release. The corresponding source of Qt and PySide6 is "
    "available from The Qt Company's download archive for the exact versions shown here; a written offer is in "
    "THIRD_PARTY_NOTICES.md.\n"
    "psutil: BSD 3-Clause.\n"
    "Graphviz (dot): Eclipse Public License 1.0. Not bundled; the system installation is used for graph layout."
)
_HEX40: Final = re.compile(r"[0-9a-f]{40}")


def _git(repo: Path, *args: str) -> str | None:
    executable = shutil.which("git")
    if executable is None:
        return None
    env = {**allowlisted_env(), "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"}
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, resolved executable
            [executable, "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
            capture_output=True, env=env, check=False, timeout=20, stdin=subprocess.DEVNULL,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None


def git_commit(repo: Path) -> str:
    """``<40 hex>`` with `` (modified)`` for a dirty tree, or ``not available``."""
    head = _git(repo, "rev-parse", "HEAD")
    commit = head.strip() if head else ""
    if not _HEX40.fullmatch(commit):
        return "not available"
    status = _git(repo, "status", "--porcelain")
    return commit + (" (modified)" if status is None or status.strip() else "")


def checkout_identity(repo: Path) -> dict[str, str]:
    """GR-70: what a batch pins: the checkout's resolved path, its commit (with " (modified)" for a dirty tree) and the
    sha256 of ``git diff HEAD`` (so a dirty tree that changes again is caught; untracked files are not covered)."""
    import hashlib

    diff = _git(repo, "diff", "HEAD") or ""
    return {"checkout": str(repo.resolve()), "commit": git_commit(repo),
            "diff": hashlib.sha256(diff.encode("utf-8", "surrogateescape")).hexdigest()}


def default_checkout() -> Path | None:
    """The checkout this GUI runs from (``gui/`` sits inside it), when it is a git checkout with a CLI."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "agentprov").is_dir():
            return parent
    return None


@dataclass(frozen=True, slots=True)
class AboutFacts:
    gui_version: str
    core_version: str
    formats: tuple[tuple[str, str], ...]
    commit: str
    qt_version: str
    pyside_version: str


def about_facts(checkout: Path | None, qt_version: str, pyside_version: str) -> AboutFacts:
    formats = tuple((k, v) for k, v in versions.VERSIONS.items() if k != "software")
    formats += (("progress", "agentprov-progress/0.1"),)
    commit = git_commit(checkout) if checkout is not None else "not available"
    return AboutFacts(__version__, versions.__version__, formats, commit, qt_version, pyside_version)
