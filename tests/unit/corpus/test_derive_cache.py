"""D-550 in ``derive``, ``recompute`` and ``verify --level rederive``: the round-trip cache never changes an output.

A ``recompute`` with the cache off, cold and warm gives the same comparison and the same new corpus bytes, in
process and with workers. A warm run serves every round trip from the hints its jobs get, and stores nothing new.
``verify --level rederive`` gives the same findings with and without it. ``--no-validation-cache`` writes nothing.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.cli.main import main
from agentprov.testing import fs_guard


def run(capsys: pytest.CaptureFixture[str], *argv: str, guard: Path | None = None) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    with fs_guard.unchanged(guard) if guard is not None else _null():
        code = main([*argv, "--json"])
    out, err = capsys.readouterr()
    return code, json.loads(out), err


class _null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def cache_root() -> Path:
    return Path(os.environ["AGENTPROV_HOME"]) / "cache" / "tier4"


def entries() -> list[Path]:
    return sorted(p for p in cache_root().rglob("*.json") if ".tmp-" not in p.name)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    yield ds.agentdojo_corpus(tmp_path_factory.mktemp("derive-cache"), count=2)


def comparison(summary: dict[str, Any]) -> dict[str, Any]:
    return {k: summary.get(k) for k in ("counters", "exit_code", "failures", "issues_by_code")}


@pytest.mark.parametrize("workers", [["--in-process"], ["--jobs", "2"]])
def test_recompute_dry_run_off_cold_and_warm_agree(capsys, source, workers):
    argv = ["recompute", "--corpus", str(source), "--dry-run", "--stages", "sem,prov,validation", *workers]
    code, off, _ = run(capsys, *argv, "--no-validation-cache", guard=ds.partial(source))
    assert code == 0 and not entries()
    code_cold, cold, err_cold = run(capsys, *argv, guard=ds.partial(source))
    stored = entries()
    code_warm, warm, err_warm = run(capsys, *argv, guard=ds.partial(source))
    assert code_cold == code_warm == 0
    assert comparison(off) == comparison(cold) == comparison(warm)
    assert off["counters"]["identical"] == off["counters"]["selected"] == 2
    assert len(stored) == 2 and "stored 2" in err_cold
    assert "hits 2" in err_warm and "stored" not in err_warm.split("round-trip cache", 1)[1].splitlines()[0]
    assert entries() == stored


def test_recompute_out_writes_the_same_corpus_with_the_cache(capsys, source, tmp_path):
    base = ["recompute", "--corpus", str(source), "--stages", "sem,prov,validation", "--no-reuse", "--in-process"]
    assert run(capsys, *base, "--out", str(tmp_path / "off"), "--no-validation-cache")[0] == 0
    assert run(capsys, *base, "--out", str(tmp_path / "cold"))[0] == 0
    assert run(capsys, *base, "--out", str(tmp_path / "warm"))[0] == 0
    trees = {name: ds.tree_bytes(ds.partial(tmp_path / name)) for name in ("off", "cold", "warm")}
    for name in ("cold", "warm"):
        assert set(trees[name]) == set(trees["off"])
        differ = sorted(k for k in trees["off"] if trees["off"][k] != trees[name][k])
        assert differ in ([], ["corpus.json"]), differ
        if differ:  # only the recorded run (isolation, timing-free) may differ; never an output
            a = json.loads(trees["off"]["corpus.json"])
            b = json.loads(trees[name]["corpus.json"])
            assert {k for k in a if a[k] != b.get(k)} <= {"producer"}


def test_verify_rederive_agrees_with_and_without_the_cache(capsys, source):
    argv = ["verify", "--corpus", str(source), "--level", "rederive", "--in-process"]
    off = run(capsys, *argv, "--no-validation-cache", guard=ds.partial(source))
    cold = run(capsys, *argv, guard=ds.partial(source))
    warm = run(capsys, *argv, guard=ds.partial(source))
    assert off[0] == cold[0] == warm[0]
    assert comparison(off[1]) == comparison(cold[1]) == comparison(warm[1])
    assert "hits 2" in warm[2]
