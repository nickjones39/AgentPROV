"""The benchmark dataset inside a backend environment and its per-session copy (D-663; design §2.2).

``backends build`` (T0) copies the pinned dataset files from AgentPROV's fetch cache into
``<env>/share/agentprov/datasets/<benchmark>/<revision>/`` and records their digests in the environment marker. At run
time the worker copies them, checking every sha256 against the descriptor's pins, into the session's
``INSPECT_EVALS_CACHE_DIR`` (a directory under the T2 home), because ``inspect_evals`` writes its ``.jsonl`` copies
beside the files it reads. A missing file or a digest mismatch refuses the run: the harness never lets
``inspect_evals`` fall back to a download (the network is the model endpoint only, D-664).
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from types import ModuleType

__all__ = ["DatasetError", "env_dataset_dir", "provision_session", "verify_dataset"]


class DatasetError(ValueError):
    """The provisioned dataset is missing or does not match its pins."""


def env_dataset_dir(bench: ModuleType, prefix: str | None = None) -> Path:
    """``<env>/share/agentprov/datasets/<benchmark>/<revision>`` (``prefix`` defaults to the running interpreter's)."""
    return Path(prefix or sys.prefix) / "share" / "agentprov" / "datasets" / bench.BENCHMARK / bench.DATASET_REVISION


def _safe(rel: str) -> PurePosixPath:
    path = PurePosixPath(rel)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise DatasetError(f"unsafe dataset path {rel!r}")
    return path


def verify_dataset(root: Path, files: Mapping[str, tuple[str, int]]) -> dict[str, str]:
    """Check every pinned file under ``root`` (regular file, size, sha256); returns ``{path: sha256}``."""
    out: dict[str, str] = {}
    for rel, (sha256, size) in sorted(files.items()):
        path = root.joinpath(*_safe(rel).parts)
        if path.is_symlink() or not path.is_file():
            raise DatasetError(f"the provisioned dataset lacks {rel}")
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
            raise DatasetError(f"the provisioned dataset file {rel} does not match its pin")
        out[rel] = sha256
    return out


def provision_session(bench: ModuleType, cache_dir: Path, *, prefix: str | None = None) -> dict[str, str]:
    """Copy the environment's dataset into ``cache_dir`` (the session's ``INSPECT_EVALS_CACHE_DIR``) where the task
    looks for it, checking each file before and after the copy. Returns ``{path: sha256}``."""
    source = env_dataset_dir(bench, prefix)
    digests = verify_dataset(source, bench.DATASET_FILES)
    dest = cache_dir.joinpath(*_safe(bench.CACHE_SUBDIR).parts)
    for rel in sorted(bench.DATASET_FILES):
        target = dest.joinpath(*_safe(rel).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.joinpath(*_safe(rel).parts).read_bytes()
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    if verify_dataset(dest, bench.DATASET_FILES) != digests:  # pragma: no cover - the copy is of verified bytes
        raise DatasetError("the session copy of the dataset does not match its pins")
    return digests
