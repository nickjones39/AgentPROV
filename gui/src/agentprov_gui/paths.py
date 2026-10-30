"""Where the GUI keeps its own state (design §4.1, §16 question 2: inside ``AGENTPROV_HOME``). No Qt here.

The GUI writes only below ``$AGENTPROV_HOME/gui/`` (its jobs, batches, caches, lock and log). It never writes into a
corpus, a raw store or the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["agentprov_home", "default_corpus_roots", "gui_dir", "layout_cache_dir", "scratch_root"]


def agentprov_home(environ: dict[str, str] | None = None) -> Path:
    """``$AGENTPROV_HOME``, else ``~/.agentprov``, absolute and ``~``-expanded (the CLI's rule for its live workers,
    ``cli/live/envs.agentprov_home``: a job's CLI runs with its cwd in the job directory)."""
    env = os.environ if environ is None else environ
    raw = env.get("AGENTPROV_HOME")
    return Path(os.path.abspath(Path(raw).expanduser() if raw else Path.home() / ".agentprov"))


def gui_dir(home: Path | None = None) -> Path:
    return (home or agentprov_home()) / "gui"


def layout_cache_dir(home: Path | None = None) -> Path:
    return gui_dir(home) / "cache" / "layout"


def default_corpus_roots(home: Path | None = None) -> list[Path]:
    return [(home or agentprov_home()) / "corpora"]


def scratch_root(home: Path | None = None) -> Path:
    """Scratch corpora for dev jobs (design §8.4): ``~/.agentprov/migration-work``."""
    return (home or agentprov_home()) / "migration-work"
