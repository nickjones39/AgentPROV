"""D-550 at import: the first validation stores its round trips, and nothing it writes changes.

An import with the cache writes the same corpus bytes as one without it, at every worker count and in process. Each
validated execution leaves one entry, and a later ``validate --corpus`` is served from them with the same report. A
``prov`` job uses a hint only for the bytes it names and returns the round trip it ran.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import seal_support as ss

from agentprov.adapters.runner import provjob
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.validation import validate_corpus
from agentprov.corpus.writer import CorpusWriter
from agentprov.validate.cache import DiskCache

SPEC = "agentprov-prov/0.1"


def import_into(root: Path, inputs: Path, cache: DiskCache | None, **kwargs: Any) -> Path:
    with CorpusWriter(root) as corpus:
        report = import_source("agentdojo", LocalTree(inputs), corpus=corpus, part="2024-06",
                               pin_check=ss.support.vouch(inputs), pin=ss.PIN, validation_cache=cache,
                               **{"mode": "release", **kwargs})
    assert report.exit_code == 0, report.counters
    return root.with_name(root.name + ".partial")


def tree_bytes(root: Path) -> dict[str, bytes]:
    skip = ("corpus.json",)  # records the run's isolation (worker or in-process), as without the cache
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and p.name not in skip and ".agentprov.lock" not in p.name}


@pytest.fixture(scope="module")
def inputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("cache-import") / "in"
    ss.support.agentdojo_tree(root, count=3)
    return root


@pytest.mark.parametrize("options", [{"workers": 1}, {"workers": 2},
                                     {"in_process": True, "mode": "dev"}])
def test_an_import_with_the_cache_writes_the_same_corpus(tmp_path: Path, inputs: Path, options: dict[str, Any]) -> None:
    plain = import_into(tmp_path / "plain", inputs, None, **options)
    cache = DiskCache(tmp_path / "cache")
    cached = import_into(tmp_path / "cached", inputs, cache, **options)
    assert tree_bytes(cached) == tree_bytes(plain)
    assert cache.stats.stored == 3 and cache.stats.unstorable == 0
    reader = CorpusReader.open(cached)
    for row in reader.index():
        assert cache.path_for(hashlib.sha256(reader.prov_bytes(row, SPEC)).hexdigest()).is_file()


def test_validation_after_import_is_served_by_the_cache(tmp_path: Path, inputs: Path) -> None:
    cache = DiskCache(tmp_path / "cache")
    corpus = import_into(tmp_path / "c", inputs, cache, workers=1)

    def report(**kwargs: Any) -> bytes:
        outcome = validate_corpus(CorpusReader.open(corpus), mode="release", **kwargs)
        assert outcome.counters["results_reproduced"] == 3
        return json.dumps(outcome.report({"corpus_id": "x"}), sort_keys=True).encode()

    off = report()
    for jobs in (None, 2):
        warm = DiskCache(tmp_path / "cache")
        assert report(jobs=jobs, cache=warm) == off
        assert warm.stats.hits == 3 and warm.stats.stored == 0


class _Ctx:
    def __init__(self, inputs: list[bytes], params: dict[str, Any]) -> None:
        self.inputs, self.params, self.frames = inputs, params, []

    def read_input(self, index: int) -> bytes:
        return self.inputs[index]

    def emit(self, frame: dict[str, Any]) -> None:
        self.frames.append(frame)

    def member(self, header: dict[str, Any]) -> None:
        self.frames.append({"$member": header})

    def data(self, data: bytes) -> None:
        self.frames.append({"$data": len(data)})


def test_the_prov_job_uses_a_hint_only_for_its_own_bytes(tmp_path: Path, inputs: Path) -> None:
    cache = DiskCache(tmp_path / "cache")
    corpus = import_into(tmp_path / "c", inputs, cache, workers=1)
    reader = CorpusReader.open(corpus)
    rows = reader.index()
    params = {"spec": SPEC, "strict": True, "validate": True, "semantics": ["agentdojo.suites@2"], "derive": True}

    def run(row: Any, hint: bytes | None) -> _Ctx:
        fidelity = {"collect": True, "hint": hint is not None}
        ctx = _Ctx([reader.aer_bytes(row), *([hint] if hint is not None else [])], {**params, "fidelity": fidelity})
        provjob.job_prov(ctx)
        return ctx

    plain = _Ctx([reader.aer_bytes(rows[0])], dict(params))
    provjob.job_prov(plain)
    own = cache.hint(hashlib.sha256(reader.prov_bytes(rows[0], SPEC)).hexdigest())
    other = cache.hint(hashlib.sha256(reader.prov_bytes(rows[1], SPEC)).hexdigest())
    served, wrong, cold = run(rows[0], own), run(rows[0], other), run(rows[0], None)
    validation = [f for f in plain.frames if "validation" in f]
    for ctx in (served, wrong, cold):
        assert [f for f in ctx.frames if "validation" in f] == validation
    assert not any("fidelity" in f for f in served.frames)  # served from the hint: nothing new to store
    assert any("fidelity" in f for f in wrong.frames) and any("fidelity" in f for f in cold.frames)
    assert not any("fidelity" in f for f in plain.frames)


def test_a_job_that_skips_conformance_never_reads_a_hint_or_returns_a_frame(tmp_path: Path, inputs: Path) -> None:
    """G2c-5 (``conformance: false``, CLI robustness): the fidelity params are ignored, so nothing is read or stored."""
    corpus = import_into(tmp_path / "c", inputs, None, workers=1)
    reader = CorpusReader.open(corpus)
    row = reader.index()[0]
    params = {"spec": SPEC, "strict": True, "validate": True, "semantics": ["agentdojo.suites@2"], "derive": True,
              "conformance": False, "fidelity": {"collect": True, "hint": True}}

    class NoHint(_Ctx):
        def read_input(self, index: int) -> bytes:
            assert index == 0, "a skipped job reads no hint"
            return super().read_input(index)

    ctx = NoHint([reader.aer_bytes(row)], params)
    provjob.job_prov(ctx)
    assert not any("fidelity" in f for f in ctx.frames)
