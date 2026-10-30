"""Inputs for the import-pipeline tests (``import_support``; not collected): small source trees built in a temporary
directory from the committed, licence-cleared fixtures (loaded programmatically; their text is never printed).

* :func:`agentdojo_tree`: the golden native June-2024 logs N-C01..N-C09 at their pinned ``runs/...`` paths;
* :func:`adprov_tree`: the released golden transcript/v1 pairs R01..R10 at their ``corpus-prov``-relative paths;
* :func:`inspect_tree`: the one committed survey AgentHarm ``.eval`` log at its ``agentharm/results/...`` path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from agentprov.testing import golden

REPO = Path(__file__).resolve().parents[2]
INSPECT_LOG = "agentharm/results/gptoss_harmful/2026-08-21T21-23-06-00-00_agentharm_TQQjY9dzdqeuyNhWvATriR.eval"
INSPECT_FIXTURE = REPO / "tests" / "fixtures" / "inspect" / "survey-agentharm" / INSPECT_LOG.rsplit("/", 1)[-1]


def require_golden() -> None:
    reason = golden.golden_skip_reason()
    if reason is not None:
        pytest.skip(reason)


def _write(root: Path, rel: str, data: bytes) -> None:
    path = root.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def agentdojo_entries() -> list[golden.GoldenEntry]:
    require_golden()
    return list(golden.native_logs())


def agentdojo_tree(root: Path, *, count: int | None = None) -> dict[str, golden.GoldenEntry]:
    """The native logs at their pinned paths below ``root``; returns path -> entry."""
    entries = agentdojo_entries()[:count] if count is not None else agentdojo_entries()
    out: dict[str, golden.GoldenEntry] = {}
    for entry in entries:
        rel = str(entry.origin["path"])
        _write(root, rel, entry.native_bytes())
        out[rel] = entry
    return out


def adprov_tree(root: Path) -> dict[str, golden.GoldenEntry]:
    """The released v1 transcripts below ``root`` (the ``corpus/corpus-prov`` tree root); returns label -> entry."""
    require_golden()
    out: dict[str, golden.GoldenEntry] = {}
    for entry in golden.v1_pairs():
        if entry.tree != "release":
            continue
        # the index records the stem relative to the old repository ("corpus/corpus-prov/<model>/prov/<attack>/<stem>")
        stem = str(entry.origin["corpus_relpath"])
        label = stem.removeprefix("corpus/corpus-prov/") + ".transcript.json"
        _write(root, label, entry.transcript_bytes())
        out[label] = entry
    return out


def inspect_tree(root: Path) -> Path:
    if not INSPECT_FIXTURE.is_file():
        pytest.skip("the committed survey AgentHarm log is not present")
    _write(root, INSPECT_LOG, INSPECT_FIXTURE.read_bytes())
    return root


AGENTDOJO = "https://github.com/ethz-spylab/agentdojo"
C274885 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
SURVEY = "https://github.com/Forever-CodingNoob/agent-security-tools-survey"
SURVEY_COMMIT = "89c4db2c949797fbb38c5bfed85dc82780ddbfe3"


def vouch(root: Path, *, repo: str = AGENTDOJO, commit: str = C274885) -> Any:
    """A ``blob`` pin check that vouches for every file below ``root`` (a test listing built from the files themselves:
    the pipeline mechanics, not the pin, are under test)."""
    from agentprov.adapters.runner.importer import PinCheck

    listing = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath, name)
            listing[path.relative_to(root).as_posix()] = golden.git_blob_sha1(path.read_bytes())
    return PinCheck("blob", {"commit": commit, "role": "test"}, listing=listing, repo=repo)


def tree_bytes(root: Path, *, skip: tuple[str, ...] = ()) -> dict[str, bytes]:
    """Every regular file below ``root`` (relative POSIX path -> bytes), the lock and ``raw/tmp`` excluded."""
    out: dict[str, bytes] = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath, name)
            rel = path.relative_to(root).as_posix()
            if rel == ".agentprov.lock" or rel.startswith("raw/tmp/") or rel in skip:
                continue
            out[rel] = path.read_bytes()
    return out
