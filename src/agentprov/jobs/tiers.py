"""Job tiers (GUI design §8.4, research §Q7; in the core since D-704). Pure: no I/O.

* **R0**: reads only (no lock, nothing written outside the job directory);
* **R1**: writes local state (a corpus, a report, a setting);
* **R2**: reaches the network, costs money or consents to a run (an R2 flag below), and is confirmed every time.

A job's tier is its command's base tier raised by its flags. ``purge`` (without ``--dry-run``) is **destructive**:
never batched, and the GUI asks for its typed confirmation first.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

__all__ = ["DESTRUCTIVE", "R2_FLAGS", "REPO_COMMANDS", "TIERS", "base_tier", "is_destructive", "split_index",
           "tier_of_argv"]

TIERS: Final = ("R0", "R1", "R2")
#: Flags that reach the network, cost money or consent to a run (the GUI's list until D-704).
R2_FLAGS: Final = ("--allow-network", "--fetch", "--i-consent-to-large-download", "--i-consent-to-api-costs",
                   "--env-stdin", "--keychain", "--i-consent-to-local-run", "--max-calls", "--max-cost-usd",
                   "--price-in", "--price-out", "--confirm-r2")
#: Commands (by their first one or two words) whose base tier is R0 (read-only) or R2 (network by definition).
_R0: Final = frozenset({"info", "sources", "validate", "inspect", "stats", "verify", "estimate", "models",
                        "prices list", "prices get", "settings list", "settings get", "keys list", "keys status",
                        "jobs list", "jobs show", "jobs follow", "batch list", "batch show"})
_R2: Final = frozenset({"fetch", "prices refresh"})
DESTRUCTIVE: Final = frozenset({"purge"})
#: Commands that find the repository from their cwd (``cli/live/envs.repository_root``, M.4): they start in the
#: checkout, not in the job directory.
REPO_COMMANDS: Final = frozenset({"run", "backends", "migrate"})
#: Commands whose second word is a subcommand (the job's global options go after both words).
_TWO_WORDS: Final = frozenset({"backends", "migrate", "prices", "settings", "keys", "jobs", "batch"})


def split_index(argv: Sequence[str]) -> int:
    """How many leading words name the command (global options go right after them)."""
    if argv[:1] and argv[0] in _TWO_WORDS and len(argv) > 1 and not argv[1].startswith("-"):
        return 2
    return 1


def _words(argv: Sequence[str]) -> str:
    return " ".join(argv[: split_index(argv)])


def _is_r2(name: str) -> bool:
    """GR-45: an R2 flag, or a prefix of one that an argparse allowing abbreviations expands to it."""
    return name in R2_FLAGS or (name.startswith("--") and len(name) > 2 and any(f.startswith(name) for f in R2_FLAGS))


def base_tier(argv: Sequence[str]) -> str:
    words = _words(argv)
    if words in _R2 or (argv[:1] and argv[0] in _R2):
        return "R2"
    if words in _R0 or (argv[:1] and argv[0] in _R0):
        return "R0"
    return "R1"


def tier_of_argv(argv: Sequence[str], base: str | None = None) -> str:
    """The tier of a subcommand argv: its base tier (or ``base``), raised by every R2 flag; ``--out``, ``--report``,
    ``--break-stale-lock`` and ``--yes`` make an R0 command R1; a dry run without an R2 flag is R0 (it takes no lock)."""
    tier = base or base_tier(argv)
    for token in argv:
        name = token.split("=", 1)[0]
        if _is_r2(name):
            tier = "R2"
        elif name in ("--out", "--report", "--break-stale-lock", "--yes") and tier == "R0":
            tier = "R1"
    if "--dry-run" in argv and tier == "R1" and not any(_is_r2(t.split("=", 1)[0]) for t in argv):
        tier = "R0"
    return tier


def is_destructive(argv: Sequence[str]) -> bool:
    return bool(argv[:1]) and argv[0] in DESTRUCTIVE and "--dry-run" not in argv
