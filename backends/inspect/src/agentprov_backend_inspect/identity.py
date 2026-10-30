"""Identity of an Inspect backend environment (D-663; D.10.6 analogue).

``task_files_sha256`` is the sha256 of the JCS object ``{relative path: sha256 of the file}`` over every regular file
of the benchmark's task package directory (``inspect_evals/agentharm`` for AgentHarm), ``__pycache__`` excluded. It is
computed from bytes on disk only, so T0 computes it without importing anything and the worker reports the same value
from the directory its imported module came from: a patched working copy (as in the kexin-xu-01 and fragfuse logs) is
told apart from the release, and the checked process does not answer its own check. Together with the RECORD digests of
the installed distributions (T0, ``cli/live/envs.py``) and the dataset digests (:mod:`.provision`) it is the identity
T0 compares with ``hello_ok`` before any model call.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import rfc8785

__all__ = ["task_files", "task_files_sha256"]


def task_files(directory: Path) -> dict[str, str]:
    """``{posix relative path: sha256}`` of every regular file under ``directory`` (no symlinks, no ``__pycache__``)."""
    out: dict[str, str] = {}
    for root, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not (Path(root) / d).is_symlink())
        for name in sorted(files):
            path = Path(root) / name
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(directory).as_posix()
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def task_files_sha256(directory: Path) -> tuple[str, int]:
    """``("sha256:<hex>", file count)`` of :func:`task_files`."""
    files = task_files(directory)
    doc: dict[str, Any] = {"files": files}
    return "sha256:" + hashlib.sha256(rfc8785.dumps(doc)).hexdigest(), len(files)
