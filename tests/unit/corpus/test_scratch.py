"""Temporary corpus trees on the source's filesystem (perf round 2, item 1a: ``$AGENTPROV_HOME`` on its own volume)."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentprov.corpus import scratch
from agentprov.corpus.scratch import scratch_tree


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _devices(monkeypatch: pytest.MonkeyPatch, devices: dict[Path, int]) -> None:
    """``os.stat`` in the module reports ``devices[path]`` as ``st_dev`` for the paths given."""
    real = os.stat

    def fake(path: str | os.PathLike[str], *args: object, **kwargs: object) -> object:
        result = real(path, *args, **kwargs)  # type: ignore[arg-type]
        dev = devices.get(Path(path))
        return result if dev is None else SimpleNamespace(st_dev=dev, st_mode=result.st_mode)

    monkeypatch.setattr(scratch.os, "stat", fake)


def test_the_tree_goes_under_agentprov_home_when_it_shares_the_corpus_volume(home, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    tree = scratch_tree("agentprov-recompute-", corpus)
    try:
        assert tree.parent == home / "tmp" and tree.name.startswith("agentprov-recompute-")
        assert stat.S_IMODE(tree.stat().st_mode) == 0o700
    finally:
        tree.rmdir()


def test_the_system_temp_dir_is_used_when_only_it_shares_the_corpus_volume(home, tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    system = Path(tempfile.gettempdir())
    _devices(monkeypatch, {corpus: 7, home / "tmp": 8, system: 7})
    tree = scratch_tree("agentprov-verify-", corpus)
    try:
        assert tree.parent == system
    finally:
        tree.rmdir()


def test_a_corpus_on_a_third_volume_falls_back_to_the_system_temp_dir(home, tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    system = Path(tempfile.gettempdir())
    _devices(monkeypatch, {corpus: 9, home / "tmp": 8, system: 7})
    for near in (corpus, tmp_path / "missing"):  # a source that cannot be stat'ed falls back the same way
        tree = scratch_tree("agentprov-recompute-", near)
        try:
            assert tree.parent == system
        finally:
            tree.rmdir()
