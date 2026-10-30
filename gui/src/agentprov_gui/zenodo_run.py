"""The draft-only Zenodo uploader run from the GUI (D-880): its argv, the collection plan and a pseudo-terminal. No Qt.

The uploader is ``agentprov_zenodo`` (``zenodo/``, the ``agentprov-zenodo`` distribution), run with the checkout's own
interpreter as ``python -I -m agentprov_zenodo``: it is not an ``agentprov`` command (D-790) and the GUI never imports
it. Consent stays D-790's: the uploader needs a terminal and a typed phrase naming the host, so the GUI runs it under a
**pseudo-terminal** and the user types each phrase in the dialog's terminal pane (the user's choice, 2026-10-28). The GUI
never holds the token: every run passes ``--keychain``, so the uploader reads ``ZENODO_SANDBOX_TOKEN`` or
``ZENODO_TOKEN`` through the core's keychain helper (D-702), and the child's environment is the GUI's allowlist
(:func:`agentprov_gui.jobs.manager.allowlisted_env`), which carries no token. Nothing here can publish: the uploader's
request allowlist has no publish request.

POSIX only (``os.openpty``): macOS and Linux. :func:`available` is false elsewhere and the action is disabled.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["MODULE", "TARGETS", "Deposit", "PtyRun", "available", "is_index_deposit", "parse_deposits", "plan_steps",
           "receipt_path"]

MODULE: Final = "agentprov_zenodo"
#: target name -> host, as the uploader's ``TARGETS``
TARGETS: Final[Mapping[str, str]] = {"sandbox": "sandbox.zenodo.org", "production": "zenodo.org"}
_ROOT: Final = re.compile(r"sha256:[0-9a-f]{64}")
#: ``agentprov.release.index.INDEX_MANIFEST_FORMAT`` (the GUI imports no ``agentprov.release``; a test pins them equal)
INDEX_MANIFEST_FORMAT: Final = "agentprov-index-manifest/0.1"
_COMMUNITY: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")
_READ: Final = 65536
_RECEIPT_LIMITS: Final = IngestLimits()


def available() -> bool:
    """Whether a pseudo-terminal can be opened here (POSIX)."""
    return hasattr(os, "openpty") and os.name == "posix"


@dataclass(frozen=True)
class Deposit:
    directory: Path
    roots: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    """One uploader run: its arguments (after ``python -I -m agentprov_zenodo``) and what it does, for the screen."""

    args: tuple[str, ...]
    what: str


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def is_index_deposit(directory: Path) -> bool:
    """Whether ``directory`` holds an index-only umbrella (``package --index``, D-947): its ``DEPOSIT-MANIFEST.json``
    (local JSON, read strictly, as data) has the index format and kind. The uploader checks the rest."""
    try:
        doc = strict_json_loads((directory / "DEPOSIT-MANIFEST.json").read_bytes(), _RECEIPT_LIMITS)
    except (OSError, AgentProvError):
        return False
    return isinstance(doc, dict) and doc.get("format") == INDEX_MANIFEST_FORMAT and doc.get("kind") == "index"


def parse_deposits(text: str) -> list[Deposit]:
    """One deposit per line, ``DEPOSIT_DIR sha256:ROOT [sha256:ROOT ...]`` (a path without spaces); the first is the
    umbrella. An index-only umbrella (D-947) holds no corpus, so the first line names it alone, with no root digest.
    :class:`ValueError` with the line's number for anything else."""
    out: list[Deposit] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        parts = raw.split()
        if not parts:
            continue
        roots = tuple(parts[1:])
        directory = Path(parts[0]).expanduser()
        if not out and is_index_deposit(directory):
            if roots:
                raise ValueError(f"line {number}: an index deposit holds no corpus; give it no root digest")
            out.append(Deposit(directory, ()))
            continue
        if not roots or any(_ROOT.fullmatch(r) is None for r in roots):
            raise ValueError(f"line {number}: DEPOSIT_DIR followed by at least one sha256:<64 hex> root digest (only an "
                             "index umbrella, on the first line, takes none)")
        out.append(Deposit(directory, roots))
    if len({d.directory.resolve() for d in out}) != len(out):
        raise ValueError("a deposit directory is listed twice")
    return out


def parse_communities(text: str) -> list[str]:
    slugs = [s for s in text.replace(",", " ").split() if s]
    bad = [s for s in slugs if _COMMUNITY.fullmatch(s) is None]
    if bad:
        raise ValueError(f"not a Zenodo community identifier: {bad[0][:40]!r}")
    return slugs


def receipt_path(directory: Path, target: str) -> Path:
    """Where the uploader writes the draft's receipt: beside the deposit directory (``receipt_path`` of the tool)."""
    return directory.parent / f"{directory.name}.zenodo-{target}-draft-receipt.json"


def _status(path: Path) -> str | None:
    """The receipt's ``status`` (local JSON the uploader wrote; read strictly, as data), or ``None`` without one."""
    try:
        doc = strict_json_loads(path.read_bytes(), _RECEIPT_LIMITS)
    except FileNotFoundError:
        return None
    except (OSError, AgentProvError):  # shown as such; the uploader decides what to do with it
        return "unreadable"
    status = doc.get("status") if isinstance(doc, dict) else None
    return status if isinstance(status, str) else "unknown"


def plan_steps(deposits: Sequence[Deposit], target: str, communities: Sequence[str]) -> Plan:
    """The uploader runs for a collection: a create per deposit without a receipt (``--resume`` for one that is not
    ``complete``; nothing for a complete one), then ``--cross-link`` with the first as the umbrella when there are two or
    more. Every run passes ``--keychain``; none can publish."""
    if target not in TARGETS:
        raise ValueError(f"target is one of {', '.join(TARGETS)}")
    plan = Plan()
    community = [a for slug in communities for a in ("--community", slug)]
    for d in deposits:
        roots = [a for r in d.roots for a in ("--root-digest", r)]
        status = _status(receipt_path(d.directory, target))
        base = (str(d.directory), "--target", target, "--create-draft", "--keychain", *community, *roots)
        if status is None:
            plan.steps.append(Step(base, f"create an unpublished draft of {d.directory}"))
        elif status == "complete":
            plan.notes.append(f"{d.directory}: its draft is complete (receipt status complete); not created again")
        else:
            plan.steps.append(Step((*base, "--resume"), f"resume the draft of {d.directory} (receipt status "
                                                        f"{status[:40]})"))
    if len(deposits) >= 2:
        receipts = [str(receipt_path(d.directory, target)) for d in deposits]
        members = [a for r in receipts[1:] for a in ("--member", r)]
        plan.steps.append(Step(("--target", target, "--cross-link", "--keychain", "--umbrella", receipts[0], *members),
                               f"cross-link {len(deposits)} drafts (umbrella: {deposits[0].directory})"))
    return plan


class PtyRun:
    """``argv`` under a pseudo-terminal: its stdin, stdout and stderr are the terminal, so the uploader's confirmation
    (a terminal and a typed phrase) is a person typing in the GUI's terminal pane. Output is read without blocking."""

    def __init__(self, argv: Sequence[str], env: Mapping[str, str], cwd: Path | None = None) -> None:
        master, slave = os.openpty()
        try:
            self.proc = subprocess.Popen(  # noqa: S603 - the checkout's interpreter and the uploader's own options
                list(argv), stdin=slave, stdout=slave, stderr=slave, env=dict(env), cwd=cwd,
                start_new_session=True, close_fds=True)
        except OSError:
            os.close(master)
            os.close(slave)
            raise
        os.set_blocking(master, False)
        self._master: int | None = master
        # held until close(): on macOS the last close of the slave discards output not yet read, so a program that
        # prints and exits at once (the uploader's last lines) would lose them
        self._slave: int | None = slave

    def read(self) -> str:
        """What the program wrote since the last read (``""`` when nothing; ``\\r`` removed)."""
        if self._master is None:
            return ""
        chunks: list[bytes] = []
        while True:
            try:
                chunk = os.read(self._master, _READ)
            except BlockingIOError:
                break
            except OSError:  # EIO on Linux once the program has closed the terminal
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", "replace").replace("\r", "")

    def send_line(self, text: str) -> None:
        """One typed line (no control character), as if typed at the terminal."""
        if self._master is None or self.proc.poll() is not None:
            return
        line = "".join(c for c in text if c.isprintable())[:500]
        os.write(self._master, (line + "\n").encode("utf-8"))

    def poll(self) -> int | None:
        return self.proc.poll()

    def stop(self) -> None:
        """Ask the program to stop (SIGTERM); the uploader never leaves a half-published state, it can only stop."""
        if self.proc.poll() is None:
            self.proc.terminate()

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for fd in (self._master, self._slave):
            if fd is not None:
                os.close(fd)
        self._master = self._slave = None
