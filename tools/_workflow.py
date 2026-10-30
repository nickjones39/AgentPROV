"""Shared helpers for the multi-agent workflow tools (design: ``docs/reports/workflow-tools/design.md``).

Used by ``session_status.py``, ``queue_status.py`` and ``reserve_id.py``. Standard library only: the tools run with the
repository's interpreter but never import ``agentprov``, so they keep working on a branch whose product code is broken.

* Machine-local state lives under ``$AGENTPROV_HOME`` (default ``~/.agentprov``), outside every worktree.
* JSON files are written atomically (temporary file in the same directory, then ``os.replace``).
* Text read from state files was written by other processes, so it is printed through :func:`safe_text`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def agentprov_home(environ: Mapping[str, str] = os.environ) -> Path:
    """``$AGENTPROV_HOME``, else ``~/.agentprov``."""
    home = environ.get("AGENTPROV_HOME")
    return Path(home).expanduser() if home else Path.home() / ".agentprov"


def utc_now() -> str:
    """The current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str) -> float | None:
    """Seconds since the epoch for a ``YYYY-MM-DDTHH:MM:SSZ`` string, or None if it is not one."""
    try:
        return _dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.UTC).timestamp()
    except (TypeError, ValueError):
        return None


def git(args: list[str], cwd: Path | str | None = None, *, check: bool = True) -> str:
    """Run ``git`` with lazy fetching disabled (no network) and return stdout without the trailing newline."""
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, check=False)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.rstrip("\n")


def git_ok(args: list[str], cwd: Path | str | None = None) -> str | None:
    """Like :func:`git`, but None instead of an exception when git fails."""
    try:
        return git(args, cwd)
    except (RuntimeError, OSError):
        return None


def write_json_atomic(path: Path, data: Any) -> None:
    """Write ``data`` as indented, key-sorted JSON with a final newline, atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, max_bytes: int = 1 << 20) -> Any:
    """Parse a JSON file of at most ``max_bytes``; ValueError if it is larger or not JSON."""
    with path.open("rb") as fh:
        raw = fh.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"{path.name}: larger than {max_bytes} bytes")
    return json.loads(raw.decode("utf-8"))


_UNSAFE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}


def safe_text(value: object, limit: int = 200) -> str:
    """``value`` as one printable line: controls, format and separator characters escaped, length capped."""
    text = str(value)
    out = []
    for ch in text:
        if unicodedata.category(ch) in _UNSAFE_CATEGORIES or 0xE0000 <= ord(ch) <= 0xE007F:
            out.append(f"\\u{ord(ch):04x}" if ord(ch) <= 0xFFFF else f"\\U{ord(ch):08x}")
        else:
            out.append(ch)
    line = "".join(out)
    return line if len(line) <= limit else line[: limit - 1] + "…"


_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    """A session or branch name made safe as a file name (``claude/x`` -> ``claude-x``); ValueError if empty."""
    cleaned = _NAME_UNSAFE.sub("-", name).strip("-.")
    if not cleaned:
        raise ValueError(f"no usable file name in {name!r}")
    return cleaned[:120]
